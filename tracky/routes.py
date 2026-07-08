from __future__ import annotations

import re
from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import and_, func, or_

from .extensions import db
from .models import Genre, MediaItem, MediaListItem, Setting, WatchEvent, watched_year_expression
from .services.metadata import apply_tmdb_details
from .services.statistics import build_statistics
from .services.tmdb import TMDbClient, TMDbError
from .utils import parse_date_field, safe_float, safe_int, split_names, utc_now


main_bp = Blueprint("main", __name__)
CHECK_SETTING_PREFIX = "seed_review_item:"
TMDB_REFERENCE_RE = re.compile(r"(?:themoviedb\.org/)?(movie|tv)/(\d+)", re.IGNORECASE)


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
        today_date=utc_now().date().isoformat(),
        default_personal_rating=_default_personal_rating(),
        active_page="search",
    )


@main_bp.route("/media/import", methods=["POST"])
def import_from_tmdb():
    tmdb_id = safe_int(request.form.get("tmdb_id"))
    media_type = request.form.get("media_type")
    watched_date = parse_date_field(request.form.get("watched_date")) or utc_now().date()
    personal_rating = _valid_personal_rating(safe_float(request.form.get("personal_rating")))
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
    if personal_rating is not None:
        item.personal_rating = personal_rating
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
    return_url = _safe_return_url(request.values.get("next")) or url_for("main.media_detail", item_id=item.id)
    if request.method == "POST":
        _update_media_from_form(item)
        db.session.commit()
        flash("Item updated.", "success")
        return redirect(return_url)
    return render_template("edit.html", item=item, return_url=return_url, active_page=None)


@main_bp.route("/media/<int:item_id>/favorite", methods=["POST"])
def toggle_favorite(item_id: int):
    item = MediaItem.query.get_or_404(item_id)
    item.favorite = not item.favorite
    db.session.commit()
    return redirect(request.referrer or url_for("main.media_detail", item_id=item.id))


@main_bp.route("/statistics")
def statistics():
    return render_template("statistics.html", stats=build_statistics(), active_page="statistics")


@main_bp.route("/check")
def check_start():
    item = _next_unchecked_item()
    if item is None:
        item = _ordered_check_items().first()
    if item is None:
        return render_template(
            "check.html",
            item=None,
            previous_item=None,
            next_item=None,
            checked_count=0,
            total_count=0,
            current_tmdb_url=None,
            active_page="check",
        )
    return redirect(url_for("main.check_item", item_id=item.id))


@main_bp.route("/check/<int:item_id>")
def check_item(item_id: int):
    item = MediaItem.query.get_or_404(item_id)
    previous_item, next_item = _check_neighbors(item)
    return render_template(
        "check.html",
        item=item,
        previous_item=previous_item,
        next_item=next_item,
        checked_count=_checked_item_count(),
        total_count=MediaItem.query.count(),
        current_tmdb_url=_tmdb_url_for(item),
        active_page="check",
    )


@main_bp.route("/check/<int:item_id>/ok", methods=["POST"])
def check_mark_ok(item_id: int):
    item = MediaItem.query.get_or_404(item_id)
    if not _update_required_personal_rating(item):
        return redirect(url_for("main.check_item", item_id=item.id))
    _mark_checked(item, "ok")
    db.session.commit()
    return redirect(_next_check_url(item))


@main_bp.route("/check/<int:item_id>/correct", methods=["POST"])
def check_correct_item(item_id: int):
    item = MediaItem.query.get_or_404(item_id)
    if not _update_required_personal_rating(item):
        return redirect(url_for("main.check_item", item_id=item.id))

    parsed = _parse_tmdb_reference(request.form.get("tmdb_url", ""), item.media_type)
    if parsed is None:
        flash("Enter a valid TMDb URL such as https://www.themoviedb.org/movie/12345 or https://www.themoviedb.org/tv/12345.", "error")
        return redirect(url_for("main.check_item", item_id=item.id))

    media_type, tmdb_id = parsed
    duplicate = MediaItem.query.filter(
        MediaItem.media_type == media_type,
        MediaItem.tmdb_id == tmdb_id,
        MediaItem.id != item.id,
    ).first()
    if duplicate is not None:
        flash(f"That TMDb item is already linked to {duplicate.title}.", "error")
        return redirect(url_for("main.check_item", item_id=item.id))

    client = _tmdb_client()
    if not client.configured:
        flash("TMDb correction requires TMDB_API_KEY.", "error")
        return redirect(url_for("main.check_item", item_id=item.id))

    try:
        details = client.details(tmdb_id, media_type)
    except TMDbError as exc:
        flash(str(exc), "error")
        return redirect(url_for("main.check_item", item_id=item.id))

    item.media_type = media_type
    apply_tmdb_details(item, details, assign_tmdb_id=True)
    _mark_checked(item, f"corrected:{media_type}:{tmdb_id}")
    db.session.commit()
    flash(f"{item.title} was updated from TMDb.", "success")
    return redirect(_next_check_url(item))


@main_bp.route("/check/<int:item_id>/delete", methods=["POST"])
def check_delete_item(item_id: int):
    item = MediaItem.query.get_or_404(item_id)
    previous_item, next_item = _check_neighbors(item)
    title = item.title
    MediaListItem.query.filter_by(media_item_id=item.id).delete(synchronize_session=False)
    Setting.query.filter_by(key=f"{CHECK_SETTING_PREFIX}{item.id}").delete(synchronize_session=False)
    db.session.delete(item)
    db.session.commit()
    flash(f"{title} was deleted from Tracky.", "success")
    if next_item is not None:
        return redirect(url_for("main.check_item", item_id=next_item.id))
    if previous_item is not None:
        return redirect(url_for("main.check_item", item_id=previous_item.id))
    return redirect(url_for("main.check_start"))


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
        query = query.filter(watched_year_expression() == watched_year)
    if search_text:
        query = query.filter(
            or_(
                MediaItem.italian_title.ilike(f"%{search_text}%"),
                MediaItem.original_title.ilike(f"%{search_text}%"),
            )
        )
    return query


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


def _default_personal_rating() -> int:
    return min(max(6, current_app.config["PERSONAL_SCORE_MIN"]), current_app.config["PERSONAL_SCORE_MAX"])


def _ordered_check_items():
    return MediaItem.query.order_by(func.lower(MediaItem.italian_title).asc(), MediaItem.id.asc())


def _next_unchecked_item() -> MediaItem | None:
    checked_ids = _checked_item_ids()
    query = _ordered_check_items()
    if checked_ids:
        query = query.filter(MediaItem.id.not_in(checked_ids))
    return query.first()


def _check_neighbors(item: MediaItem) -> tuple[MediaItem | None, MediaItem | None]:
    item_title = item.title.lower()
    title_sort = func.lower(MediaItem.italian_title)
    previous_item = MediaItem.query.filter(
        or_(
            title_sort < item_title,
            and_(title_sort == item_title, MediaItem.id < item.id),
        )
    ).filter(MediaItem.id != item.id).order_by(title_sort.desc(), MediaItem.id.desc()).first()
    next_item = MediaItem.query.filter(
        or_(
            title_sort > item_title,
            and_(title_sort == item_title, MediaItem.id > item.id),
        )
    ).filter(MediaItem.id != item.id).order_by(title_sort.asc(), MediaItem.id.asc()).first()
    return previous_item, next_item


def _checked_item_ids() -> set[int]:
    settings = Setting.query.filter(Setting.key.startswith(CHECK_SETTING_PREFIX)).all()
    checked_ids: set[int] = set()
    for setting in settings:
        raw_id = setting.key.removeprefix(CHECK_SETTING_PREFIX)
        if raw_id.isdigit():
            checked_ids.add(int(raw_id))
    return checked_ids


def _checked_item_count() -> int:
    return Setting.query.filter(Setting.key.startswith(CHECK_SETTING_PREFIX)).count()


def _mark_checked(item: MediaItem, status: str) -> None:
    Setting.set(f"{CHECK_SETTING_PREFIX}{item.id}", f"{status}:{utc_now().isoformat()}")


def _next_check_url(item: MediaItem) -> str:
    _, next_item = _check_neighbors(item)
    if next_item is not None:
        return url_for("main.check_item", item_id=next_item.id)
    return url_for("main.check_start")


def _tmdb_url_for(item: MediaItem | None) -> str | None:
    if item is None or item.tmdb_id is None:
        return None
    return f"https://www.themoviedb.org/{item.media_type}/{item.tmdb_id}"


def _parse_tmdb_reference(value: str, fallback_media_type: str) -> tuple[str, int] | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.isdigit():
        return fallback_media_type, int(cleaned)
    match = TMDB_REFERENCE_RE.search(cleaned)
    if match is None:
        return None
    return match.group(1).lower(), int(match.group(2))


def _update_required_personal_rating(item: MediaItem) -> bool:
    value = safe_float(request.form.get("personal_rating"))
    if value is None:
        flash("Add your score before moving to the next item.", "error")
        return False
    if value < current_app.config["PERSONAL_SCORE_MIN"] or value > current_app.config["PERSONAL_SCORE_MAX"]:
        flash(
            f"Your score must be between {current_app.config['PERSONAL_SCORE_MIN']} and {current_app.config['PERSONAL_SCORE_MAX']}.",
            "error",
        )
        return False
    item.personal_rating = value
    return True


def _safe_return_url(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("/") and not value.startswith("//"):
        return value
    return None
