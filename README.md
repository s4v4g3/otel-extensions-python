# otel-extensions-python: OpenTelemetry Extensions for Python
OpenTelemetry Extensions for Python is a collection of helper classes, functions, and decorators to facilitate the use of the 
[OpenTelemetry Python API & SDK packages](https://opentelemetry.io/docs/instrumentation/python/)


## Version Support

Python >= 3.6

## Installation
### pip install

You can install through pip using:

```sh
pip install otel-extensions
```
(you may need to run `pip` with root permission: `sudo pip install otel-extensions`)


### Setuptools

Install via [Setuptools](http://pypi.python.org/pypi/setuptools).

```sh
python setup.py install --user
```
(or `sudo python setup.py install` to install the package for all users)



## Features

### Tracer Provider Initialization

```python
from otel_extensions import init_telemetry_provider, TelemetryOptions

# Provide options for telemetry provider
# Alternatively, any of the following options can be specified through
# environment variables with the equivalent name
options = TelemetryOptions(
    # OTLP receiver endpoint
    OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317/",
    # CA bundle for TLS verification of endpoint (if endpoint scheme is https)
    OTEL_EXPORTER_OTLP_CERTIFICATE="/path/to/ca/bundle",
    # protocol for OTLP receiver (supported: gprc | http/protobuf | custom)
    OTEL_EXPORTER_OTLP_PROTOCOL="grpc",
    # Custom span exporter class name (needed if protocol set to 'custom')
    OTEL_EXPORTER_CUSTOM_SPAN_EXPORTER_TYPE="pkg.ClassName",
    # Name of service
    OTEL_SERVICE_NAME="My Service",
    # Processor type
    #   batch:  use BatchSpanProcessor
    #   simple: use SimpleSpanProcessor
    OTEL_PROCESSOR_TYPE="batch",
    # Optional parent span id.  Will be injected into current context
    TRACEPARENT="001233454656...."
)
# Initialize the global tracer provider
init_telemetry_provider(options)
```

### Instrumentation Decorator
You can use the `@instrumented` decorator to automatically wrap a span around a function or method

```python
from otel_extensions import init_telemetry_provider, instrumented

@instrumented
def foo():
    """Creates a span named 'foo'"""
    bar()

@instrumented(span_name="custom span name")
def bar():
    """Creates a span named 'custom span name'"""
    print("Hello World")

if __name__ == '__main__':
    # init telemetry provider (using options from environment variables)
    init_telemetry_provider()
    foo()

```

### Trace Context helper class
The `TraceContextCarrier` class is useful when propagating context across process or thread boundaries

```python
from otel_extensions import TraceContextCarrier
from threading import Thread


def main_program():
    ...
    # capture current context
    ctx = TraceContextCarrier()
    thread = Thread(thread_func, args=(ctx))
    thread.start()
    ...

def thread_func(ctx: TraceContextCarrier):
    # attach to context stored in ctx
    ctx.attach()
    ...
```

Also, the `TraceContextCarrier` class can attach to context stored in the `TRACEPARENT` environment variable.
Note that this is done automatically when calling the `init_telemetry_provider()` function.

```python
from otel_extensions import TraceContextCarrier

TraceContextCarrier.attach_from_env()
```

`TraceContextCarrier` can also inject the current context into the `TRACEPARENT` environment variable.
This is useful for context propagation when using `Popen` to create a subprocess
```python
from otel_extensions import TraceContextCarrier
from subprocess import Popen

TraceContextCarrier.inject_to_env()
process = Popen(...)
```

### Log messages as events
The `TraceEventLogHandler` class is a `logging.Handler` class that creates events for any log message that occurs in a span.

```python
from otel_extensions import TraceEventLogHandler, init_telemetry_provider, get_tracer
import logging

init_telemetry_provider()

logging.basicConfig()
logging.getLogger(__name__).addHandler(TraceEventLogHandler())

with get_tracer(__name__).start_as_current_span("foo") as span:
    logging.getLogger(__name__).warning("Some log message")
    # 'Some Log message' will be created as an event in 'span',
    # as if you had called
    # span.add_event('Some Log message')

```

