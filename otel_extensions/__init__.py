import importlib
import inspect
import logging
import os
import warnings
from functools import wraps
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Optional,
    TypeVar,
    Union,
    cast,
    overload,
)

from opentelemetry import context, trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Tracer
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.util.types import AttributeValue as SpanAttributeValue

CallableType = Callable[..., Any]
DecoratedFuncType = TypeVar("DecoratedFuncType", bound=CallableType)

__all__ = [
    "TelemetryOptions",
    "TraceEventLogHandler",
    "init_telemetry_provider",
    "instrumented",
    "TraceContextCarrier",
    "get_tracer",
    "flush_telemetry_data",
    "ContextInjector",
    "inject_context_to_env",
]

global_tracer_provider: Optional[TracerProvider] = None
tracer_providers_by_service_name: Dict[str, TracerProvider] = {}


class TelemetryOptions:
    """Settings class holding options for telemetry"""

    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = None
    OTEL_EXPORTER_OTLP_CERTIFICATE: Optional[str] = None
    OTEL_EXPORTER_OTLP_PROTOCOL: str = "http/protobuf"
    OTEL_EXPORTER_CUSTOM_SPAN_EXPORTER_TYPE: str = ""
    OTEL_SERVICE_NAME: str = ""
    OTEL_PROCESSOR_TYPE: str = "batch"
    TRACEPARENT: Optional[str] = None

    def __init__(self, *_args: Any, **kwargs: Any) -> None:
        all_attrs = [attr for attr in dir(self.__class__) if not attr.startswith("_")]
        # set default values from env
        for attr in all_attrs:
            default_val = getattr(self.__class__, attr)
            setattr(self, attr, os.environ.get(attr, default_val))
        # set values from args
        for kwarg in kwargs:
            if kwarg not in all_attrs:
                raise ValueError(f"{kwarg} is an invalid keyword argument")
            setattr(self, kwarg, kwargs[kwarg])


class TraceContextCarrier:
    """Helper class to simplify context propagation tasks"""

    traceparent_var = "TRACEPARENT"

    def __init__(self, carrier: Optional[Dict[str, str]] = None):
        self.token: Optional[object] = None
        if carrier is None:
            carrier = {}
            TraceContextTextMapPropagator().inject(carrier)
        self.carrier: Dict[str, str] = carrier

    def __enter__(self) -> "TraceContextCarrier":
        if self.token is None:
            self.token = self.__attach(self.carrier)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.detach()

    @classmethod
    def attach_from_env(cls) -> "TraceContextCarrier":
        traceparent = os.environ.get(cls.traceparent_var)
        carrier = TraceContextCarrier(
            carrier={"traceparent": traceparent} if traceparent is not None else {}
        )
        carrier.attach()
        return carrier

    @classmethod
    def attach_from_options(cls, options: TelemetryOptions) -> "TraceContextCarrier":
        traceparent = options.TRACEPARENT
        carrier = TraceContextCarrier(
            carrier={"traceparent": traceparent} if traceparent is not None else {}
        )
        carrier.attach()
        return carrier

    @classmethod
    def inject_to_env(cls) -> None:
        ctx = TraceContextCarrier()
        if "traceparent" in ctx.carrier:
            os.environ[cls.traceparent_var] = ctx.carrier["traceparent"]

    def attach(self) -> None:
        self.token = self.__attach(self.carrier)

    def detach(self) -> None:
        if self.token is not None:
            context.detach(self.token)
            self.token = None

    def __eq__(self, other: object) -> bool:
        return isinstance(other, TraceContextCarrier) and self.carrier == other.carrier

    @classmethod
    def __attach(cls, carrier: Dict[str, str]) -> object:
        token = context.attach(TraceContextTextMapPropagator().extract(carrier=carrier))
        return token


if TYPE_CHECKING:
    BaseStreamHandler = logging.StreamHandler["TraceEventLogHandler"]
else:
    BaseStreamHandler = logging.StreamHandler


class TraceEventLogHandler(BaseStreamHandler):
    """log handler class that adds log messages as events in the current span"""

    def __init__(self) -> None:
        super().__init__(stream=self)
        self.name = "TraceEventLogHandler"

    def write(self, msg: str) -> None:
        if msg != self.terminator:
            current_span = trace.get_current_span()
            current_span.add_event(msg)

    def flush(self) -> None:
        """no need to flush"""


def get_tracer(module_name: str, service_name: Optional[str] = None) -> Tracer:
    """
    Get the `Tracer` for the specified module and service name
    Args:
        module_name: module name
        service_name: optional service name

    Returns: a Tracer object

    """
    global global_tracer_provider, tracer_providers_by_service_name
    tracer_provider = (
        global_tracer_provider
        if service_name is None
        else tracer_providers_by_service_name.get(service_name)
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return trace.get_tracer(module_name, tracer_provider=tracer_provider)


def init_telemetry_provider(
    options: Optional[TelemetryOptions] = None, **resource_attrs: Any
) -> None:
    """
    Initialize telemetry collection for a service, and inherits any trace context
    set from the TRACEPARENT environment variable

    Args:
        options:  `TelemetryOptions` settings object

    """
    if options is None:
        options = TelemetryOptions()
    otlp_endpoint = options.OTEL_EXPORTER_OTLP_ENDPOINT
    if otlp_endpoint:
        _try_load_trace_provider(options, **resource_attrs)

    # Check if TRACEPARENT is set in options otherwise attach to context from TRACEPARENT
    # environment, but only if we don't already have a context with a span parent
    if len(context.get_current()) == 0:
        if options.TRACEPARENT:
            TraceContextCarrier.attach_from_options(options)
        else:
            TraceContextCarrier.attach_from_env()


def flush_telemetry_data() -> None:
    """Forces a flush of all span exporters attached to trace providers"""
    global global_tracer_provider, tracer_providers_by_service_name
    if global_tracer_provider is not None:
        global_tracer_provider.force_flush()  # noqa
    for service in tracer_providers_by_service_name:
        provider = tracer_providers_by_service_name[service]
        provider.force_flush()  # noqa


def _try_load_trace_provider(options: TelemetryOptions, **resource_attrs: Any) -> None:
    global global_tracer_provider, tracer_providers_by_service_name
    try:
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            SimpleSpanProcessor,
        )

        service_name = options.OTEL_SERVICE_NAME
        if service_name == "":
            logging.getLogger(__name__).warning(
                "OTEL_SERVICE_NAME not set; defaulting to 'otel_extensions'"
            )
            service_name = "otel_extensions"
        resource = Resource(attributes={SERVICE_NAME: service_name, **resource_attrs})
        tracer_provider = TracerProvider(resource=resource)
        processor_type = (
            BatchSpanProcessor
            if options.OTEL_PROCESSOR_TYPE == "batch"
            else SimpleSpanProcessor
        )
        if (
            options.OTEL_EXPORTER_OTLP_CERTIFICATE is not None
            and "OTEL_EXPORTER_OTLP_CERTIFICATE" not in os.environ
        ):
            os.environ["OTEL_EXPORTER_OTLP_CERTIFICATE"] = (
                options.OTEL_EXPORTER_OTLP_CERTIFICATE
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


def _get_traces_endpoint(options: TelemetryOptions) -> str:
    path = (
        "v1/traces"
        if options.OTEL_EXPORTER_OTLP_ENDPOINT
        and options.OTEL_EXPORTER_OTLP_ENDPOINT.endswith("/")
        else "/v1/traces"
    )
    endpoint = f"{options.OTEL_EXPORTER_OTLP_ENDPOINT}{path}"
    return endpoint


class ContextInjector:
    def __call__(self, wrapped_function: CallableType) -> CallableType:
        @wraps(wrapped_function)
        def new_f(*args: Any, **kwargs: Any) -> Any:
            prev_env = os.environ.get(TraceContextCarrier.traceparent_var)
            TraceContextCarrier.inject_to_env()
            try:
                return wrapped_function(*args, **kwargs)
            finally:
                if prev_env:
                    os.environ[TraceContextCarrier.traceparent_var] = prev_env

        return new_f


def inject_context_to_env(wrapped_function: CallableType) -> CallableType:
    injector = ContextInjector()
    return injector(wrapped_function)


class Instrumented:
    def __init__(
        self,
        span_name: Optional[str] = None,
        service_name: Optional[str] = None,
        span_attributes: Optional[Dict[str, SpanAttributeValue]] = None,
    ) -> None:
        self.span_name = span_name
        self.service_name = service_name
        self.span_attributes = span_attributes if span_attributes is not None else {}
        self.process_modules = os.environ.get("OTEL_PROCESS_MODULES", "")

    def __call__(self, wrapped_function: DecoratedFuncType) -> DecoratedFuncType:
        module = inspect.getmodule(wrapped_function)
        is_async = inspect.iscoroutinefunction(wrapped_function)
        module_name = __name__
        if module is not None:
            module_name = module.__name__
        span_name = self.span_name or wrapped_function.__qualname__

        create_span = True
        if hasattr(wrapped_function, "__module__"):
            func_module_path = wrapped_function.__module__
            self.span_attributes["module.name"] = func_module_path
            create_span = self._module_allowed(func_module_path)

        @wraps(wrapped_function)
        def new_f(*args: Any, **kwargs: Any) -> Any:
            if create_span:
                with get_tracer(
                    module_name, service_name=self.service_name
                ).start_as_current_span(span_name) as span:
                    span.set_attributes(self.span_attributes)
                    return wrapped_function(*args, **kwargs)
            else:
                return wrapped_function(*args, **kwargs)

        @wraps(wrapped_function)
        async def new_f_async(*args: Any, **kwargs: Any) -> Any:
            if create_span:
                with get_tracer(
                    module_name, service_name=self.service_name
                ).start_as_current_span(span_name) as span:
                    span.set_attributes(self.span_attributes)
                    return await wrapped_function(*args, **kwargs)
            else:
                return await wrapped_function(*args, **kwargs)

        return (
            cast(DecoratedFuncType, new_f_async)
            if is_async
            else cast(DecoratedFuncType, new_f)
        )

    def _module_allowed(self, func_module_path: str) -> bool:
        if not self.process_modules:
            return True

        modules = self.process_modules.split(",")
        module_path = str(func_module_path).lower()
        for mod in modules:
            if str(mod).lower() in module_path:
                return True
        return False


@overload
def instrumented(wrapped_function: DecoratedFuncType) -> DecoratedFuncType: ...


@overload
def instrumented(
    *,
    span_name: Optional[str] = None,
    service_name: Optional[str] = None,
    span_attributes: Optional[Dict[str, SpanAttributeValue]] = None,
) -> Instrumented: ...


def instrumented(
    wrapped_function: Optional[DecoratedFuncType] = None,
    *,
    span_name: Optional[str] = None,
    service_name: Optional[str] = None,
    span_attributes: Optional[Dict[str, SpanAttributeValue]] = None,
) -> Union[DecoratedFuncType, Instrumented]:
    """
    Decorator to enable opentelemetry instrumentation on a function.

    When the decorator is used, a child span will be created in the current trace
    context, using the fully-qualified function name as the span name.
    Alternatively, the span name can be set manually by setting the span_name parameter

    @param wrapped_function:  function or method to wrap
    @param span_name:  optional span name.  Defaults to fully qualified function name of wrapped function
    @param service_name: optional service name.  Defaults to service name set in first invocation
                         of `init_telemetry_provider`
    @param span_attributes: optional dictionary of attributes to be set on the span
    """
    inst = Instrumented(
        span_name=span_name, service_name=service_name, span_attributes=span_attributes
    )
    if wrapped_function:
        return inst(wrapped_function)
    return inst
