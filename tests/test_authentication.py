from __future__ import annotations

import json

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


def test_login_exposes_home_screen_icon_metadata(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b'href="/static/manifest.webmanifest"' in response.data
    assert b'href="/static/img/app-icon-180.png"' in response.data
    assert b'name="apple-mobile-web-app-title" content="Tracky"' in response.data


def test_authenticated_pages_expose_home_screen_icon_metadata(client, login):
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b'href="/static/manifest.webmanifest"' in response.data
    assert b'href="/static/img/app-icon-180.png"' in response.data


def test_web_app_manifest_references_png_icons(client):
    response = client.get("/static/manifest.webmanifest")
    assert response.status_code == 200
    manifest = json.loads(response.data)
    assert manifest["name"] == "Tracky"
    assert manifest["display"] == "standalone"
    assert {icon["sizes"] for icon in manifest["icons"]} == {"192x192", "512x512"}


def test_login_ignores_unknown_next_page(client):
    response = client.get("/login?next=/missing-page")
    token = extract_csrf(response.data)
    response = client.post(
        "/login?next=/missing-page",
        data={"_csrf_token": token, "username": "owner", "password": "correct-password"},
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard"


def test_login_preserves_known_next_page(client):
    response = client.get("/login?next=/library?type=movie")
    token = extract_csrf(response.data)
    response = client.post(
        "/login?next=/library?type=movie",
        data={"_csrf_token": token, "username": "owner", "password": "correct-password"},
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/library?type=movie"


def test_unknown_page_opens_login_without_broken_next(client):
    response = client.get("/missing-page")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"


def test_unknown_page_opens_dashboard_when_authenticated(client, login):
    response = client.get("/missing-page")
    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard"
