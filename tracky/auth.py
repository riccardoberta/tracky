from __future__ import annotations

from urllib.parse import urlparse

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.exceptions import MethodNotAllowed, NotFound
from werkzeug.routing import RequestRedirect
from werkzeug.security import check_password_hash


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("authenticated"):
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        configured_username = current_app.config.get("APP_USERNAME")
        password_hash = current_app.config.get("APP_PASSWORD_HASH")
        if not configured_username or not password_hash:
            flash("Tracky authentication is not configured yet.", "error")
        elif username == configured_username and check_password_hash(password_hash, password):
            session.clear()
            session["authenticated"] = True
            session["username"] = username
            target = request.args.get("next") or url_for("main.dashboard")
            if not _is_safe_next(target):
                target = url_for("main.dashboard")
            return redirect(target)
        else:
            flash("Invalid username or password.", "error")

    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("auth.login"))


def _is_safe_next(target: str) -> bool:
    parsed = urlparse(target)
    if parsed.netloc or parsed.scheme or not parsed.path.startswith("/") or parsed.path.startswith("//"):
        return False
    endpoint = _match_get_endpoint(parsed.path)
    return endpoint is not None and endpoint.startswith("main.")


def _match_get_endpoint(path: str) -> str | None:
    try:
        endpoint, _ = current_app.url_map.bind("").match(path, method="GET")
    except RequestRedirect as exc:
        redirected_path = urlparse(exc.new_url).path
        if not redirected_path or redirected_path == path:
            return None
        return _match_get_endpoint(redirected_path)
    except (MethodNotAllowed, NotFound):
        return None
    return endpoint
