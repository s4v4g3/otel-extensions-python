from otel_extensions import TelemetryOptions
import pytest
import os


def test_invalid_kwarg():
    with pytest.raises(ValueError):
        TelemetryOptions(INVALID_KWARG="foo")


def test_defaults():
    opts = TelemetryOptions()
    assert opts.OTEL_EXPORTER_OTLP_ENDPOINT is None
    assert opts.OTEL_EXPORTER_OTLP_CERTIFICATE is None
    assert opts.OTEL_EXPORTER_OTLP_PROTOCOL == "http/protobuf"
    assert opts.OTEL_EXPORTER_CUSTOM_SPAN_EXPORTER_TYPE == ""
    assert opts.OTEL_SERVICE_NAME == ""
    assert opts.OTEL_PROCESSOR_TYPE == "batch"
    assert opts.TRACEPARENT is None


def test_kwargs():
    opts = TelemetryOptions(OTEL_EXPORTER_OTLP_ENDPOINT="foo")
    assert opts.OTEL_EXPORTER_OTLP_ENDPOINT == "foo"


def test_subclass():
    class TelemetryOptionsSubclass(TelemetryOptions):
        SOME_OTHER_ATTR: str = "foo"

    opts = TelemetryOptionsSubclass()
    assert opts.SOME_OTHER_ATTR == "foo"

    opts = TelemetryOptionsSubclass(SOME_OTHER_ATTR="bar")
    assert opts.SOME_OTHER_ATTR == "bar"

    os.environ["SOME_OTHER_ATTR"] = "foobar"
    try:
        opts = TelemetryOptionsSubclass()
        assert opts.SOME_OTHER_ATTR == "foobar"
    finally:
        del os.environ["SOME_OTHER_ATTR"]
