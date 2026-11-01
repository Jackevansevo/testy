"""Fixtures for the todo app.

One app and one database are shared by the whole run, created when this module
is first imported. Tests run in parallel against it, so each test makes its own
rows and never assumes the database is empty.
"""

import contextlib
import uuid

from calc.todos import create_app

# Test config lives here, in one place, and is applied before the database is set up.
_app = create_app({"TESTING": True})


@contextlib.contextmanager
def app():
    """The shared app with an app context pushed, so `db.session` works."""
    with _app.app_context():
        # per-test setup goes here
        yield _app
        # per-test cleanup goes here


@contextlib.contextmanager
def client():
    with app() as a:
        yield a.test_client()


def unique(name: str) -> str:
    """A title no other test will use."""
    return f"{name} {uuid.uuid4().hex[:8]}"
