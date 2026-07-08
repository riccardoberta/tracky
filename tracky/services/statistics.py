from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func

from ..extensions import db
from ..models import Genre, MediaItem, date_month_expression, date_year_expression, media_genres


@dataclass(frozen=True)
class BarDatum:
    label: str
    value: int | float


def _rows_to_bar_data(rows: list[tuple[Any, Any]]) -> list[BarDatum]:
    return [BarDatum(str(label), value or 0) for label, value in rows if label is not None]


def build_statistics() -> dict[str, Any]:
    total_movies = MediaItem.query.filter(
        MediaItem.media_type == "movie",
        MediaItem.watched_date.is_not(None),
    ).count()
    total_shows = MediaItem.query.filter(
        MediaItem.media_type == "tv",
        MediaItem.watched_date.is_not(None),
    ).count()
    favorites_count = MediaItem.query.filter_by(favorite=True).count()

    avg_personal = db.session.query(func.avg(MediaItem.personal_rating)).filter(
        MediaItem.personal_rating.is_not(None)
    ).scalar()
    avg_tmdb = db.session.query(func.avg(MediaItem.tmdb_rating)).filter(MediaItem.tmdb_rating.is_not(None)).scalar()

    watched_year = date_year_expression(MediaItem.watched_date)
    watched_month = date_month_expression(MediaItem.watched_date)

    movies_by_year = db.session.query(
        watched_year,
        func.count(MediaItem.id),
    ).filter(MediaItem.media_type == "movie", MediaItem.watched_date.is_not(None)).group_by(
        watched_year
    ).order_by(
        watched_year
    ).all()

    shows_by_year = db.session.query(
        watched_year,
        func.count(MediaItem.id),
    ).filter(MediaItem.media_type == "tv", MediaItem.watched_date.is_not(None)).group_by(
        watched_year
    ).order_by(
        watched_year
    ).all()

    genre_counts = db.session.query(Genre.name, func.count(MediaItem.id)).join(
        media_genres,
        Genre.id == media_genres.c.genre_id,
    ).join(
        MediaItem,
        MediaItem.id == media_genres.c.media_item_id,
    ).group_by(Genre.id).order_by(func.count(MediaItem.id).desc(), Genre.name.asc()).limit(10).all()

    favorite_genres = db.session.query(Genre.name, func.count(MediaItem.id)).join(
        media_genres,
        Genre.id == media_genres.c.genre_id,
    ).join(
        MediaItem,
        MediaItem.id == media_genres.c.media_item_id,
    ).filter(MediaItem.favorite.is_(True)).group_by(Genre.id).order_by(
        func.count(MediaItem.id).desc(),
        Genre.name.asc(),
    ).limit(10).all()

    activity_by_month = db.session.query(
        watched_month,
        func.count(MediaItem.id),
    ).filter(MediaItem.watched_date.is_not(None)).group_by(watched_month).order_by(
        watched_month
    ).all()

    activity_by_year = db.session.query(
        watched_year,
        func.count(MediaItem.id),
    ).filter(MediaItem.watched_date.is_not(None)).group_by(watched_year).order_by(
        watched_year
    ).all()

    return {
        "total_movies": total_movies,
        "total_shows": total_shows,
        "favorites_count": favorites_count,
        "average_personal_rating": round(float(avg_personal), 2) if avg_personal else None,
        "average_tmdb_rating": round(float(avg_tmdb), 2) if avg_tmdb else None,
        "movies_by_year": _rows_to_bar_data(movies_by_year),
        "shows_by_year": _rows_to_bar_data(shows_by_year),
        "most_watched_genres": _rows_to_bar_data(genre_counts),
        "favorite_genres": _rows_to_bar_data(favorite_genres),
        "activity_by_month": _rows_to_bar_data(activity_by_month[-18:]),
        "activity_by_year": _rows_to_bar_data(activity_by_year),
    }
