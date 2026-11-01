"""Read-only tests against 1,000 rows, seeded once for this module."""

import pytest
from calc.todos import Todo, create_app, db
from sqlalchemy import func, select


@pytest.fixture(scope="module")
def catalog():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    with app.app_context():
        db.session.add_all(
            Todo(title=f"item {i}", done=i % 3 == 0) for i in range(1000)
        )
        db.session.commit()
    return app


def test_lists_everything(catalog):
    assert len(catalog.test_client().get("/todos").json) == 1000


def test_every_third_is_done(catalog):
    with catalog.app_context():
        assert db.session.scalar(select(func.count(Todo.id)).where(Todo.done)) == 334


def test_fetch_one(catalog):
    assert catalog.test_client().get("/todos/500").json["title"] == "item 499"
