from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import current_app
from sqlalchemy import func, or_

from ..extensions import db
from ..models import (
    Episode,
    MediaPerson,
    MediaItem,
    MediaList,
    MediaListItem,
    Setting,
    WatchEvent,
    get_or_create_person,
)
from ..utils import parse_date, parse_date_field, parse_datetime, utc_now
from .tmdb import TMDbClient, TMDbError


@dataclass
class BootstrapReport:
    movies: int = 0
    shows: int = 0
    episodes: int = 0
    watch_events: int = 0
    lists: int = 0
    enriched: int = 0
    warnings: list[str] | None = None

    def add_warning(self, message: str) -> None:
        if self.warnings is None:
            self.warnings = []
        self.warnings.append(message)


def run_bootstrap_if_needed() -> BootstrapReport:
    report = BootstrapReport()
    if not current_app.config.get("TRACKY_AUTO_BOOTSTRAP", True):
        return report

    with current_app.app_context():
        if Setting.get("tvtime_bootstrap_imported") != "true":
            report = bootstrap_from_tvtime()
        else:
            report.add_warning("TV Time bootstrap already completed; skipped local import.")

        if not current_app.config.get("TRACKY_ENRICH_ON_STARTUP", True):
            report.add_warning("TMDb startup enrichment skipped by TRACKY_ENRICH_ON_STARTUP.")
        elif Setting.get("tmdb_enrichment_completed") != "true":
            client = TMDbClient(
                current_app.config.get("TMDB_API_KEY"),
                language=current_app.config.get("TRACKY_TMDB_LANGUAGE", "it-IT"),
            )
            if client.configured:
                report.enriched += enrich_missing_metadata(client)
                Setting.set("tmdb_enrichment_completed", "true")
                Setting.set("tmdb_enrichment_completed_at", utc_now().isoformat())
                db.session.commit()
            else:
                report.add_warning("TMDb enrichment skipped because TMDB_API_KEY is not configured.")
    return report


def bootstrap_from_tvtime(export_dir: str | None = None) -> BootstrapReport:
    report = BootstrapReport()
    directory = Path(export_dir or current_app.config["TRACKY_EXPORT_DIR"])
    movies_path = _find_export_file(directory, "tvtime-movies*.json")
    series_path = _find_export_file(directory, "tvtime-series*.json")
    lists_path = _find_export_file(directory, "tvtime-lists*.json")

    if movies_path is None and series_path is None:
        report.add_warning(f"No TV Time export files were found in {directory}.")
        return report

    if movies_path:
        report.movies = _import_movies(_load_json_list(movies_path), report)
    if series_path:
        show_count, episode_count, event_count = _import_series(_load_json_list(series_path), report)
        report.shows = show_count
        report.episodes = episode_count
        report.watch_events += event_count
    if lists_path:
        report.lists = _import_lists(_load_json_list(lists_path), report)

    Setting.set("tvtime_bootstrap_imported", "true")
    Setting.set("tvtime_bootstrap_completed_at", utc_now().isoformat())
    db.session.commit()
    return report


def enrich_missing_metadata(client: TMDbClient) -> int:
    enriched = 0
    items = MediaItem.query.filter(
        MediaItem.media_type.in_(("movie", "tv")),
        or_(MediaItem.tmdb_id.is_(None), MediaItem.overview.is_(None), MediaItem.poster_path.is_(None)),
    ).order_by(MediaItem.id.asc()).all()

    for item in items:
        try:
            tmdb_id = item.tmdb_id
            if tmdb_id is None and item.imdb_id:
                tmdb_id = client.find_by_imdb(item.imdb_id, item.media_type)
            if tmdb_id is None:
                tmdb_id = client.best_match(item.original_title or item.italian_title, item.year, item.media_type)
            if tmdb_id is None:
                continue
            details = client.details(tmdb_id, item.media_type)
            apply_tmdb_details(item, details)
            enriched += 1
            db.session.commit()
        except TMDbError as exc:
            current_app.logger.warning("TMDb enrichment failed for %s: %s", item.title, exc)
            db.session.rollback()
            continue
    return enriched


def apply_tmdb_details(item: MediaItem, details: dict[str, Any]) -> None:
    item.tmdb_id = details.get("tmdb_id") or item.tmdb_id
    item.imdb_id = details.get("imdb_id") or item.imdb_id
    item.italian_title = details.get("italian_title") or item.italian_title
    item.original_title = details.get("original_title") or item.original_title
    item.overview = details.get("overview") or item.overview
    item.tmdb_rating = details.get("tmdb_rating")
    item.tmdb_vote_count = details.get("tmdb_vote_count")
    item.poster_path = details.get("poster_path") or item.poster_path
    item.backdrop_path = details.get("backdrop_path") or item.backdrop_path
    date_value = parse_date_field(details.get("date"))
    if item.media_type == "movie":
        item.release_date = date_value or item.release_date
    else:
        item.first_air_date = date_value or item.first_air_date
    item.set_genres(details.get("genres") or [])

    primary_role = "director" if item.media_type == "movie" else "creator"
    _set_people_from_tmdb(item, primary_role, details.get("primary_people") or [])
    _set_people_from_tmdb(item, "cast", details.get("cast") or [])


def _set_people_from_tmdb(item: MediaItem, role: str, people: list[dict[str, Any]]) -> None:
    for link in list(item.people_links):
        if link.role == role:
            item.people_links.remove(link)
            db.session.delete(link)
    db.session.flush()
    for index, person_data in enumerate(people):
        person = get_or_create_person(person_data["name"], person_data.get("tmdb_id"))
        item.people_links.append(
            MediaPerson(
                person=person,
                role=role,
                sort_order=index,
            )
        )


def _find_export_file(directory: Path, pattern: str) -> Path | None:
    if not directory.exists():
        return None
    matches = sorted(directory.glob(pattern))
    return matches[0] if matches else None


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Invalid bootstrap data in {path}: {exc}") from exc
    if not isinstance(payload, list):
        raise RuntimeError(f"Invalid bootstrap data in {path}: expected a JSON list.")
    return [item for item in payload if isinstance(item, dict)]


def _import_movies(items: list[dict[str, Any]], report: BootstrapReport) -> int:
    imported = 0
    for raw in items:
        ids = raw.get("id") or {}
        item = _find_media_item("movie", raw.get("uuid"), ids.get("imdb"), ids.get("tvdb"))
        watched_at = parse_datetime(raw.get("watched_at") or raw.get("created_at"))
        if item is None:
            item = MediaItem(
                media_type="movie",
                tvtime_uuid=raw.get("uuid"),
                tvdb_id=ids.get("tvdb"),
                imdb_id=ids.get("imdb"),
                italian_title=raw.get("title") or "Untitled movie",
                original_title=raw.get("title"),
                release_date=_date_from_year(raw.get("year")),
                watched_date=watched_at.date() if watched_at else None,
                favorite=bool(raw.get("is_favorite")),
                source="tvtime",
                bootstrap_payload=raw,
            )
            db.session.add(item)
            db.session.flush()
            imported += 1
        else:
            item.tvtime_uuid = item.tvtime_uuid or raw.get("uuid")
            item.tvdb_id = item.tvdb_id or ids.get("tvdb")
            item.imdb_id = item.imdb_id or ids.get("imdb")
            item.favorite = item.favorite or bool(raw.get("is_favorite"))
            item.watched_date = item.watched_date or (watched_at.date() if watched_at else None)
            item.bootstrap_payload = raw
        if watched_at:
            report.watch_events += _ensure_watch_event(item, None, watched_at, "tvtime", raw.get("rewatch_count", 0) + 1)
    return imported


def _import_series(items: list[dict[str, Any]], report: BootstrapReport) -> tuple[int, int, int]:
    show_count = 0
    episode_count = 0
    event_count = 0
    for raw in items:
        ids = raw.get("id") or {}
        item = _find_media_item("tv", raw.get("uuid"), ids.get("imdb"), ids.get("tvdb"))
        if item is None:
            item = MediaItem(
                media_type="tv",
                tvtime_uuid=raw.get("uuid"),
                tvdb_id=ids.get("tvdb"),
                imdb_id=ids.get("imdb"),
                italian_title=raw.get("title") or "Untitled show",
                original_title=raw.get("title"),
                favorite=bool(raw.get("is_favorite")),
                source="tvtime",
                bootstrap_payload=raw,
            )
            db.session.add(item)
            db.session.flush()
            show_count += 1
        else:
            item.tvtime_uuid = item.tvtime_uuid or raw.get("uuid")
            item.tvdb_id = item.tvdb_id or ids.get("tvdb")
            item.imdb_id = item.imdb_id or ids.get("imdb")
            item.favorite = item.favorite or bool(raw.get("is_favorite"))
            item.bootstrap_payload = raw

        latest_watch: datetime | None = None
        for season in raw.get("seasons") or []:
            season_number = int(season.get("number") or 0)
            for raw_episode in season.get("episodes") or []:
                episode = _ensure_episode(item, season_number, raw_episode)
                episode_count += 1
                watched_at = parse_datetime(raw_episode.get("watched_at"))
                if watched_at:
                    latest_watch = max(latest_watch or watched_at, watched_at)
                    event_count += _ensure_watch_event(
                        item,
                        episode,
                        watched_at,
                        "tvtime",
                        int(raw_episode.get("watched_count") or 1),
                    )
        if latest_watch and (item.watched_date is None or latest_watch.date() > item.watched_date):
            item.watched_date = latest_watch.date()
    return show_count, episode_count, event_count


def _import_lists(items: list[dict[str, Any]], report: BootstrapReport) -> int:
    imported = 0
    for raw in items:
        media_list = MediaList.query.filter_by(tvtime_id=raw.get("id")).first()
        if media_list is None:
            media_list = MediaList(tvtime_id=raw.get("id"), name=raw.get("name") or "Untitled list")
            db.session.add(media_list)
            db.session.flush()
            imported += 1
        media_list.description = raw.get("description")
        media_list.is_public = bool(raw.get("is_public"))
        media_list.source_created_at = parse_datetime(raw.get("created_at"))

        for raw_item in raw.get("items") or []:
            media_item = _find_media_item(raw_item.get("type"), raw_item.get("uuid"), None, None)
            if media_item is None:
                media_item = MediaItem(
                    media_type="movie" if raw_item.get("type") == "movie" else "tv",
                    tvtime_uuid=raw_item.get("uuid"),
                    italian_title=raw_item.get("name") or "Untitled",
                    original_title=raw_item.get("name"),
                    source="tvtime-list",
                )
                db.session.add(media_item)
                db.session.flush()
            link = MediaListItem.query.filter_by(media_list_id=media_list.id, media_item_id=media_item.id).first()
            if link is None:
                link = MediaListItem(media_list=media_list, media_item=media_item)
                db.session.add(link)
            link.sort_order = int(raw_item.get("custom_order") or 0)
    return imported


def _find_media_item(
    media_type: str | None,
    tvtime_uuid: str | None,
    imdb_id: str | None,
    tvdb_id: int | None,
) -> MediaItem | None:
    if media_type not in {"movie", "tv"}:
        return None
    query = MediaItem.query.filter_by(media_type=media_type)
    if tvtime_uuid:
        item = query.filter_by(tvtime_uuid=tvtime_uuid).first()
        if item:
            return item
    if imdb_id:
        item = query.filter_by(imdb_id=imdb_id).first()
        if item:
            return item
    if tvdb_id:
        item = query.filter_by(tvdb_id=tvdb_id).first()
        if item:
            return item
    return None


def _ensure_episode(item: MediaItem, season_number: int, raw: dict[str, Any]) -> Episode:
    episode = Episode.query.filter_by(
        media_item=item,
        season_number=season_number,
        episode_number=int(raw.get("number") or 0),
    ).first()
    ids = raw.get("id") or {}
    if episode is None:
        episode = Episode(
            media_item=item,
            season_number=season_number,
            episode_number=int(raw.get("number") or 0),
        )
        db.session.add(episode)
        db.session.flush()
    episode.title = raw.get("name")
    episode.tvdb_id = ids.get("tvdb")
    episode.imdb_id = ids.get("imdb")
    episode.is_special = bool(raw.get("special"))
    episode.is_watched = bool(raw.get("is_watched"))
    episode.watched_at = parse_datetime(raw.get("watched_at"))
    episode.watched_count = int(raw.get("watched_count") or 0)
    episode.rewatch_count = int(raw.get("rewatch_count") or 0)
    return episode


def _ensure_watch_event(
    item: MediaItem,
    episode: Episode | None,
    watched_at: datetime,
    source: str,
    watch_count: int = 1,
) -> int:
    query = WatchEvent.query.filter_by(media_item=item, episode=episode, watched_at=watched_at, source=source)
    event = query.first()
    if event is None:
        db.session.add(
            WatchEvent(
                media_item=item,
                episode=episode,
                watched_at=watched_at,
                source=source,
                watch_count=max(1, watch_count),
            )
        )
        return 1
    event.watch_count = max(event.watch_count, watch_count)
    return 0


def _date_from_year(year: int | None) -> Any:
    if not year:
        return None
    return parse_date(f"{year}-01-01")


def reset_bootstrap_flags() -> None:
    for key in ("tvtime_bootstrap_imported", "tmdb_enrichment_completed"):
        item = Setting.query.filter(func.lower(Setting.key) == key).first()
        if item:
            db.session.delete(item)
    db.session.commit()
