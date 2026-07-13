from __future__ import annotations

import csv
from datetime import date, datetime
from io import StringIO
from typing import Any

from sqlalchemy import func, select

from ..extensions import db
from ..models import (
    Episode,
    Genre,
    MediaItem,
    MediaList,
    MediaListItem,
    MediaPerson,
    Person,
    Setting,
    User,
    WatchEvent,
    media_genres,
)
from ..utils import utc_now


LETTERBOXD_COLUMNS = [
    "tmdbID",
    "imdbID",
    "Title",
    "Year",
    "Directors",
    "Rating",
    "WatchedDate",
    "Rewatch",
    "Tags",
    "Review",
]


def build_export_payload(exported_at: datetime | None = None) -> dict[str, Any]:
    exported_at = exported_at or utc_now()
    users = User.query.order_by(User.id.asc()).all()
    genres = Genre.query.order_by(Genre.id.asc()).all()
    people = Person.query.order_by(Person.id.asc()).all()
    media_items = MediaItem.query.order_by(MediaItem.id.asc()).all()
    media_people = MediaPerson.query.order_by(
        MediaPerson.media_item_id.asc(),
        MediaPerson.sort_order.asc(),
    ).all()
    episodes = Episode.query.order_by(
        Episode.media_item_id.asc(),
        Episode.season_number.asc(),
        Episode.episode_number.asc(),
    ).all()
    watch_events = WatchEvent.query.order_by(
        WatchEvent.watched_at.asc(),
        WatchEvent.id.asc(),
    ).all()
    media_lists = MediaList.query.order_by(MediaList.id.asc()).all()
    media_list_items = MediaListItem.query.order_by(
        MediaListItem.media_list_id.asc(),
        MediaListItem.sort_order.asc(),
    ).all()
    settings = Setting.query.order_by(Setting.key.asc()).all()
    genre_links = db.session.execute(
        select(media_genres.c.media_item_id, media_genres.c.genre_id).order_by(
            media_genres.c.media_item_id.asc(),
            media_genres.c.genre_id.asc(),
        )
    ).all()

    return {
        "format": "tracky.export.v1",
        "exported_at": _serialize_datetime(exported_at),
        "counts": {
            "users": len(users),
            "genres": len(genres),
            "people": len(people),
            "media_items": len(media_items),
            "media_genres": len(genre_links),
            "media_people": len(media_people),
            "episodes": len(episodes),
            "watch_events": len(watch_events),
            "media_lists": len(media_lists),
            "media_list_items": len(media_list_items),
            "settings": len(settings),
        },
        "users": [_serialize_user(user) for user in users],
        "genres": [_serialize_genre(genre) for genre in genres],
        "people": [_serialize_person(person) for person in people],
        "media_items": [_serialize_media_item(item) for item in media_items],
        "media_genres": [
            {"media_item_id": media_item_id, "genre_id": genre_id}
            for media_item_id, genre_id in genre_links
        ],
        "media_people": [_serialize_media_person(link) for link in media_people],
        "episodes": [_serialize_episode(episode) for episode in episodes],
        "watch_events": [_serialize_watch_event(event) for event in watch_events],
        "media_lists": [_serialize_media_list(media_list) for media_list in media_lists],
        "media_list_items": [_serialize_media_list_item(item) for item in media_list_items],
        "settings": [_serialize_setting(setting) for setting in settings],
    }


def build_letterboxd_csv(personal_score_max: int) -> str:
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=LETTERBOXD_COLUMNS,
        lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL,
        escapechar="\\",
        doublequote=False,
    )
    writer.writeheader()
    movies = MediaItem.query.filter_by(media_type="movie").order_by(
        func.lower(MediaItem.italian_title).asc(),
        MediaItem.id.asc(),
    ).all()
    for item in movies:
        writer.writerow(_serialize_letterboxd_movie(item, personal_score_max))
    return output.getvalue()


def _serialize_letterboxd_movie(item: MediaItem, personal_score_max: int) -> dict[str, str]:
    return {
        "tmdbID": str(item.tmdb_id or ""),
        "imdbID": item.imdb_id or "",
        "Title": item.original_title or item.italian_title,
        "Year": str(item.year or ""),
        "Directors": ", ".join(person.name for person in item.primary_people),
        "Rating": _letterboxd_rating(item.personal_rating, personal_score_max),
        "WatchedDate": _serialize_date(item.watched_date) or "",
        "Rewatch": "",
        "Tags": "",
        "Review": item.personal_notes or "",
    }


def _letterboxd_rating(value: float | None, personal_score_max: int) -> str:
    if value is None or personal_score_max <= 0:
        return ""
    normalized = max(0.5, min(5.0, value / personal_score_max * 5))
    rounded = int(normalized * 2 + 0.5) / 2
    return f"{rounded:g}"


def _serialize_user(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "created_at": _serialize_datetime(user.created_at),
        "updated_at": _serialize_datetime(user.updated_at),
    }


def _serialize_genre(genre: Genre) -> dict[str, Any]:
    return {
        "id": genre.id,
        "name": genre.name,
    }


def _serialize_person(person: Person) -> dict[str, Any]:
    return {
        "id": person.id,
        "tmdb_id": person.tmdb_id,
        "name": person.name,
    }


def _serialize_media_item(item: MediaItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "media_type": item.media_type,
        "tmdb_id": item.tmdb_id,
        "tvdb_id": item.tvdb_id,
        "imdb_id": item.imdb_id,
        "italian_title": item.italian_title,
        "original_title": item.original_title,
        "overview": item.overview,
        "release_date": _serialize_date(item.release_date),
        "first_air_date": _serialize_date(item.first_air_date),
        "tmdb_rating": item.tmdb_rating,
        "tmdb_vote_count": item.tmdb_vote_count,
        "poster_path": item.poster_path,
        "backdrop_path": item.backdrop_path,
        "watched_date": _serialize_date(item.watched_date),
        "favorite": item.favorite,
        "personal_rating": item.personal_rating,
        "personal_notes": item.personal_notes,
        "source": item.source,
        "created_at": _serialize_datetime(item.created_at),
        "updated_at": _serialize_datetime(item.updated_at),
    }


def _serialize_media_person(link: MediaPerson) -> dict[str, Any]:
    return {
        "id": link.id,
        "media_item_id": link.media_item_id,
        "person_id": link.person_id,
        "role": link.role,
        "sort_order": link.sort_order,
    }


def _serialize_episode(episode: Episode) -> dict[str, Any]:
    return {
        "id": episode.id,
        "media_item_id": episode.media_item_id,
        "season_number": episode.season_number,
        "episode_number": episode.episode_number,
        "title": episode.title,
        "tvdb_id": episode.tvdb_id,
        "imdb_id": episode.imdb_id,
        "is_special": episode.is_special,
        "is_watched": episode.is_watched,
        "watched_at": _serialize_datetime(episode.watched_at),
        "watched_count": episode.watched_count,
        "rewatch_count": episode.rewatch_count,
        "created_at": _serialize_datetime(episode.created_at),
        "updated_at": _serialize_datetime(episode.updated_at),
    }


def _serialize_watch_event(event: WatchEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "media_item_id": event.media_item_id,
        "episode_id": event.episode_id,
        "watched_at": _serialize_datetime(event.watched_at),
        "source": event.source,
        "watch_count": event.watch_count,
        "created_at": _serialize_datetime(event.created_at),
        "updated_at": _serialize_datetime(event.updated_at),
    }


def _serialize_media_list(media_list: MediaList) -> dict[str, Any]:
    return {
        "id": media_list.id,
        "name": media_list.name,
        "description": media_list.description,
        "is_public": media_list.is_public,
        "source_created_at": _serialize_datetime(media_list.source_created_at),
        "created_at": _serialize_datetime(media_list.created_at),
        "updated_at": _serialize_datetime(media_list.updated_at),
    }


def _serialize_media_list_item(item: MediaListItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "media_list_id": item.media_list_id,
        "media_item_id": item.media_item_id,
        "sort_order": item.sort_order,
    }


def _serialize_setting(setting: Setting) -> dict[str, Any]:
    return {
        "key": setting.key,
        "value": setting.value,
        "updated_at": _serialize_datetime(setting.updated_at),
    }


def _serialize_date(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _serialize_datetime(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") + "Z" if value else None
