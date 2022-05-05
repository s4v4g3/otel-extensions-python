from typing import Callable, Optional
import os
from functools import wraps
import logging
import inspect
from pydantic import BaseSettings
from opentelemetry import context, trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

TRACEPARENT_VAR = "TRACEPARENT"


class TelemetryOptions(BaseSettings):
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = None
    OTEL_EXPORTER_OTLP_PROTOCOL: str = "grpc"
    SERVICE_NAME: str = ""


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


def init_telemetry_provider(options: TelemetryOptions):
    try:

        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor

        otlp_endpoint = options.OTEL_EXPORTER_OTLP_ENDPOINT
        if otlp_endpoint:
            resource = Resource(attributes={SERVICE_NAME: options.SERVICE_NAME})
            provider = TracerProvider(resource=resource)
            if options.OTEL_EXPORTER_OTLP_PROTOCOL == "grpc":
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter as GRPCSpanExporter,
                )

                processor = SimpleSpanProcessor(GRPCSpanExporter())
            elif options.OTEL_EXPORTER_OTLP_PROTOCOL == "http/protobuf":
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                    OTLPSpanExporter as HTTPSpanExporter,
                )

                processor = SimpleSpanProcessor(HTTPSpanExporter())
            else:
                raise ValueError("Invalid value for OTEL_EXPORTER_OTLP_PROTOCOL")
            provider.add_span_processor(processor)
            trace.set_tracer_provider(provider)
    except ImportError:
        pass

    traceparent = os.environ.get(TRACEPARENT_VAR)
    carrier = {"traceparent": traceparent} if traceparent else {}
    context.attach(TraceContextTextMapPropagator().extract(carrier=carrier))


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
    def __init__(self, span_name=None):
        self.span_name = span_name

    def __call__(self, wrapped_function: Callable) -> Callable:
        @wraps(wrapped_function)
        def new_f(*args, **kwargs):
            module = inspect.getmodule(wrapped_function)
            module_name = __name__
            if module is not None:
                module_name = module.__name__
            span_name = self.span_name or wrapped_function.__qualname__
            with trace.get_tracer(module_name).start_as_current_span(span_name):
                return wrapped_function(*args, **kwargs)

        return new_f


def instrumented(
    wrapped_function: Optional[Callable] = None,
    *,
    span_name: Optional[str] = None,
):
    """
    Decorator to enable opentelemetry instrumentation on a function.

    When the decorator is used, a child span will be created in the current trace
    context, using the fully-qualified function name as the span name.
    Alternatively, the span name can be set manually by setting the span_name parameter

    @param wrapped_function:  function or method to wrap
    @param span_name:  optional span name
    """
    inst = Instrumented(span_name=span_name)
    if wrapped_function:
        return inst(wrapped_function)
    return inst
