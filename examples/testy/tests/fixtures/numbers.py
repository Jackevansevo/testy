import contextlib


@contextlib.contextmanager
def numbers():
    yield [1, 2, 3, 4]
