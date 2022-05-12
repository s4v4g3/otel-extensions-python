from otel_extensions_pytest import TelemetryOptions

pytest_plugins = ("otel_extensions_pytest",)


def pytest_addoption(parser, pluginmanager):
    options = TelemetryOptions()
    options.OTEL_SERVICE_NAME = "otel-extensions-python"
    options.OTEL_SESSION_NAME = "unit tests pytest session"
    options.OTEL_PROCESSOR_TYPE = "batch"
    options.OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:4318/"
    options.OTEL_EXPORTER_OTLP_PROTOCOL = "http/protobuf"
