"""

"""


from setuptools import setup, find_packages  # noqa: H301

NAME = "otel-extensions"
VERSION = "0.0.1"
# To install the library, run the following
#
# python setup.py install
#
# prerequisite: setuptools
# http://pypi.python.org/pypi/setuptools

REQUIRES = [
    "opentelemetry-api",
    "opentelemetry-sdk",
    "pydantic"
]

setup(
    name=NAME,
    version=VERSION,
    description="",
    author="Joe Savage",
    author_email="joe.savage@gmail.com",
    url="https://github.com/s4v4g3/otel-extensions-python",
    keywords=["OpenTelemetry", ""],
    python_requires=">=3.6",
    install_requires=REQUIRES,
    packages=find_packages(exclude=["test", "tests"]),
    long_description="""\
    No description provided
    """,
)
