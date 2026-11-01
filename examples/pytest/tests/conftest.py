"""Fixtures in the style of Flask's testing docs:
https://flask.palletsprojects.com/en/stable/testing/
"""

import pytest
from calc.todos import create_app


@pytest.fixture()
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})

    # other setup can go here

    yield app

    # clean up / reset resources here


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def runner(app):
    return app.test_cli_runner()


@pytest.fixture()
def numbers():
    return [1, 2, 3, 4]
