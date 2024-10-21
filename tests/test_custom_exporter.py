import typing

import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from otel_extensions import (
    TelemetryOptions,
    flush_telemetry_data,
    get_tracer,
    init_telemetry_provider,
)


class FakeCustomExporter(SpanExporter):
    all_spans = []

    def __init__(self, options: TelemetryOptions):
        assert options.OTEL_EXPORTER_OTLP_ENDPOINT == "unused"
        self.spans = []

    def export(self, spans: typing.Sequence[ReadableSpan]) -> "SpanExportResult":
        self.spans.extend(spans)
        self.all_spans.extend(spans)
        return SpanExportResult.SUCCESS


@pytest.mark.parametrize("span_name", ["foo", "bar"])
@pytest.mark.parametrize("service_name", ["foo_service", "bar_service"])
@pytest.mark.parametrize("processor_type", ["simple", "batch"])
@pytest.mark.parametrize("resource_attrs", [None, {}, {"foo": "bar"}])
def test_custom_exporter(processor_type, service_name, span_name, resource_attrs):
    type_name = f"{__name__}.{FakeCustomExporter.__name__}"
    options = TelemetryOptions(
        OTEL_EXPORTER_OTLP_ENDPOINT="unused",
        OTEL_EXPORTER_OTLP_PROTOCOL="custom",
        OTEL_EXPORTER_CUSTOM_SPAN_EXPORTER_TYPE=type_name,
        OTEL_SERVICE_NAME=service_name,
        OTEL_PROCESSOR_TYPE=processor_type,
    )
    if resource_attrs is not None:
        init_telemetry_provider(options, **resource_attrs)
    else:
        init_telemetry_provider(options)
    tracer = get_tracer(__name__, service_name)
    assert (
        "service.name" in tracer.resource.attributes
        and tracer.resource.attributes["service.name"] == service_name
    )
    if resource_attrs:
        for attr in resource_attrs:
            assert (
                attr in tracer.resource.attributes
                and tracer.resource.attributes[attr] == resource_attrs[attr]
            )
    with tracer.start_as_current_span(span_name) as span:
        assert span.name == span_name
        span_id = span.context.span_id
    flush_telemetry_data()
    assert span_id in [span.context.span_id for span in FakeCustomExporter.all_spans]
