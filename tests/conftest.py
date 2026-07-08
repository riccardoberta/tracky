from __future__ import annotations

import re
from collections.abc import Iterator

import pytest
from werkzeug.security import generate_password_hash

from tracky import create_app
from tracky.config import Config
from tracky.extensions import db


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret"
    APP_USERNAME = "owner"
    APP_PASSWORD_HASH = generate_password_hash("correct-password")
    TMDB_API_KEY = None
    PERSONAL_SCORE_MIN = 1
    PERSONAL_SCORE_MAX = 10


@pytest.fixture()
def app(tmp_path):
    class RuntimeConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'tracky-test.sqlite3'}"

    app = create_app(RuntimeConfig)
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def extract_csrf(html: bytes) -> str:
    match = re.search(rb'name="_csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1).decode()


@pytest.fixture()
def login(client) -> Iterator[None]:
    response = client.get("/login")
    token = extract_csrf(response.data)
    client.post(
        "/login",
        data={
            "_csrf_token": token,
            "username": "owner",
            "password": "correct-password",
        },
        follow_redirects=True,
    )
    yield
