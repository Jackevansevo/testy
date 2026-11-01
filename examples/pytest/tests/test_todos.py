"""Each test gets a fresh app with its own empty in-memory database (see conftest.py),
so unlike the testy example these can assume the database starts empty."""

from calc.todos import Todo, db
from sqlalchemy import func, select


def test_starts_empty(client):
    assert client.get("/todos").json == []


def test_create_and_fetch(app, client):
    created = client.post("/todos", json={"title": "write docs"})
    assert created.status_code == 201
    todo_id = created.json["id"]
    assert client.get(f"/todos/{todo_id}").json == {
        "id": todo_id,
        "title": "write docs",
        "done": False,
    }
    with app.app_context():
        assert db.session.get(Todo, todo_id).title == "write docs"


def test_create_requires_title(app, client):
    assert client.post("/todos", json={}).status_code == 400
    with app.app_context():
        assert db.session.scalar(select(func.count(Todo.id))) == 0


def test_complete(app, client):
    with app.app_context():
        todo = Todo(title="ship it")
        db.session.add(todo)
        db.session.commit()
        todo_id = todo.id
    assert client.post(f"/todos/{todo_id}/done").json["done"] is True
    with app.app_context():
        assert db.session.get(Todo, todo_id).done is True


def test_missing_is_404(client):
    assert client.get("/todos/1").status_code == 404
    assert client.post("/todos/1/done").status_code == 404
