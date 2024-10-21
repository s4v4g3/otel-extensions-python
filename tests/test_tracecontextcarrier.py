import os
from contextlib import contextmanager

from opentelemetry import context

from otel_extensions import (
    TelemetryOptions,
    TraceContextCarrier,
    inject_context_to_env,
    instrumented,
)


@contextmanager
def temporary_environment_variable_setter(var, val):
    prev_val = os.environ.get(var)
    if val is not None:
        os.environ[var] = val
    else:
        if prev_val is not None:
            del os.environ[var]
    try:
        yield
    finally:
        if prev_val is None:
            if val is not None and var in os.environ:
                del os.environ[var]
        else:
            os.environ[var] = prev_val


def test_tracecontextcarrier():
    @instrumented
    def test_fn():
        assert len(context.get_current()) > 0
        orig_ctx = TraceContextCarrier()
        with temporary_environment_variable_setter("TRACEPARENT", None):
            empty_ctx = TraceContextCarrier.attach_from_env()
            assert len(context.get_current()) == 0
            with empty_ctx:
                assert len(context.get_current()) == 0

                with orig_ctx:
                    assert len(context.get_current()) > 0
                assert len(context.get_current()) == 0

                orig_ctx.attach()
                assert len(context.get_current()) > 0
                new_ctx = TraceContextCarrier()
                assert orig_ctx == new_ctx
                orig_ctx.detach()
                assert len(context.get_current()) == 0
                TraceContextCarrier.inject_to_env()
                assert "TRACEPARENT" not in os.environ
                orig_ctx.detach()

            assert len(context.get_current()) > 0

        with temporary_environment_variable_setter("TRACEPARENT", "invalid"):
            TraceContextCarrier.inject_to_env()
            assert os.environ["TRACEPARENT"].startswith("00-")

    test_fn()


def test_tracecontextcarrier_attach_from_options():
    @instrumented
    def test_fn():
        orig_ctx_len = len(context.get_current())
        assert orig_ctx_len > 0
        orig_ctx = TraceContextCarrier()
        opts = TelemetryOptions()
        _ = TraceContextCarrier.attach_from_options(opts)
        assert len(context.get_current()) == 0
        opts = TelemetryOptions(TRACEPARENT=orig_ctx.carrier["traceparent"])
        _ = TraceContextCarrier.attach_from_options(opts)
        assert len(context.get_current()) == orig_ctx_len

    test_fn()


def test_context_injection():
    @instrumented
    def test_fn():
        @inject_context_to_env
        def wrapped():
            assert os.environ["TRACEPARENT"].startswith("00-")

    with temporary_environment_variable_setter("TRACEPARENT", None):
        test_fn()
