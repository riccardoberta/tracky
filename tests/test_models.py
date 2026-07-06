from __future__ import annotations

from tracky.extensions import db
from tracky.models import MediaItem


def test_media_item_normalized_genres_and_people(app):
    with app.app_context():
        item = MediaItem(media_type="movie", italian_title="La grande bellezza", original_title="The Great Beauty")
        db.session.add(item)
        db.session.flush()

        item.set_genres(["Drama", "Comedy"])
        item.set_people("director", ["Paolo Sorrentino"])
        item.set_people("cast", ["Toni Servillo", "Carlo Verdone"])
        db.session.commit()

        saved = MediaItem.query.one()
        assert [genre.name for genre in saved.genres] == ["Drama", "Comedy"]
        assert [person.name for person in saved.primary_people] == ["Paolo Sorrentino"]
        assert [person.name for person in saved.cast] == ["Toni Servillo", "Carlo Verdone"]
