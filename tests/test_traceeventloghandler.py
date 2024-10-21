from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan

from otel_extensions import TraceEventLogHandler, instrumented


def test_traceloghandler():
    log = TraceEventLogHandler()
    log.write("\n")
    log.write("foo")
    log.flush()

    @instrumented
    def test_fn():
        log.write("bar")
        current_span: ReadableSpan = trace.get_current_span()  # noqa
        assert len(current_span.events) > 0

    test_fn()
