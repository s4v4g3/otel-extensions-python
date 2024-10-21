import os
from collections.abc import Sequence
from typing import cast

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import Span

from otel_extensions import instrumented

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


@pytest.mark.anyio
async def test_async_decorator_with_default_name():
    await decorated_async_function()


@pytest.mark.anyio
async def test_async_decorator_with_custom_name():
    await decorated_async_function_with_custom_name()


@pytest.mark.anyio
async def test_async_decorator_with_span_attributes():
    await decorated_async_function_with_span_attrs()


@pytest.fixture
def otel_process_modules(request):
    if request.param is not None:
        os.environ["OTEL_PROCESS_MODULES"] = request.param
    yield request.param
    os.environ.pop("OTEL_PROCESS_MODULES", None)


@pytest.mark.parametrize(
    "otel_process_modules", ["foo", "", None, "test_decorator"], indirect=True
)
def test_decorator_with_module_filter(otel_process_modules):
    """If the OTEL_PROCESS_MODULES environment variable is set, the decorator should only
    create a span if the module name for the wrapped function matches the filter.
    """

    @instrumented(span_name="decorated_function_with_module_filter")
    def decorated_local_function():
        span: Span = trace.get_current_span()
        if otel_process_modules == "foo":
            if span.is_recording():
                assert (
                    cast(ReadableSpan, span).name
                    == "test_decorator_with_module_filter[foo] (call)"
                )
        else:
            assert span.is_recording()
            assert (
                cast(ReadableSpan, span).name == "decorated_function_with_module_filter"
            )

    decorated_local_function()
