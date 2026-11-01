"""A small todo API: Flask-SQLAlchemy models and Flask routes, put together by create_app."""

from flask import Blueprint, Flask, abort, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


class Todo(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    done: Mapped[bool] = mapped_column(default=False)

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "done": self.done}


bp = Blueprint("todos", __name__)


@bp.get("/todos")
def list_todos():
    return [t.to_dict() for t in db.session.scalars(select(Todo).order_by(Todo.id))]


@bp.post("/todos")
def create_todo():
    title = (request.get_json(silent=True) or {}).get("title")
    if not title:
        abort(400)
    todo = Todo(title=title)
    db.session.add(todo)
    db.session.commit()
    return todo.to_dict(), 201


@bp.get("/todos/<int:todo_id>")
def get_todo(todo_id: int):
    return db.get_or_404(Todo, todo_id).to_dict()


@bp.post("/todos/<int:todo_id>/done")
def complete_todo(todo_id: int):
    todo = db.get_or_404(Todo, todo_id)
    todo.done = True
    db.session.commit()
    return todo.to_dict()


def create_app(config: dict | None = None) -> Flask:
    """By default the database is in memory and shared by every connection in the
    process (SQLite's memdb VFS), so concurrent threads each get a connection."""
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///file:/todos?vfs=memdb&uri=true"
    app.config.update(config or {})
    db.init_app(app)
    with app.app_context():
        db.create_all()
    app.register_blueprint(bp)
    return app
