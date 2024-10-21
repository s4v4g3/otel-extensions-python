import random
import time
from typing import cast

from opentelemetry import trace
from opentelemetry.trace import SpanContext

from otel_extensions import TelemetryOptions, init_telemetry_provider, instrumented


@instrumented
def foobar() -> None:
    # automatically creates a "foobar" span due to "instrumented" decorator
    time.sleep(random.randint(0, 10) / 10.0)


@instrumented(span_name="my custom span name")
def bar() -> None:
    # automatically creates a span due to "instrumented" decorator, using a custom name

    # set an attribute for the span
    trace.get_current_span().set_attribute("some key", "some value")
    time.sleep(random.randint(0, 5) / 10.0)
    # create an event (log) attached to the span
    trace.get_current_span().add_event("my event")
    foobar()
    time.sleep(random.randint(0, 5) / 10.0)


@instrumented
def foo() -> None:
    # automatically creates a span due to "instrumented" decorator
    for _ in range(0, random.randint(10, 20)):
        bar()


def main() -> int:
    # manually create a span
    with trace.get_tracer(__name__).start_as_current_span("main") as span:
        foo()
        return cast(SpanContext, span.get_span_context()).trace_id


if __name__ == "__main__":
    # one-time collection setup -- assumes a collector agent running locally with an http receiver on port 4318
    options = TelemetryOptions(
        OTEL_SERVICE_NAME="OpenTelemetry Example",
        OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318",
        OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf",
    )
    init_telemetry_provider(options)
    trace_id = main()
    print(f"https://jaegertracing-poc.dev.silabs.net/trace/{trace_id:032x}")
