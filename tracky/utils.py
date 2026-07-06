from __future__ import annotations

from datetime import UTC, date, datetime
from secrets import token_urlsafe
from typing import Any

from flask import session


TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip().replace("Z", "+00:00")
    for pattern in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(normalized, pattern)
            return parsed.replace(tzinfo=None)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(normalized).replace(tzinfo=None)
    except ValueError:
        return None


def parse_date(value: str | None) -> date | None:
    parsed = parse_datetime(value)
    if parsed:
        return parsed.date()
    return None


def parse_date_field(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def image_url(path: str | None, size: str = "w500") -> str | None:
    if not path:
        return None
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"{TMDB_IMAGE_BASE}/{size}{path}"


def split_names(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def join_names(values: list[Any]) -> str:
    return ", ".join(getattr(value, "name", str(value)) for value in values)


def score_range(min_score: int, max_score: int) -> list[int]:
    return list(range(min_score, max_score + 1))


def ensure_csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def safe_int(value: str | None) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def safe_float(value: str | None) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except ValueError:
        return None
