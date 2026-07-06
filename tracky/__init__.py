from __future__ import annotations

from pathlib import Path

from flask import Flask, abort, flash, redirect, request, session, url_for
from werkzeug.exceptions import HTTPException

from .config import BASE_DIR, Config
from .extensions import db
from .models import User
from .services.bootstrap import bootstrap_from_tvtime, enrich_missing_metadata, run_bootstrap_if_needed
from .services.tmdb import TMDbClient
from .utils import ensure_csrf_token, image_url, join_names, score_range


def create_app(config_object: type[Config] = Config) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object)
    _prepare_sqlite_path(app)

    db.init_app(app)

    from .auth import auth_bp
    from .routes import main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    @app.before_request
    def require_authentication() -> None:
        allowed_endpoints = {"auth.login", "static", "health"}
        if request.endpoint in allowed_endpoints or request.endpoint is None:
            return
        if not session.get("authenticated"):
            next_url = request.full_path if request.query_string else request.path
            return redirect(url_for("auth.login", next=next_url))

    @app.before_request
    def protect_post_requests() -> None:
        if request.method != "POST":
            return
        sent_token = request.form.get("_csrf_token")
        if not sent_token or sent_token != session.get("_csrf_token"):
            abort(400)

    @app.context_processor
    def inject_globals() -> dict[str, object]:
        return {
            "csrf_token": ensure_csrf_token,
            "score_values": score_range(
                app.config["PERSONAL_SCORE_MIN"],
                app.config["PERSONAL_SCORE_MAX"],
            ),
            "score_min": app.config["PERSONAL_SCORE_MIN"],
            "score_max": app.config["PERSONAL_SCORE_MAX"],
            "config_warnings": _configuration_warnings(app),
        }

    app.add_template_filter(image_url, "image_url")
    app.add_template_filter(join_names, "join_names")

    @app.route("/health")
    def health() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, 200

    @app.errorhandler(Exception)
    def handle_error(exc: Exception):
        db.session.rollback()
        if isinstance(exc, HTTPException):
            return (
                app.jinja_env.get_template("errors/error.html").render(
                    status_code=exc.code,
                    title=exc.name,
                    message=exc.description,
                ),
                exc.code,
            )
        app.logger.exception("Unhandled application error")
        return (
            app.jinja_env.get_template("errors/error.html").render(
                status_code=500,
                title="Application error",
                message="Tracky could not complete the request. Check the server logs for details.",
            ),
            500,
        )

    @app.cli.command("bootstrap")
    def bootstrap_command() -> None:
        """Import the bundled TV Time export and enrich it with TMDb metadata."""
        report = bootstrap_from_tvtime()
        client = TMDbClient(
            app.config.get("TMDB_API_KEY"),
            language=app.config.get("TRACKY_TMDB_LANGUAGE", "it-IT"),
        )
        if client.configured:
            report.enriched = enrich_missing_metadata(client)
        else:
            report.add_warning("TMDb enrichment skipped because TMDB_API_KEY is not configured.")
        print(report)

    with app.app_context():
        db.create_all()
        _ensure_configured_user(app)
        if app.config.get("TRACKY_AUTO_BOOTSTRAP", True):
            try:
                report = run_bootstrap_if_needed()
                for warning in report.warnings or []:
                    app.logger.warning(warning)
            except RuntimeError as exc:
                app.logger.warning("Bootstrap skipped: %s", exc)

    return app


def _prepare_sqlite_path(app: Flask) -> None:
    database_uri = str(app.config.get("SQLALCHEMY_DATABASE_URI", ""))
    if database_uri == "sqlite:///:memory:" or not database_uri.startswith("sqlite:///"):
        return
    path_text = database_uri.removeprefix("sqlite:///").split("?", 1)[0]
    database_path = Path(path_text)
    if not database_path.is_absolute():
        database_path = BASE_DIR / database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)


def _ensure_configured_user(app: Flask) -> None:
    username = app.config.get("APP_USERNAME")
    if not username:
        return
    if User.query.filter_by(username=username).first() is None:
        db.session.add(User(username=username))
        db.session.commit()


def _configuration_warnings(app: Flask) -> list[str]:
    warnings: list[str] = []
    if not app.config.get("APP_USERNAME") or not app.config.get("APP_PASSWORD_HASH"):
        warnings.append("Authentication is not configured. Set APP_USERNAME and APP_PASSWORD_HASH.")
    if not app.config.get("TMDB_API_KEY"):
        warnings.append("TMDb integration is disabled until TMDB_API_KEY is configured.")
    if app.config.get("SECRET_KEY") == "change-me-in-production":
        warnings.append("SECRET_KEY is using the development fallback.")
    if app.config["PERSONAL_SCORE_MIN"] > app.config["PERSONAL_SCORE_MAX"]:
        warnings.append("PERSONAL_SCORE_MIN must be lower than or equal to PERSONAL_SCORE_MAX.")
    return warnings
