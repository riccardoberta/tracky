from __future__ import annotations

from tests.conftest import extract_csrf


def test_dashboard_requires_authentication(client):
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_invalid_login_is_rejected(client):
    response = client.get("/login")
    token = extract_csrf(response.data)
    response = client.post(
        "/login",
        data={"_csrf_token": token, "username": "owner", "password": "wrong"},
        follow_redirects=True,
    )
    assert b"Invalid username or password." in response.data


def test_valid_login_opens_dashboard(client):
    response = client.get("/login")
    token = extract_csrf(response.data)
    response = client.post(
        "/login",
        data={"_csrf_token": token, "username": "owner", "password": "correct-password"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Dashboard" in response.data
