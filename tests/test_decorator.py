from otel_extensions import instrumented
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan


@instrumented
def decorated_function():
    span: ReadableSpan = trace.get_current_span()  # noqa
    assert span.name == "decorated_function"


@instrumented(span_name="overridden span name")
def decorated_function_with_custom_name():
    span: ReadableSpan = trace.get_current_span()  # noqa
    assert span.name == "overridden span name"


@instrumented
async def decorated_async_function():
    span: ReadableSpan = trace.get_current_span()  # noqa
    assert span.name == "decorated_async_function"


@instrumented(span_name="overridden span name")
def decorated_async_function_with_custom_name():
    span: ReadableSpan = trace.get_current_span()  # noqa
    assert span.name == "overridden span name"


def test_decorator_with_default_name():
    decorated_function()


def test_decorator_with_custom_name():
    decorated_function_with_custom_name()


async def test_async_decorator_with_default_name():
    await decorated_async_function()


async def test_async_decorator_with_custom_name():
    await decorated_async_function_with_custom_name()
