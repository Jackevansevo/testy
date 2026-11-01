"""Read-only tests against 1,000 rows this file adds once, when it's imported.

Other tests add rows at the same time, so these only look at their own batch.
"""

from sqlalchemy import func, select

from calc.todos import Todo, db
from tests.fixtures.todos import app, client, unique

BATCH = unique("catalog")
with app():
    db.session.add_all(
        Todo(title=f"{BATCH} #{i}", done=i % 3 == 0) for i in range(1000)
    )
    db.session.commit()


def test_lists_everything():
    with client() as c:
        todos = c.get("/todos").json
    assert sum(t["title"].startswith(BATCH) for t in todos) == 1000


def test_every_third_is_done():
    with app():
        done = select(func.count(Todo.id)).where(
            Todo.title.startswith(BATCH), Todo.done
        )
        assert db.session.scalar(done) == 334


def test_fetch_one():
    with client() as c:
        todo_id = db.session.scalar(
            select(Todo.id).where(Todo.title == f"{BATCH} #499")
        )
        assert c.get(f"/todos/{todo_id}").json["done"] is False
