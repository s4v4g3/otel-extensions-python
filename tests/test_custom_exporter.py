import pytest
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.trace import ReadableSpan
import typing
from otel_extensions import (
    TelemetryOptions,
    init_telemetry_provider,
    get_tracer,
    flush_telemetry_data,
)


class FakeCustomExporter(SpanExporter):
    all_spans = []

    def __init__(self, endpoint: str = None):
        assert endpoint == "unused"
        self.spans = []

    def export(self, spans: typing.Sequence[ReadableSpan]) -> "SpanExportResult":
        self.spans.extend(spans)
        self.all_spans.extend(spans)
        return SpanExportResult.SUCCESS


@pytest.mark.parametrize("span_name", ["foo", "bar"])
@pytest.mark.parametrize("service_name", ["foo_service", "bar_service"])
@pytest.mark.parametrize("processor_type", ["simple", "batch"])
def test_custom_exporter(processor_type, service_name, span_name):
    type_name = f"{__name__}.{FakeCustomExporter.__name__}"
    options = TelemetryOptions(
        OTEL_EXPORTER_OTLP_ENDPOINT="unused",
        OTEL_EXPORTER_OTLP_PROTOCOL="custom",
        OTEL_EXPORTER_CUSTOM_SPAN_EXPORTER_TYPE=type_name,
        OTEL_SERVICE_NAME=service_name,
        OTEL_PROCESSOR_TYPE=processor_type,
    )
    init_telemetry_provider(options)
    tracer = get_tracer(__name__, service_name)
    with tracer.start_as_current_span(span_name) as span:
        assert span.name == span_name
        span_id = span.context.span_id
    flush_telemetry_data()
    assert span_id in [span.context.span_id for span in FakeCustomExporter.all_spans]
