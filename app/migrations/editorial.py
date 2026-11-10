"""Explicit additive v1 -> v2 migration; never imports the operational engine."""
import argparse
from pathlib import Path
from sqlalchemy import create_engine, inspect
from app.editorial.models import Base, Cursor
from app.editorial.config import dedicated_database
from app.editorial.instance import EditorialInstance

V2_TABLES = {"editorial_proposals", "editorial_interviews"}
LEGACY_TABLES = set(Base.metadata.tables) - V2_TABLES


def check_schema(connection, *, legacy=False):
    inspector = inspect(connection)
    for table in Base.metadata.sorted_tables:
        if legacy and table.name in V2_TABLES:
            continue
        if not inspector.has_table(table.name):
            raise ValueError("Editorial migration required")
        actual = inspector.get_columns(table.name)
        expected = list(table.columns)
        if {c["name"] for c in actual} != {c.name for c in expected}:
            raise ValueError("Unsupported Editorial schema")
        for column in actual:
            model = table.columns[column["name"]]
            if str(column["type"]).upper() != model.type.compile(dialect=connection.dialect).upper() \
                    or column["nullable"] != model.nullable:
                raise ValueError("Unsupported Editorial column")
        if inspector.get_pk_constraint(table.name)["constrained_columns"] != [c.name for c in expected if c.primary_key]:
            raise ValueError("Unsupported Editorial primary key")
        wanted = {tuple(c.name for c in constraint.columns) for constraint in table.constraints
                  if constraint.__class__.__name__ == "UniqueConstraint"}
        found = {tuple(c["column_names"]) for c in inspector.get_unique_constraints(table.name)}
        if not wanted.issubset(found):
            raise ValueError("Unsupported Editorial uniqueness")
        wanted_foreign = {(tuple(c.parent.name for c in constraint.elements),
                           constraint.referred_table.name, tuple(c.column.name for c in constraint.elements))
                          for constraint in table.foreign_key_constraints}
        found_foreign = {(tuple(c["constrained_columns"]), c["referred_table"], tuple(c["referred_columns"]))
                         for c in inspector.get_foreign_keys(table.name)}
        if wanted_foreign != found_foreign:
            raise ValueError("Unsupported Editorial references")
    row = connection.exec_driver_sql("SELECT schema_version FROM editorial_cursor WHERE id=1").first()
    if not row or row[0] != (1 if legacy else 2):
        raise ValueError("Unsupported Editorial version")


def migrate(engine):
    if engine.dialect.name != "sqlite":
        raise ValueError("SQLite required")
    with engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            existing = set(inspect(connection).get_table_names()) & set(Base.metadata.tables)
            if existing:
                if existing == LEGACY_TABLES:
                    check_schema(connection, legacy=True)
                    for table in Base.metadata.sorted_tables:
                        if table.name in V2_TABLES:
                            table.create(connection)
                    connection.exec_driver_sql("UPDATE editorial_cursor SET schema_version=2 WHERE id=1")
                check_schema(connection)  # Partial/incompatible schemas fail closed.
            else:
                Base.metadata.create_all(connection)
                connection.execute(Cursor.__table__.insert().values(id=1, next_offset=0, schema_version=2))
                check_schema(connection)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def main():
    parser = argparse.ArgumentParser(description="Explicit Editorial schema creation; back up existing storage first")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--create", action="store_true")
    args = parser.parse_args()
    path = args.database.resolve()
    if not path.is_file() and not args.create:
        parser.error("Missing database; --create is required for new storage")
    engine = create_engine("sqlite:///" + path.as_posix())
    try:
        dedicated_database("sqlite:///" + path.as_posix())
        with EditorialInstance("sqlite:///" + path.as_posix()):
            migrate(engine)
        print("Editorial v2 schema ready; no catalog or Museum publication performed")
        return 0
    except Exception:
        print("Editorial migration failed; transaction rolled back; inspect schema offline")
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
