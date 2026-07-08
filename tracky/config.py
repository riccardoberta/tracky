from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent


def _bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def _default_database_url() -> str:
    if _bool_env("VERCEL", False):
        return "sqlite:////tmp/tracky.sqlite3"
    return f"sqlite:///{BASE_DIR / 'instance' / 'tracky.sqlite3'}"


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url.removeprefix("postgres://")
    if database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    if not database_url.startswith("sqlite:///") or database_url.startswith("sqlite:////"):
        return database_url
    path_text = database_url.removeprefix("sqlite:///").split("?", 1)[0]
    if path_text == ":memory:":
        return database_url
    query_text = ""
    if "?" in database_url:
        query_text = "?" + database_url.split("?", 1)[1]
    return f"sqlite:///{BASE_DIR / path_text}{query_text}"


def _database_url() -> str:
    configured_url = os.getenv("DATABASE_URL")
    if not configured_url:
        return _default_database_url()
    return normalize_database_url(configured_url)


def _engine_options(database_url: str) -> dict[str, object]:
    if not database_url.startswith("postgresql"):
        return {}
    return {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 1,
        "max_overflow": 2,
        "pool_timeout": 10,
        "connect_args": {"connect_timeout": 5, "prepare_threshold": None},
    }


def create_schema_on_startup(database_url: str) -> bool:
    configured_value = os.getenv("TRACKY_CREATE_SCHEMA_ON_STARTUP")
    if configured_value is not None:
        return configured_value.strip().lower() in {"1", "true", "yes", "on"}
    return database_url.startswith("sqlite:")


class Config:
    load_dotenv(BASE_DIR / ".env")

    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
    APP_USERNAME = os.getenv("APP_USERNAME")
    APP_PASSWORD_HASH = os.getenv("APP_PASSWORD_HASH")
    TMDB_API_KEY = os.getenv("TMDB_API_KEY")

    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options(SQLALCHEMY_DATABASE_URI)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TRACKY_CREATE_SCHEMA_ON_STARTUP = create_schema_on_startup(SQLALCHEMY_DATABASE_URI)
    DATABASE_URL_CONFIGURED = bool(os.getenv("DATABASE_URL"))
    RUNNING_ON_VERCEL = _bool_env("VERCEL", False)

    PERSONAL_SCORE_MIN = _int_env("PERSONAL_SCORE_MIN", 1)
    PERSONAL_SCORE_MAX = _int_env("PERSONAL_SCORE_MAX", 10)

    TRACKY_TMDB_LANGUAGE = os.getenv("TRACKY_TMDB_LANGUAGE", "it-IT")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
