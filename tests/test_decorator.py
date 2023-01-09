from otel_extensions import instrumented
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan
from collections.abc import Sequence
import pytest

SPAN_ATTRS = {
    "foo": "bar",
    "intKey": 5,
    "boolKey": True,
    "floatKey": 5.8,
    "strListKey": ["foo", "bar"],
    "boolListKey": [True, False, True],
    "intListKey": [1, 2, 3, 4],
    "floatListKey": [2.3, 6.7],
}


def check_span_attributes(span: ReadableSpan):
    assert len(span.attributes) == len(SPAN_ATTRS)
    for key in span.attributes:
        value = span.attributes[key]
        expected = SPAN_ATTRS[key]
        if isinstance(value, Sequence):
            assert len(value) == len(expected)
            for i in range(0, len(value)):
                assert value[i] == expected[i]
        else:
            assert SPAN_ATTRS[key] == span.attributes[key]


@instrumented
def decorated_function():
    span: ReadableSpan = trace.get_current_span()  # noqa
    assert span.name == "decorated_function"


@instrumented(span_name="overridden span name")
def decorated_function_with_custom_name():
    span: ReadableSpan = trace.get_current_span()  # noqa
    assert span.name == "overridden span name"


@instrumented(span_attributes=SPAN_ATTRS)
def decorated_function_with_span_attrs():
    span: ReadableSpan = trace.get_current_span()  # noqa
    check_span_attributes(span)
    assert span.name == "decorated_function_with_span_attrs"


@instrumented
async def decorated_async_function():
    span: ReadableSpan = trace.get_current_span()  # noqa
    assert span.name == "decorated_async_function"


@instrumented(span_name="overridden span name")
async def decorated_async_function_with_custom_name():
    span: ReadableSpan = trace.get_current_span()  # noqa
    assert span.name == "overridden span name"


@instrumented(span_attributes=SPAN_ATTRS)
async def decorated_async_function_with_span_attrs():
    span: ReadableSpan = trace.get_current_span()  # noqa
    check_span_attributes(span)
    assert span.name == "decorated_async_function_with_span_attrs"


def test_decorator_with_default_name():
    decorated_function()


def test_decorator_with_custom_name():
    decorated_function_with_custom_name()


def test_decorator_with_span_attributes():
    decorated_function_with_span_attrs()


@pytest.mark.asyncio
async def test_async_decorator_with_default_name():
    await decorated_async_function()


@pytest.mark.asyncio
async def test_async_decorator_with_custom_name():
    await decorated_async_function_with_custom_name()


@pytest.mark.asyncio
async def test_async_decorator_with_span_attributes():
    await decorated_async_function_with_span_attrs()
