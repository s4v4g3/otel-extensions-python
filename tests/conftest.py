from otel_extensions import init_telemetry_provider, TelemetryOptions
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode, Span, Tracer
import logging
from typing import Optional, Iterator, Union
import traceback
import pytest

tracer: Optional[Tracer]
session_span: Optional[Span]
session_span_iterator: Optional[Iterator[Span]]


def logger():
    return logging.getLogger(__name__)


def convert_outcome(outcome: str) -> Status:
    """Convert from pytest outcome to OpenTelemetry status code"""
    if outcome == "passed":
        return Status(status_code=StatusCode.OK)
    elif (
        outcome == "failed"
        or outcome == "interrupted"
        or outcome == "internal_error"
        or outcome == "usage_error"
        or outcome == "no_tests_collected"
    ):
        return Status(status_code=StatusCode.ERROR)
    else:
        return Status(status_code=StatusCode.UNSET)


def exit_code_to_outcome(exit_code: int) -> str:
    """convert pytest ExitCode to outcome"""
    if exit_code == 0:
        return "passed"
    elif exit_code == 1:
        return "failed"
    elif exit_code == 2:
        return "interrupted"
    elif exit_code == 3:
        return "internal_error"
    elif exit_code == 4:
        return "usage_error"
    elif exit_code == 5:
        return "no_tests_collected"
    else:
        return "failed"


def _start_span(span_name, kind=None):
    """Starts a span with the name, and kind passed as parameters"""
    global tracer
    assert tracer is not None
    span = tracer.start_span(
        span_name, record_exception=True, set_status_on_exception=True, kind=kind
    )
    return span


def _end_span(span, outcome):
    """Ends a span and sets attributes & status"""
    status = convert_outcome(outcome)
    span.set_status(status)
    span.set_attribute("tests.status", outcome)
    span.end()
    return span


def pytest_sessionstart(session):
    """
    Sets up telemetry collection and starts the session span
    """
    global session_span, tracer, session_span_iterator
    init_telemetry_provider(
        TelemetryOptions(
            OTEL_SERVICE_NAME="otel-extensions-tests",
            OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318",
            OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf",
            OTEL_PROCESSOR_TYPE="simple",
        )
    )
    session_name = "otel-extensions test"
    tracer = trace.get_tracer(session_name)
    session_span = _start_span(session_name, trace.SpanKind.SERVER)
    session_span_iterator = trace.use_span(session_span, end_on_exit=False)
    session_span_iterator.__enter__()  # noqa


def pytest_sessionfinish(session, exitstatus):  # noqa: U100
    """Ends the session span with the session outcome"""
    global session_span, session_span_iterator
    if session_span is not None:
        trace_id = session_span.get_span_context().trace_id
        session_span_iterator.__exit__(None, None, None)  # noqa
        _end_span(session_span, exit_code_to_outcome(exitstatus))
        logger().info(f"Trace ID is {trace_id:32x}")


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    with tracer.start_as_current_span(
        item.name,
        record_exception=True,
        set_status_on_exception=True,
    ) as span:
        span.set_attribute("tests.name", item.name)
        yield


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):  # noqa
    report = yield
    rep = report.get_result()

    if rep.when == "call":
        span = trace.get_current_span()
        status = convert_outcome(rep.outcome)
        span.set_status(status)
        span.set_attribute("tests.status", rep.outcome)


def pytest_exception_interact(
    node: Union[pytest.Item, pytest.Collector],
    call: pytest.CallInfo,
    report: Union[pytest.CollectReport, pytest.TestReport],
):
    if isinstance(report, pytest.TestReport) and call.excinfo is not None:
        span = trace.get_current_span()
        stack_trace = repr(
            traceback.format_exception(
                call.excinfo.type, call.excinfo.value, call.excinfo.tb
            )
        )
        span.set_attribute("tests.error", stack_trace)


@pytest.hookimpl()
def pytest_runtest_logreport(report):
    if report.failed and report.when == "call":
        span = trace.get_current_span()
        span.set_attribute("tests.systemerr", report.capstderr)
        span.set_attribute("tests.systemout", report.capstdout)
        span.set_attribute("tests.duration", getattr(report, "duration", 0.0))
