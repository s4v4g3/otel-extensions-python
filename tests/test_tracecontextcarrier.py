import os

from otel_extensions import TraceContextCarrier
from opentelemetry import context
from contextlib import contextmanager

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

        assert len(context.get_current()) > 0




