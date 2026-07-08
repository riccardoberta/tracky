from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from flask import current_app
from sqlalchemy import or_

from ..extensions import db
from ..models import MediaItem, MediaPerson, get_or_create_person
from ..utils import parse_date_field
from .tmdb import TMDbClient, TMDbError


@dataclass
class EnrichmentReport:
    processed: int = 0
    enriched: int = 0
    skipped: int = 0
    failed: int = 0
    remaining: int = 0


def missing_metadata_query():
    return MediaItem.query.filter(
        MediaItem.media_type.in_(("movie", "tv")),
        or_(
            MediaItem.overview.is_(None),
            MediaItem.poster_path.is_(None),
            MediaItem.tmdb_rating.is_(None),
        ),
    )


def missing_metadata_count() -> int:
    return missing_metadata_query().count()


def enrich_missing_metadata(client: TMDbClient) -> int:
    return enrich_metadata_batch(client, limit=None).enriched


def enrich_metadata_batch(client: TMDbClient, limit: int | None = 10) -> EnrichmentReport:
    report = EnrichmentReport()
    query = missing_metadata_query().order_by(MediaItem.id.asc())
    if limit is not None:
        query = query.limit(limit)
    items = query.all()

    for item in items:
        report.processed += 1
        try:
            tmdb_id = item.tmdb_id
            if tmdb_id is None and item.imdb_id:
                tmdb_id = client.find_by_imdb(item.imdb_id, item.media_type)
            if tmdb_id is None:
                for title, year in _title_candidates(item):
                    tmdb_id = client.best_match(title, year, item.media_type)
                    if tmdb_id is not None:
                        break
            if tmdb_id is None:
                report.skipped += 1
                continue
            details = client.details(tmdb_id, item.media_type)
            assign_tmdb_id = not _tmdb_id_conflicts(item, details.get("tmdb_id") or tmdb_id)
            apply_tmdb_details(item, details, assign_tmdb_id=assign_tmdb_id)
            report.enriched += 1
            db.session.commit()
        except TMDbError as exc:
            current_app.logger.warning("TMDb enrichment failed for %s: %s", item.title, exc)
            report.failed += 1
            db.session.rollback()
            continue
    report.remaining = missing_metadata_count()
    return report


def apply_tmdb_details(item: MediaItem, details: dict[str, Any], assign_tmdb_id: bool = True) -> None:
    if assign_tmdb_id:
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


def _tmdb_id_conflicts(item: MediaItem, tmdb_id: int | None) -> bool:
    if tmdb_id is None:
        return False
    return (
        MediaItem.query.filter(
            MediaItem.media_type == item.media_type,
            MediaItem.tmdb_id == tmdb_id,
            MediaItem.id != item.id,
        ).first()
        is not None
    )


def _title_candidates(item: MediaItem) -> list[tuple[str, int | None]]:
    candidates: list[tuple[str, int | None]] = []
    for title in (item.original_title, item.italian_title):
        if not title:
            continue
        _append_title_candidate(candidates, title, item.year)

        year_match = re.search(r"\((19\d{2}|20\d{2})\)", title)
        if year_match:
            cleaned_title = re.sub(r"\s*\((19\d{2}|20\d{2})\)\s*", " ", title).strip()
            _append_title_candidate(candidates, cleaned_title, int(year_match.group(1)))

        suffix_match = re.search(r"\s*\(([A-Za-z]{2,})\)\s*$", title)
        if suffix_match:
            cleaned_title = re.sub(r"\s*\([A-Za-z]{2,}\)\s*$", "", title).strip()
            _append_title_candidate(candidates, cleaned_title, item.year)
    return candidates


def _append_title_candidate(candidates: list[tuple[str, int | None]], title: str, year: int | None) -> None:
    clean_title = " ".join(title.split())
    if clean_title and (clean_title, year) not in candidates:
        candidates.append((clean_title, year))


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
