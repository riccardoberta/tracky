from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Integer, create_engine, func, inspect, select, text
from sqlalchemy.engine import Connection, Engine, make_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tracky.config import BASE_DIR, normalize_database_url  # noqa: E402
from tracky.extensions import db  # noqa: E402
from tracky.models import User  # noqa: E402,F401
from tracky.utils import utc_now  # noqa: E402


DEFAULT_SOURCE_DATABASE_URL = "sqlite:///data/tracky.seed.sqlite3"
SKIPPED_TABLES = {"users"}


@dataclass(frozen=True)
class LoadSummary:
    source_url: str
    target_url: str
    copied_rows: dict[str, int]

    @property
    def total_rows(self) -> int:
        return sum(self.copied_rows.values())


def load_initial_database(source_url: str, target_url: str, *, force: bool = False) -> LoadSummary:
    normalized_source_url = normalize_database_url(source_url)
    normalized_target_url = normalize_database_url(target_url)
    _validate_source_database(normalized_source_url)
    if _same_sqlite_database(normalized_source_url, normalized_target_url):
        raise RuntimeError("Source and target point to the same SQLite database.")

    source_engine = create_engine(normalized_source_url)
    target_engine = create_engine(normalized_target_url)
    try:
        copied_rows = _copy_database(source_engine, target_engine, force=force)
    finally:
        source_engine.dispose()
        target_engine.dispose()
    return LoadSummary(
        source_url=normalized_source_url,
        target_url=normalized_target_url,
        copied_rows=copied_rows,
    )


def _copy_database(source_engine: Engine, target_engine: Engine, *, force: bool) -> dict[str, int]:
    db.metadata.create_all(target_engine)
    source_table_names = set(inspect(source_engine).get_table_names())
    tables = [
        table
        for table in db.metadata.sorted_tables
        if table.name in source_table_names and table.name not in SKIPPED_TABLES
    ]

    with target_engine.begin() as target_connection:
        populated_tables = _populated_tables(target_connection, tables)
        if populated_tables and not force:
            table_list = ", ".join(populated_tables)
            raise RuntimeError(
                f"Target database already contains data in: {table_list}. "
                "Use --force only if you want to replace those tables."
            )
        if force:
            for table in reversed(tables):
                target_connection.execute(table.delete())

        copied_rows: dict[str, int] = {}
        with source_engine.connect() as source_connection:
            for table in tables:
                rows = [dict(row._mapping) for row in source_connection.execute(select(table)).all()]
                if rows:
                    target_connection.execute(table.insert(), rows)
                copied_rows[table.name] = len(rows)

        _ensure_configured_user(target_connection)
        _reset_postgres_sequences(target_connection, [*tables, db.metadata.tables["users"]])

    return copied_rows


def _populated_tables(connection: Connection, tables) -> list[str]:
    populated = []
    for table in tables:
        row_count = connection.execute(select(func.count()).select_from(table)).scalar_one()
        if row_count:
            populated.append(table.name)
    return populated


def _ensure_configured_user(connection: Connection) -> None:
    username = os.getenv("APP_USERNAME")
    if not username:
        return
    users = db.metadata.tables["users"]
    existing = connection.execute(select(users.c.id).where(users.c.username == username)).first()
    if existing is not None:
        return
    now = utc_now()
    connection.execute(users.insert().values(username=username, created_at=now, updated_at=now))


def _reset_postgres_sequences(connection: Connection, tables) -> None:
    if connection.dialect.name != "postgresql":
        return

    preparer = connection.dialect.identifier_preparer
    for table in tables:
        primary_key_columns = list(table.primary_key.columns)
        if len(primary_key_columns) != 1:
            continue
        primary_key = primary_key_columns[0]
        if not isinstance(primary_key.type, Integer):
            continue

        sequence_name = connection.execute(
            text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
            {"table_name": table.name, "column_name": primary_key.name},
        ).scalar()
        if not sequence_name:
            continue

        formatted_table = preparer.format_table(table)
        formatted_column = preparer.quote(primary_key.name)
        max_id = connection.execute(text(f"SELECT MAX({formatted_column}) FROM {formatted_table}")).scalar()
        connection.execute(
            text("SELECT setval(CAST(:sequence_name AS regclass), :value, :is_called)"),
            {
                "sequence_name": sequence_name,
                "value": max_id or 1,
                "is_called": bool(max_id),
            },
        )


def _validate_source_database(source_url: str) -> None:
    source_path = _sqlite_database_path(source_url)
    if source_path is not None and not source_path.exists():
        raise RuntimeError(f"Source database does not exist: {source_path}")


def _same_sqlite_database(source_url: str, target_url: str) -> bool:
    source_path = _sqlite_database_path(source_url)
    target_path = _sqlite_database_path(target_url)
    if source_path is None or target_path is None:
        return False
    return source_path.resolve() == target_path.resolve()


def _sqlite_database_path(database_url: str) -> Path | None:
    if database_url == "sqlite:///:memory:" or not database_url.startswith("sqlite:///"):
        return None
    path_text = database_url.removeprefix("sqlite:///").split("?", 1)[0]
    database_path = Path(path_text)
    if not database_path.is_absolute():
        database_path = BASE_DIR / database_path
    return database_path


def _display_url(database_url: str) -> str:
    return make_url(database_url).render_as_string(hide_password=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load Tracky's initial local SQLite data into a persistent database.")
    parser.add_argument(
        "--source-url",
        default=os.getenv("TRACKY_INITIAL_SOURCE_DATABASE_URL", DEFAULT_SOURCE_DATABASE_URL),
        help="Source database URL. Defaults to sqlite:///data/tracky.seed.sqlite3.",
    )
    parser.add_argument(
        "--target-url",
        default=os.getenv("DATABASE_URL"),
        help="Target persistent database URL. Defaults to DATABASE_URL.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing Tracky data tables in the target database before copying.",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv(BASE_DIR / ".env")
    args = _parse_args()
    if not args.target_url:
        print("DATABASE_URL or --target-url is required.", file=sys.stderr)
        return 2

    try:
        summary = load_initial_database(args.source_url, args.target_url, force=args.force)
    except RuntimeError as exc:
        print(f"Initial database load failed: {exc}", file=sys.stderr)
        return 1

    print(f"Source: {_display_url(summary.source_url)}")
    print(f"Target: {_display_url(summary.target_url)}")
    print(f"Copied rows: {summary.total_rows}")
    for table_name, row_count in summary.copied_rows.items():
        print(f"- {table_name}: {row_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
