from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

from sqlalchemy import CheckConstraint, UniqueConstraint, func

from .extensions import db
from .utils import utc_now


media_genres = db.Table(
    "media_genres",
    db.Column("media_item_id", db.Integer, db.ForeignKey("media_items.id"), primary_key=True),
    db.Column("genre_id", db.Integer, db.ForeignKey("genres.id"), primary_key=True),
)


class TimestampMixin:
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class User(TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False, index=True)


class Genre(db.Model):
    __tablename__ = "genres"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<Genre {self.name}>"


class Person(db.Model):
    __tablename__ = "people"

    id = db.Column(db.Integer, primary_key=True)
    tmdb_id = db.Column(db.Integer, unique=True, nullable=True, index=True)
    name = db.Column(db.String(180), unique=True, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<Person {self.name}>"


class MediaPerson(db.Model):
    __tablename__ = "media_people"
    __table_args__ = (
        UniqueConstraint("media_item_id", "person_id", "role", name="uq_media_person_role"),
    )

    id = db.Column(db.Integer, primary_key=True)
    media_item_id = db.Column(db.Integer, db.ForeignKey("media_items.id"), nullable=False, index=True)
    person_id = db.Column(db.Integer, db.ForeignKey("people.id"), nullable=False, index=True)
    role = db.Column(db.String(40), nullable=False, index=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    media_item = db.relationship("MediaItem", back_populates="people_links")
    person = db.relationship("Person")


class MediaItem(TimestampMixin, db.Model):
    __tablename__ = "media_items"
    __table_args__ = (
        CheckConstraint("media_type IN ('movie', 'tv')", name="ck_media_type"),
        UniqueConstraint("media_type", "tmdb_id", name="uq_media_tmdb"),
    )

    id = db.Column(db.Integer, primary_key=True)
    media_type = db.Column(db.String(12), nullable=False, index=True)

    tmdb_id = db.Column(db.Integer, nullable=True, index=True)
    tvdb_id = db.Column(db.Integer, nullable=True, index=True)
    imdb_id = db.Column(db.String(32), nullable=True, index=True)
    tvtime_uuid = db.Column(db.String(80), unique=True, nullable=True, index=True)

    italian_title = db.Column(db.String(300), nullable=False, index=True)
    original_title = db.Column(db.String(300), nullable=True, index=True)
    overview = db.Column(db.Text, nullable=True)

    release_date = db.Column(db.Date, nullable=True)
    first_air_date = db.Column(db.Date, nullable=True)
    tmdb_rating = db.Column(db.Float, nullable=True)
    tmdb_vote_count = db.Column(db.Integer, nullable=True)
    poster_path = db.Column(db.String(500), nullable=True)
    backdrop_path = db.Column(db.String(500), nullable=True)

    watched_date = db.Column(db.Date, nullable=True, index=True)
    favorite = db.Column(db.Boolean, nullable=False, default=False, index=True)
    personal_rating = db.Column(db.Float, nullable=True, index=True)
    personal_notes = db.Column(db.Text, nullable=True)

    source = db.Column(db.String(80), nullable=False, default="manual", index=True)
    bootstrap_payload = db.Column(db.JSON, nullable=True)

    genres = db.relationship("Genre", secondary=media_genres, lazy="selectin", backref="media_items")
    people_links = db.relationship(
        "MediaPerson",
        back_populates="media_item",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="MediaPerson.sort_order",
    )
    episodes = db.relationship(
        "Episode",
        back_populates="media_item",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="(Episode.season_number, Episode.episode_number)",
    )
    watch_events = db.relationship(
        "WatchEvent",
        back_populates="media_item",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="WatchEvent.watched_at.desc()",
    )

    @property
    def title(self) -> str:
        return self.italian_title or self.original_title or "Untitled"

    @property
    def year(self) -> int | None:
        value = self.release_date or self.first_air_date or self.watched_date
        return value.year if value else None

    @property
    def primary_people(self) -> list[Person]:
        role = "director" if self.media_type == "movie" else "creator"
        return self.people_by_role(role)

    @property
    def cast(self) -> list[Person]:
        return self.people_by_role("cast")

    @property
    def watched_episode_count(self) -> int:
        return sum(1 for episode in self.episodes if episode.is_watched)

    def people_by_role(self, role: str) -> list[Person]:
        return [link.person for link in self.people_links if link.role == role]

    def set_genres(self, names: Iterable[str]) -> None:
        self.genres = [get_or_create_genre(name) for name in names if name.strip()]

    def set_people(self, role: str, names: Iterable[str]) -> None:
        cleaned_names = [name.strip() for name in names if name.strip()]
        for link in list(self.people_links):
            if link.role == role:
                self.people_links.remove(link)
                db.session.delete(link)
        db.session.flush()
        for index, name in enumerate(cleaned_names):
            person = get_or_create_person(name)
            self.people_links.append(MediaPerson(person=person, role=role, sort_order=index))

    def __repr__(self) -> str:
        return f"<MediaItem {self.media_type}:{self.title}>"


class Episode(TimestampMixin, db.Model):
    __tablename__ = "episodes"
    __table_args__ = (
        UniqueConstraint("media_item_id", "season_number", "episode_number", name="uq_episode_number"),
    )

    id = db.Column(db.Integer, primary_key=True)
    media_item_id = db.Column(db.Integer, db.ForeignKey("media_items.id"), nullable=False, index=True)
    season_number = db.Column(db.Integer, nullable=False, default=0, index=True)
    episode_number = db.Column(db.Integer, nullable=False, default=0, index=True)
    title = db.Column(db.String(300), nullable=True)
    tvdb_id = db.Column(db.Integer, nullable=True, index=True)
    imdb_id = db.Column(db.String(32), nullable=True, index=True)
    is_special = db.Column(db.Boolean, nullable=False, default=False)
    is_watched = db.Column(db.Boolean, nullable=False, default=False, index=True)
    watched_at = db.Column(db.DateTime, nullable=True, index=True)
    watched_count = db.Column(db.Integer, nullable=False, default=0)
    rewatch_count = db.Column(db.Integer, nullable=False, default=0)

    media_item = db.relationship("MediaItem", back_populates="episodes")
    watch_events = db.relationship(
        "WatchEvent",
        back_populates="episode",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class WatchEvent(TimestampMixin, db.Model):
    __tablename__ = "watch_events"

    id = db.Column(db.Integer, primary_key=True)
    media_item_id = db.Column(db.Integer, db.ForeignKey("media_items.id"), nullable=False, index=True)
    episode_id = db.Column(db.Integer, db.ForeignKey("episodes.id"), nullable=True, index=True)
    watched_at = db.Column(db.DateTime, nullable=False, index=True)
    source = db.Column(db.String(80), nullable=False, default="manual", index=True)
    watch_count = db.Column(db.Integer, nullable=False, default=1)

    media_item = db.relationship("MediaItem", back_populates="watch_events")
    episode = db.relationship("Episode", back_populates="watch_events")


class MediaList(TimestampMixin, db.Model):
    __tablename__ = "media_lists"

    id = db.Column(db.Integer, primary_key=True)
    tvtime_id = db.Column(db.String(100), unique=True, nullable=True, index=True)
    name = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_public = db.Column(db.Boolean, nullable=False, default=False)
    source_created_at = db.Column(db.DateTime, nullable=True)

    items = db.relationship(
        "MediaListItem",
        back_populates="media_list",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="MediaListItem.sort_order",
    )


class MediaListItem(db.Model):
    __tablename__ = "media_list_items"
    __table_args__ = (
        UniqueConstraint("media_list_id", "media_item_id", name="uq_media_list_item"),
    )

    id = db.Column(db.Integer, primary_key=True)
    media_list_id = db.Column(db.Integer, db.ForeignKey("media_lists.id"), nullable=False, index=True)
    media_item_id = db.Column(db.Integer, db.ForeignKey("media_items.id"), nullable=False, index=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    media_list = db.relationship("MediaList", back_populates="items")
    media_item = db.relationship("MediaItem")


class Setting(db.Model):
    __tablename__ = "settings"

    key = db.Column(db.String(120), primary_key=True)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    @classmethod
    def get(cls, key: str, default: str | None = None) -> str | None:
        item = db.session.get(cls, key)
        return item.value if item else default

    @classmethod
    def set(cls, key: str, value: str | None) -> None:
        item = db.session.get(cls, key)
        if item is None:
            item = cls(key=key, value=value)
            db.session.add(item)
        else:
            item.value = value


def get_or_create_genre(name: str) -> Genre:
    clean_name = name.strip()
    genre = Genre.query.filter(func.lower(Genre.name) == clean_name.lower()).first()
    if genre is None:
        genre = Genre(name=clean_name)
        db.session.add(genre)
        db.session.flush()
    return genre


def get_or_create_person(name: str, tmdb_id: int | None = None) -> Person:
    clean_name = name.strip()
    person = None
    if tmdb_id:
        person = Person.query.filter_by(tmdb_id=tmdb_id).first()
    if person is None:
        person = Person.query.filter(func.lower(Person.name) == clean_name.lower()).first()
    if person is None:
        person = Person(name=clean_name, tmdb_id=tmdb_id)
        db.session.add(person)
        db.session.flush()
    elif tmdb_id and person.tmdb_id is None:
        person.tmdb_id = tmdb_id
    return person


def watched_year_expression():
    return func.strftime("%Y", MediaItem.watched_date)


def watched_month_expression():
    return func.strftime("%Y-%m", WatchEvent.watched_at)
