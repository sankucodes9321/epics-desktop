from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter

current = ContextVar("timings", default=None)


@contextmanager
def measure(name):
    values = current.get()
    start = perf_counter()
    try:
        yield
    finally:
        if values is not None:
            elapsed = perf_counter() - start
            values[name] = values.get(name, 0.) + elapsed
            if name == "antispoof":
                values["detect"] = values.get("detect", 0.) - elapsed


@contextmanager
def collect():
    values = {}
    token = current.set(values)
    try:
        yield values
    finally:
        current.reset(token)
