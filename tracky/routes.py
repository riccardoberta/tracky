from __future__ import annotations

from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import func, or_

from .extensions import db
from .models import Genre, MediaItem, Setting, WatchEvent
from .services.bootstrap import apply_tmdb_details, enrich_metadata_batch, missing_metadata_count
from .services.statistics import build_statistics
from .services.tmdb import TMDbClient, TMDbError
from .utils import parse_date_field, safe_float, safe_int, split_names, utc_now


main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    return redirect(url_for("main.dashboard"))


@main_bp.route("/dashboard")
def dashboard():
    stats = build_statistics()
    recent_items = MediaItem.query.filter(MediaItem.watched_date.is_not(None)).order_by(
        MediaItem.watched_date.desc(),
        MediaItem.updated_at.desc(),
    ).limit(8).all()
    favorites = MediaItem.query.filter_by(favorite=True).order_by(MediaItem.updated_at.desc()).limit(6).all()
    return render_template(
        "dashboard.html",
        stats=stats,
        recent_items=recent_items,
        favorites=favorites,
        active_page="dashboard",
    )


@main_bp.route("/timeline")
def timeline():
    query = _filtered_media_query().filter(MediaItem.watched_date.is_not(None))
    items = query.order_by(MediaItem.watched_date.desc(), func.lower(MediaItem.italian_title).asc()).all()
    return render_template(
        "collection.html",
        title="Timeline",
        subtitle="Watched items, newest first.",
        items=items,
        genres=_all_genres(),
        active_page="timeline",
        sort_label="Newest first",
        show_filters=True,
    )


@main_bp.route("/library")
def library():
    items = _filtered_media_query().order_by(func.lower(MediaItem.italian_title).asc()).all()
    return render_template(
        "collection.html",
        title="Library",
        subtitle="Your complete media library, ordered alphabetically.",
        items=items,
        genres=_all_genres(),
        active_page="library",
        sort_label="A to Z",
        show_filters=True,
    )


@main_bp.route("/favorites")
def favorites():
    items = _filtered_media_query().filter_by(favorite=True).order_by(func.lower(MediaItem.italian_title).asc()).all()
    return render_template(
        "collection.html",
        title="Favorites",
        subtitle="Movies and shows you marked as favorites.",
        items=items,
        genres=_all_genres(),
        active_page="favorites",
        sort_label="Favorites",
        show_filters=True,
    )


@main_bp.route("/search")
def search():
    query_text = request.args.get("q", "").strip()
    media_type = request.args.get("type") or None
    local_results: list[MediaItem] = []
    remote_results = []
    tmdb_error = None

    if query_text:
        query = MediaItem.query.filter(
            or_(
                MediaItem.italian_title.ilike(f"%{query_text}%"),
                MediaItem.original_title.ilike(f"%{query_text}%"),
            )
        )
        if media_type in {"movie", "tv"}:
            query = query.filter_by(media_type=media_type)
        local_results = query.order_by(func.lower(MediaItem.italian_title).asc()).all()

        client = _tmdb_client()
        if client.configured:
            try:
                remote_results = client.search(query_text, media_type)
            except TMDbError as exc:
                tmdb_error = str(exc)
        else:
            tmdb_error = "TMDb search is unavailable because TMDB_API_KEY is not configured."

    return render_template(
        "search.html",
        query=query_text,
        selected_type=media_type or "",
        local_results=local_results,
        remote_results=remote_results,
        tmdb_error=tmdb_error,
        active_page="search",
    )


@main_bp.route("/media/import", methods=["POST"])
def import_from_tmdb():
    tmdb_id = safe_int(request.form.get("tmdb_id"))
    media_type = request.form.get("media_type")
    watched_date = parse_date_field(request.form.get("watched_date")) or utc_now().date()
    if tmdb_id is None or media_type not in {"movie", "tv"}:
        flash("The TMDb result could not be imported.", "error")
        return redirect(url_for("main.search"))

    client = _tmdb_client()
    if not client.configured:
        flash("TMDb import requires TMDB_API_KEY.", "error")
        return redirect(url_for("main.search"))

    try:
        details = client.details(tmdb_id, media_type)
    except TMDbError as exc:
        flash(str(exc), "error")
        return redirect(url_for("main.search", q=request.form.get("q", "")))

    item = MediaItem.query.filter_by(media_type=media_type, tmdb_id=tmdb_id).first()
    if item is None:
        item = MediaItem(media_type=media_type, italian_title=details.get("italian_title") or "Untitled", source="tmdb")
        db.session.add(item)
        db.session.flush()
    apply_tmdb_details(item, details)
    item.watched_date = item.watched_date or watched_date
    item.favorite = bool(request.form.get("favorite"))
    db.session.add(WatchEvent(media_item=item, watched_at=datetime.combine(watched_date, datetime.min.time()), source="manual"))
    db.session.commit()
    flash(f"{item.title} was added to Tracky.", "success")
    return redirect(url_for("main.media_detail", item_id=item.id))


@main_bp.route("/media/<int:item_id>")
def media_detail(item_id: int):
    item = MediaItem.query.get_or_404(item_id)
    return render_template("detail.html", item=item, active_page=None)


@main_bp.route("/media/<int:item_id>/edit", methods=["GET", "POST"])
def media_edit(item_id: int):
    item = MediaItem.query.get_or_404(item_id)
    if request.method == "POST":
        _update_media_from_form(item)
        db.session.commit()
        flash("Item updated.", "success")
        return redirect(url_for("main.media_detail", item_id=item.id))
    return render_template("edit.html", item=item, active_page=None)


@main_bp.route("/media/<int:item_id>/favorite", methods=["POST"])
def toggle_favorite(item_id: int):
    item = MediaItem.query.get_or_404(item_id)
    item.favorite = not item.favorite
    db.session.commit()
    return redirect(request.referrer or url_for("main.media_detail", item_id=item.id))


@main_bp.route("/statistics")
def statistics():
    return render_template("statistics.html", stats=build_statistics(), active_page="statistics")


@main_bp.route("/metadata")
def metadata():
    client = _tmdb_client()
    return render_template(
        "metadata.html",
        missing_count=missing_metadata_count(),
        tmdb_configured=client.configured,
        active_page="metadata",
    )


@main_bp.route("/metadata/enrich", methods=["POST"])
def enrich_metadata():
    client = _tmdb_client()
    if not client.configured:
        flash("TMDb enrichment requires TMDB_API_KEY.", "error")
        return redirect(url_for("main.metadata"))

    batch_size = safe_int(request.form.get("batch_size")) or 10
    batch_size = max(1, min(batch_size, 25))
    report = enrich_metadata_batch(client, limit=batch_size)
    if report.remaining == 0:
        Setting.set("tmdb_enrichment_completed", "true")
        Setting.set("tmdb_enrichment_completed_at", utc_now().isoformat())
        db.session.commit()

    flash(
        (
            f"TMDb enrichment processed {report.processed} items: "
            f"{report.enriched} enriched, {report.skipped} skipped, {report.failed} failed. "
            f"{report.remaining} remaining."
        ),
        "success" if report.failed == 0 else "warning",
    )
    return redirect(url_for("main.metadata"))


def _filtered_media_query():
    query = MediaItem.query
    media_type = request.args.get("type")
    genre = request.args.get("genre")
    favorite = request.args.get("favorite")
    min_rating = safe_float(request.args.get("min_rating"))
    watched_year = request.args.get("year")
    search_text = request.args.get("q", "").strip()

    if media_type in {"movie", "tv"}:
        query = query.filter_by(media_type=media_type)
    if genre:
        query = query.join(MediaItem.genres).filter(Genre.name == genre)
    if favorite == "1":
        query = query.filter_by(favorite=True)
    if min_rating is not None:
        query = query.filter(MediaItem.personal_rating >= min_rating)
    if watched_year:
        query = query.filter(func.strftime("%Y", MediaItem.watched_date) == watched_year)
    if search_text:
        query = query.filter(
            or_(
                MediaItem.italian_title.ilike(f"%{search_text}%"),
                MediaItem.original_title.ilike(f"%{search_text}%"),
            )
        )
    return query.distinct()


def _all_genres() -> list[Genre]:
    return Genre.query.order_by(func.lower(Genre.name).asc()).all()


def _tmdb_client() -> TMDbClient:
    return TMDbClient(
        current_app.config.get("TMDB_API_KEY"),
        language=current_app.config.get("TRACKY_TMDB_LANGUAGE", "it-IT"),
    )


def _update_media_from_form(item: MediaItem) -> None:
    item.italian_title = request.form.get("italian_title", "").strip() or item.italian_title
    item.original_title = request.form.get("original_title", "").strip() or item.original_title
    item.overview = request.form.get("overview", "").strip() or None
    item.tmdb_rating = safe_float(request.form.get("tmdb_rating"))
    item.tmdb_vote_count = safe_int(request.form.get("tmdb_vote_count"))
    item.poster_path = request.form.get("poster_path", "").strip() or None
    item.backdrop_path = request.form.get("backdrop_path", "").strip() or None
    item.watched_date = parse_date_field(request.form.get("watched_date"))
    item.favorite = bool(request.form.get("favorite"))
    item.personal_rating = _valid_personal_rating(safe_float(request.form.get("personal_rating")))
    item.personal_notes = request.form.get("personal_notes", "").strip() or None

    release_date = parse_date_field(request.form.get("release_date"))
    if item.media_type == "movie":
        item.release_date = release_date
    else:
        item.first_air_date = release_date

    item.set_genres(split_names(request.form.get("genres")))
    primary_role = "director" if item.media_type == "movie" else "creator"
    item.set_people(primary_role, split_names(request.form.get("primary_people")))
    item.set_people("cast", split_names(request.form.get("cast")))


def _valid_personal_rating(value: float | None) -> float | None:
    if value is None:
        return None
    if value < current_app.config["PERSONAL_SCORE_MIN"] or value > current_app.config["PERSONAL_SCORE_MAX"]:
        flash("Personal rating was outside the configured range and was ignored.", "error")
        return None
    return value
