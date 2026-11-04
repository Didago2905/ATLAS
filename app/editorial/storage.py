"""Explicit verified COPY of stopped Editorial storage. Never moves/deletes source."""
import argparse
from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile

from PIL import Image
from sqlalchemy import create_engine
from app.editorial.config import dedicated_database, private_root
from app.editorial.instance import EditorialInstance
from app.editorial.models import Base
from app.migrations.editorial import check_schema


def digest(path):
    value = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def snapshot(connection):
    tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if tables != set(Base.metadata.tables):
        raise ValueError("Source must contain only Editorial tables")
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise ValueError("Editorial integrity failed")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise ValueError("Editorial references failed")
    return {table: connection.execute(f'SELECT * FROM "{table}" ORDER BY id').fetchall()
            for table in sorted(Base.metadata.tables)}


def copy_storage(source_database, source_media, destination):
    source_database = dedicated_database("sqlite:///" + Path(source_database).resolve().as_posix())
    source_media, destination = private_root(source_media), private_root(destination)
    if not source_database.is_file() or not source_media.is_dir() or destination.exists():
        raise ValueError("Source required and destination must not exist")
    for source in (source_database.parent, source_media):
        if source == destination or source in destination.parents or destination in source.parents:
            raise ValueError("Source and destination trees must be separate")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Refuse to copy a running supported worker. OS-held lock releases even on crash.
    with EditorialInstance("sqlite:///" + source_database.as_posix()):
        staging = Path(tempfile.mkdtemp(prefix=".editorial-copy-", dir=destination.parent)).resolve()
        if staging.parent != destination.parent.resolve():
            raise ValueError("Unsafe staging location")
        target_db, target_media = staging / "editorial.sqlite3", staging / "media"
        target_media.mkdir()
        with closing(sqlite3.connect(source_database.as_uri() + "?mode=ro", uri=True)) as source:
            source.execute("BEGIN")
            before = snapshot(source)
            with closing(sqlite3.connect(target_db)) as target:
                source.backup(target)  # Consistent SQLite online backup, including WAL-visible data.
                if snapshot(target) != before:
                    raise ValueError("Database snapshot mismatch")
            columns = [row[1] for row in source.execute("PRAGMA table_info(editorial_assets)")]
            assets = [dict(zip(columns, row)) for row in before["editorial_assets"]]
            for asset in assets:
                key, extension = asset["digest"], asset["extension"]
                if not re.fullmatch(r"[a-f0-9]{64}", key) or extension not in {"jpg", "png", "webp", "tif", "bmp", "gif"}:
                    raise ValueError("Invalid private asset identity")
                for suffix in ("." + extension, ".preview.jpg"):
                    original, copied = source_media / (key + suffix), target_media / (key + suffix)
                    if original.resolve().parent != source_media or original.is_symlink():
                        raise ValueError("Unsafe private asset path")
                    source_digest = digest(original)
                    if suffix != ".preview.jpg" and (source_digest != key or original.stat().st_size != asset["byte_count"]):
                        raise ValueError("Source artwork integrity mismatch")
                    shutil.copyfile(original, copied)
                    if digest(copied) != source_digest or digest(original) != source_digest:
                        raise ValueError("Media changed during copy")
                    with Image.open(copied) as image:
                        image.verify()
                    if suffix == ".preview.jpg":
                        with Image.open(copied) as image:
                            if image.format != "JPEG" or image.size != (asset["width"], asset["height"]):
                                raise ValueError("Preview dimensions mismatch")
            if snapshot(source) != before:
                raise ValueError("Source snapshot changed")
        engine = create_engine("sqlite:///" + target_db.as_posix())
        try:
            with engine.connect() as connection:
                check_schema(connection)
        finally:
            engine.dispose()
        receipt = {"schema": 1, "table_counts": {name: len(rows) for name, rows in before.items()},
                   "asset_count": len(assets), "database_sha256": digest(target_db),
                   "database_bytes": target_db.stat().st_size, "source_retained": True,
                   "originals_and_previews_verified": True}
        (staging / "copy-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        if destination.exists():
            raise ValueError("Destination appeared during copy; no replacement allowed")
        # Only a new verified directory on the destination filesystem is renamed.
        # On failure retain staging for inspection; never remove any source data.
        os.rename(staging, destination)
        return receipt


def main():
    parser = argparse.ArgumentParser(description="Copy stopped Editorial DB and private assets to a NEW durable directory")
    parser.add_argument("--source-database", required=True, type=Path)
    parser.add_argument("--source-media", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    try:
        receipt = copy_storage(args.source_database, args.source_media, args.destination)
        print(json.dumps(receipt, indent=2))
        return 0
    except Exception:
        print("Editorial copy stopped; source retained; inspect destination staging privately; no activation performed")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
