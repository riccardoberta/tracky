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


class Config:
    load_dotenv(BASE_DIR / ".env")

    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
    APP_USERNAME = os.getenv("APP_USERNAME")
    APP_PASSWORD_HASH = os.getenv("APP_PASSWORD_HASH")
    TMDB_API_KEY = os.getenv("TMDB_API_KEY")

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or _default_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    PERSONAL_SCORE_MIN = _int_env("PERSONAL_SCORE_MIN", 1)
    PERSONAL_SCORE_MAX = _int_env("PERSONAL_SCORE_MAX", 10)

    TRACKY_AUTO_BOOTSTRAP = _bool_env("TRACKY_AUTO_BOOTSTRAP", True)
    TRACKY_ENRICH_ON_STARTUP = _bool_env("TRACKY_ENRICH_ON_STARTUP", not _bool_env("VERCEL", False))
    TRACKY_USE_SEED_DATABASE = _bool_env("TRACKY_USE_SEED_DATABASE", _bool_env("VERCEL", False))
    TRACKY_SEED_DATABASE_PATH = os.getenv("TRACKY_SEED_DATABASE_PATH", str(BASE_DIR / "data" / "tracky.seed.sqlite3"))
    TRACKY_EXPORT_DIR = os.getenv("TRACKY_EXPORT_DIR", str(BASE_DIR / "tvtime-export-2026-07-03"))
    TRACKY_TMDB_LANGUAGE = os.getenv("TRACKY_TMDB_LANGUAGE", "it-IT")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
