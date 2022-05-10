from typing import Callable, Optional, Dict
import os
from functools import wraps
import logging
import inspect
from pydantic import BaseSettings
from opentelemetry import context, trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
import importlib
import warnings

__all__ = [
    "TelemetryOptions",
    "TraceEventLogHandler",
    "init_telemetry_provider",
    "instrumented",
]
TRACEPARENT_VAR = "TRACEPARENT"

global_tracer_provider: Optional[object] = None
tracer_providers_by_service_name: Dict[str, object] = {}
span_processors = []


class TelemetryOptions(BaseSettings):
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = None
    OTEL_EXPORTER_OTLP_PROTOCOL: str = "http/protobuf"
    OTEL_EXPORTER_CUSTOM_SPAN_EXPORTER_TYPE: str = ""
    OTEL_SERVICE_NAME: str = ""
    OTEL_PROCESSOR_TYPE: str = "batch"


class TraceEventLogHandler(logging.StreamHandler):
    def __init__(self):
        super().__init__(stream=self)
        self.name = "TraceEventLogHandler"

    def write(self, msg: str):
        if msg != self.terminator:
            current_span = trace.get_current_span()
            current_span.add_event(msg)

    def flush(self):
        # no-op
        pass


def get_tracer(module_name: str, service_name: str = None):
    global global_tracer_provider, tracer_providers_by_service_name
    tracer_provider = (
        global_tracer_provider
        if service_name is None
        else tracer_providers_by_service_name.get(service_name)
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return trace.get_tracer(module_name, tracer_provider=tracer_provider)


def init_telemetry_provider(options: TelemetryOptions = None):
    if options is None:
        options = TelemetryOptions()
    otlp_endpoint = options.OTEL_EXPORTER_OTLP_ENDPOINT
    if otlp_endpoint:
        _try_load_trace_provider(options)

    traceparent = os.environ.get(TRACEPARENT_VAR)
    carrier = {"traceparent": traceparent} if traceparent else {}
    context.attach(TraceContextTextMapPropagator().extract(carrier=carrier))


def flush_telemetry_data():
    global global_tracer_provider, tracer_providers_by_service_name
    if global_tracer_provider is not None:
        global_tracer_provider.force_flush()  # noqa
    for service in tracer_providers_by_service_name:
        provider = tracer_providers_by_service_name[service]
        provider.force_flush()  # noqa


def _try_load_trace_provider(options: TelemetryOptions):
    global global_tracer_provider, tracer_providers_by_service_name
    try:
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            SimpleSpanProcessor,
            BatchSpanProcessor,
        )

        service_name = options.OTEL_SERVICE_NAME
        if service_name == "":
            logging.getLogger(__name__).warning(
                "OTEL_SERVICE_NAME not set; defaulting to 'otel_extensions'"
            )
            service_name = "otel_extensions"
        resource = Resource(attributes={SERVICE_NAME: service_name})
        tracer_provider = TracerProvider(resource=resource)
        processor_type = (
            BatchSpanProcessor
            if options.OTEL_PROCESSOR_TYPE == "batch"
            else SimpleSpanProcessor
        )
        if options.OTEL_EXPORTER_OTLP_PROTOCOL == "grpc":
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter as GRPCSpanExporter,
            )

            processor = processor_type(
                GRPCSpanExporter(endpoint=_get_traces_endpoint(options))
            )
        elif options.OTEL_EXPORTER_OTLP_PROTOCOL == "http/protobuf":
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter as HTTPSpanExporter,
            )

            processor = processor_type(
                HTTPSpanExporter(endpoint=_get_traces_endpoint(options))
            )
        elif options.OTEL_EXPORTER_OTLP_PROTOCOL == "custom":
            (
                module_name,
                sep,
                class_name,
            ) = options.OTEL_EXPORTER_CUSTOM_SPAN_EXPORTER_TYPE.rpartition(".")
            if sep == "":
                raise RuntimeError(
                    "Invalid value for OTEL_EXPORTER_CUSTOM_SPAN_EXPORTER_TYPE"
                )
            module = importlib.import_module(module_name)
            klass = getattr(module, class_name)
            processor = processor_type(klass(options=options))
        else:
            raise ValueError("Invalid value for OTEL_EXPORTER_OTLP_PROTOCOL")
        tracer_provider.add_span_processor(processor)
        if global_tracer_provider is None:
            global_tracer_provider = tracer_provider
            trace.set_tracer_provider(global_tracer_provider)
        tracer_providers_by_service_name[service_name] = tracer_provider
    except ImportError:
        pass


def _get_traces_endpoint(options: TelemetryOptions):
    endpoint = (
        f"{options.OTEL_EXPORTER_OTLP_ENDPOINT}v1/traces"
        if options.OTEL_EXPORTER_OTLP_ENDPOINT.endswith("/")
        else options.OTEL_EXPORTER_OTLP_ENDPOINT
    )
    return endpoint


class ContextInjector:
    def __call__(self, wrapped_function: Callable) -> Callable:
        @wraps(wrapped_function)
        def new_f(*args, **kwargs):
            prev_env = os.environ.get(TRACEPARENT_VAR)
            carrier = {}
            TraceContextTextMapPropagator().inject(carrier)
            if "traceparent" in carrier:
                os.environ[TRACEPARENT_VAR] = carrier["traceparent"]
            try:
                return wrapped_function(*args, **kwargs)
            finally:
                if prev_env:
                    os.environ[TRACEPARENT_VAR] = prev_env

        return new_f


def inject_context_to_env(wrapped_function: Callable):
    injector = ContextInjector()
    return injector(wrapped_function)


class Instrumented:
    def __init__(self, span_name: str = None, service_name: str = None):
        self.span_name = span_name
        self.service_name = service_name

    def __call__(self, wrapped_function: Callable) -> Callable:
        @wraps(wrapped_function)
        def new_f(*args, **kwargs):
            module = inspect.getmodule(wrapped_function)
            module_name = __name__
            if module is not None:
                module_name = module.__name__
            span_name = self.span_name or wrapped_function.__qualname__
            with get_tracer(
                module_name, service_name=self.service_name
            ).start_as_current_span(span_name):
                return wrapped_function(*args, **kwargs)

        return new_f


def instrumented(
    wrapped_function: Optional[Callable] = None,
    *,
    span_name: Optional[str] = None,
    service_name: Optional[str] = None,
):
    """
    Decorator to enable opentelemetry instrumentation on a function.

    When the decorator is used, a child span will be created in the current trace
    context, using the fully-qualified function name as the span name.
    Alternatively, the span name can be set manually by setting the span_name parameter

    @param wrapped_function:  function or method to wrap
    @param span_name:  optional span name.  Defaults to fully qualified function name of wrapped function
    @param service_name: optional service name.  Defaults to service name set in first invocation of `init_telemetry_provider`
    """
    inst = Instrumented(span_name=span_name, service_name=service_name)
    if wrapped_function:
        return inst(wrapped_function)
    return inst
