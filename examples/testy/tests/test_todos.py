from calc.todos import Todo, db
from tests.fixtures.todos import app, client, unique


def test_create_and_fetch():
    title = unique("write docs")
    with client() as c:
        created = c.post("/todos", json={"title": title})
        assert created.status_code == 201
        todo_id = created.json["id"]
        assert c.get(f"/todos/{todo_id}").json == {
            "id": todo_id,
            "title": title,
            "done": False,
        }
        assert db.session.get(Todo, todo_id).title == title


def test_listed_after_create():
    with client() as c:
        todo_id = c.post("/todos", json={"title": unique("listed")}).json["id"]
        assert todo_id in {t["id"] for t in c.get("/todos").json}


def test_create_requires_title():
    with client() as c:
        assert c.post("/todos", json={}).status_code == 400


def test_complete():
    with app():
        todo = Todo(title=unique("ship it"))
        db.session.add(todo)
        db.session.commit()
        todo_id = todo.id
    with client() as c:
        assert c.post(f"/todos/{todo_id}/done").json["done"] is True
        assert db.session.get(Todo, todo_id).done is True


def test_missing_is_404():
    with client() as c:
        # SQLite ids start at 1, so 0 never exists however many rows other tests add.
        assert c.get("/todos/0").status_code == 404
        assert c.post("/todos/0/done").status_code == 404
