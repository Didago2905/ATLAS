"""Additive, transactional SQLite migration. Does not import app.main."""
import argparse
from pathlib import Path

from sqlalchemy import create_engine, inspect

from app.models.issue_report import IssueReport

DELIVERY_COLUMNS = {
    "notification_attempts": "INTEGER NOT NULL DEFAULT 0",
    "notification_next_attempt_at": "DATETIME",
    "notification_lease_expires_at": "DATETIME",
    "notification_lease_token": "VARCHAR(36)",
    "notification_sent_at": "DATETIME",
    "telegram_message_id": "BIGINT",
    "notification_error_code": "VARCHAR(40)",
    "notification_destination": "VARCHAR(32) NOT NULL DEFAULT 'incidents'",
}
INDEX_NAME = "ix_issue_reports_delivery"
INDEX_COLUMNS = ["notification_state", "notification_destination", "notification_next_attempt_at",
                 "notification_lease_expires_at"]


class DeliverySchemaError(RuntimeError):
    def __init__(self):
        super().__init__("Unsupported issue report schema; inspect offline before migration or worker startup")


def _validate(connection, *, complete):
    entry = connection.exec_driver_sql("SELECT type FROM sqlite_master WHERE name='issue_reports'").first()
    if not entry or entry[0] != "table":
        raise DeliverySchemaError()
    columns = {row[1]: row for row in connection.exec_driver_sql('PRAGMA table_info("issue_reports")')}
    expected = {column.name: column for column in IssueReport.__table__.columns}
    base = set(expected) - set(DELIVERY_COLUMNS)
    if not base.issubset(columns) or set(columns) - set(expected):
        raise DeliverySchemaError()
    if complete and set(columns) != set(expected):
        raise DeliverySchemaError()
    for name, actual in columns.items():
        model = expected[name]
        wanted_type = model.type.compile(dialect=connection.dialect).upper()
        if actual[2].upper() != wanted_type or bool(actual[3]) != (not model.nullable) or bool(actual[5]) != model.primary_key:
            raise DeliverySchemaError()
        if name in DELIVERY_COLUMNS and model.server_default is not None:
            if str(actual[4]).strip("() ") != str(model.server_default.arg):
                raise DeliverySchemaError()
    unique_key = False
    # PRAGMA covers both inline UNIQUE and separately named unique indexes,
    # without depending on SQLAlchemy's parsing of historical CREATE SQL.
    for index in connection.exec_driver_sql('PRAGMA index_list("issue_reports")'):
        if index[2] and not index[4]:
            quoted = index[1].replace('"', '""')
            names = [item[2] for item in connection.exec_driver_sql(f'PRAGMA index_info("{quoted}")')]
            unique_key = unique_key or names == ["idempotency_key"]
    indexes = inspect(connection).get_indexes("issue_reports")
    if not unique_key:
        raise DeliverySchemaError()
    matching = [item for item in indexes if item["name"] == INDEX_NAME]
    if matching and (matching[0]["column_names"] != INDEX_COLUMNS or matching[0]["unique"]
                     or matching[0].get("dialect_options", {}).get("sqlite_where") is not None):
        raise DeliverySchemaError()
    if complete and not matching:
        raise DeliverySchemaError()
    return columns, bool(matching)


def check_delivery_schema(engine):
    if engine.dialect.name != "sqlite":
        raise DeliverySchemaError()
    with engine.connect() as connection:
        _validate(connection, complete=True)


def migrate(engine):
    if engine.dialect.name != "sqlite":
        raise DeliverySchemaError()
    with engine.connect() as connection:
        # Explicit BEGIN is needed for rollback of SQLite DDL and serializes
        # concurrent migration invocations before inspecting the schema.
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            exists = connection.exec_driver_sql("SELECT 1 FROM sqlite_master WHERE name='issue_reports'").first()
            added = []
            if not exists:
                IssueReport.__table__.create(connection)
                added = list(DELIVERY_COLUMNS)
            else:
                columns, indexed = _validate(connection, complete=False)
                for name, definition in DELIVERY_COLUMNS.items():
                    if name not in columns:
                        connection.exec_driver_sql(f'ALTER TABLE "issue_reports" ADD COLUMN "{name}" {definition}')
                        added.append(name)
                if not indexed:
                    names = ", ".join(f'"{name}"' for name in INDEX_COLUMNS)
                    connection.exec_driver_sql(f'CREATE INDEX "{INDEX_NAME}" ON "issue_reports" ({names})')
            _validate(connection, complete=True)
            connection.commit()
            return added
        except BaseException:
            connection.rollback()
            raise


def main():
    parser = argparse.ArgumentParser(description="Explicit issue delivery migration; back up the database first")
    parser.add_argument("--database", type=Path, required=True, help="Explicit local SQLite file path")
    parser.add_argument("--create", action="store_true", help="Allow a new SQLite file at the supplied path")
    args = parser.parse_args()
    target = args.database.resolve()
    if not target.is_file() and not args.create:
        parser.error("Database file missing; use --create only for intentional fresh storage")
    engine = create_engine("sqlite:///" + target.as_posix(), connect_args={"timeout": 15})
    try:
        added = migrate(engine)
        print(f"Issue delivery schema ready; added {len(added)} columns")
        return 0
    except Exception:
        # Never render SQLAlchemy exceptions: parameters may contain private data.
        print("Issue delivery migration failed; transaction rolled back. Inspect schema and backup offline.")
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
