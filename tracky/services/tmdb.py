from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


class TMDbError(RuntimeError):
    pass


@dataclass(frozen=True)
class TMDbSearchResult:
    media_type: str
    tmdb_id: int
    title: str
    original_title: str | None
    overview: str | None
    date: str | None
    poster_path: str | None
    vote_average: float | None


class TMDbClient:
    base_url = "https://api.themoviedb.org/3"

    def __init__(
        self,
        api_key: str | None,
        language: str = "it-IT",
        session: requests.Session | None = None,
        timeout: int = 12,
    ) -> None:
        self.api_key = api_key
        self.language = language
        self.session = session or requests.Session()
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _get(self, path: str, **params: Any) -> dict[str, Any]:
        if not self.api_key:
            raise TMDbError("TMDb API key is not configured.")
        query = {"api_key": self.api_key, "language": self.language, **params}
        try:
            response = self.session.get(
                f"{self.base_url}{path}",
                params=query,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise TMDbError(f"TMDb request failed: {exc}") from exc
        payload = response.json()
        if not isinstance(payload, dict):
            raise TMDbError("TMDb returned an unexpected response.")
        return payload

    def find_by_imdb(self, imdb_id: str | None, expected_type: str) -> int | None:
        if not imdb_id:
            return None
        payload = self._get(f"/find/{imdb_id}", external_source="imdb_id")
        key = "movie_results" if expected_type == "movie" else "tv_results"
        results = payload.get(key) or []
        if results:
            return results[0].get("id")
        return None

    def search(self, query: str, media_type: str | None = None) -> list[TMDbSearchResult]:
        if not query.strip():
            return []
        media_types = [media_type] if media_type in {"movie", "tv"} else ["movie", "tv"]
        results: list[TMDbSearchResult] = []
        for item_type in media_types:
            payload = self._get(f"/search/{item_type}", query=query, include_adult=False)
            for item in payload.get("results", [])[:10]:
                title_key = "title" if item_type == "movie" else "name"
                original_key = "original_title" if item_type == "movie" else "original_name"
                date_key = "release_date" if item_type == "movie" else "first_air_date"
                results.append(
                    TMDbSearchResult(
                        media_type=item_type,
                        tmdb_id=item["id"],
                        title=item.get(title_key) or item.get(original_key) or "Untitled",
                        original_title=item.get(original_key),
                        overview=item.get("overview"),
                        date=item.get(date_key),
                        poster_path=item.get("poster_path"),
                        vote_average=item.get("vote_average"),
                    )
                )
        return results

    def best_match(self, title: str, year: int | None, media_type: str) -> int | None:
        results = self.search(title, media_type)
        if not results:
            return None
        if year:
            for result in results:
                if result.date and result.date[:4] == str(year):
                    return result.tmdb_id
        return results[0].tmdb_id

    def details(self, tmdb_id: int, media_type: str) -> dict[str, Any]:
        append = "credits,external_ids"
        payload = self._get(f"/{media_type}/{tmdb_id}", append_to_response=append)
        credits = payload.get("credits") or {}
        cast = [
            {"name": person.get("name"), "tmdb_id": person.get("id")}
            for person in (credits.get("cast") or [])[:10]
            if person.get("name")
        ]

        if media_type == "movie":
            directors = [
                {"name": person.get("name"), "tmdb_id": person.get("id")}
                for person in (credits.get("crew") or [])
                if person.get("job") == "Director" and person.get("name")
            ]
            primary_people = directors[:4]
            italian_title = payload.get("title")
            original_title = payload.get("original_title")
            date_value = payload.get("release_date")
        else:
            primary_people = [
                {"name": person.get("name"), "tmdb_id": person.get("id")}
                for person in payload.get("created_by", [])
                if person.get("name")
            ]
            italian_title = payload.get("name")
            original_title = payload.get("original_name")
            date_value = payload.get("first_air_date")

        external_ids = payload.get("external_ids") or {}
        return {
            "tmdb_id": payload.get("id"),
            "imdb_id": external_ids.get("imdb_id"),
            "italian_title": italian_title or original_title or "Untitled",
            "original_title": original_title,
            "overview": payload.get("overview"),
            "genres": [genre.get("name") for genre in payload.get("genres", []) if genre.get("name")],
            "primary_people": primary_people,
            "cast": cast,
            "date": date_value,
            "tmdb_rating": payload.get("vote_average"),
            "tmdb_vote_count": payload.get("vote_count"),
            "poster_path": payload.get("poster_path"),
            "backdrop_path": payload.get("backdrop_path"),
        }
