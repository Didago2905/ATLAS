"""Dedicated nonsecret local configuration; never reads Operations, Incidents or .env."""
import json
import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from app.editorial.production_execution import ProductionExecutionConfig

REPO = Path(__file__).resolve().parents[2]
KNOWN_PERMISSIONS = {"artwork.submit", "beer.create", "beer.edit", "beer.commercial.apply", "event.prepare"}
STORAGE = REPO / "data/editorial"


class EditorialSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ATLAS_EDITORIAL_", env_file=None,
                                     extra="forbid", hide_input_in_errors=True)
    enabled: bool = False
    database_url: str | None = "sqlite:///" + (STORAGE / "storage/editorial.sqlite3").as_posix()
    media_root: Path = STORAGE / "storage/media"
    chat_id: int | None = None
    permissions_file: Path | None = STORAGE / "permissions.json"
    download_limit_bytes: int = Field(default=15 * 1024 * 1024, ge=1, le=100 * 1024 * 1024)
    catalog_database_url: str | None = None  # Explicit read-only identity source; never the Editorial engine.
    commercial_execution: ProductionExecutionConfig = Field(default_factory=ProductionExecutionConfig)

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
        # Environment can explicitly disable a local file at any time.
        return env_settings, init_settings


def load_settings():
    """Optional NONSECRET local configuration. No token field is accepted."""
    path = Path(os.environ.get("ATLAS_EDITORIAL_CONFIG_FILE", STORAGE / "settings.json"))
    if not path.exists():
        return EditorialSettings()
    private_root(path.parent)
    with path.open("rb") as source:
        raw = source.read(32 * 1024 + 1)
    if len(raw) > 32 * 1024:
        raise ValueError("Oversized Editorial configuration")
    values = json.loads(raw)
    if not isinstance(values, dict):
        raise ValueError("Invalid Editorial configuration")
    return EditorialSettings(**values)


def sqlite_path(url):
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or not parsed.database or parsed.database == ":memory:" or parsed.query:
        raise ValueError("Editorial requires an explicit SQLite file")
    return Path(parsed.database).resolve()


def dedicated_database(url):
    parsed = make_url(url)
    if parsed.database and Path(parsed.database).name.lower() == "atlas.db":
        raise ValueError("Editorial must use a dedicated database")
    path = sqlite_path(url)
    if path.name.lower() == "atlas.db":
        raise ValueError("Editorial must use a dedicated database")
    private_root(path.parent)
    return path


def private_root(path):
    root = Path(path).resolve()
    for public in (REPO / "static", REPO / "frontend", REPO / "build"):
        if root == public.resolve() or public.resolve() in root.parents or root in public.resolve().parents:
            raise ValueError("Editorial media must be outside public roots")
    return root


class Authorization:
    def __init__(self, chat_id, grants):
        if type(chat_id) is not int or chat_id >= 0:
            raise ValueError("Use a numeric private group ID")
        self.chat_id = chat_id
        self.grants = {}
        if not isinstance(grants, dict) or len(grants) > 100:
            raise ValueError("Invalid permission map")
        for key, permissions in grants.items():
            if not isinstance(key, str) or not key.isdecimal() or int(key) <= 0 or str(int(key)) != key \
                    or not isinstance(permissions, list) or not permissions \
                    or any(not isinstance(p, str) or p not in KNOWN_PERMISSIONS for p in permissions):
                raise ValueError("Invalid permission grant")
            self.grants[int(key)] = frozenset(permissions)

    @classmethod
    def load(cls, settings):
        path = settings.permissions_file
        if path is None or path.stat().st_size > 32 * 1024:
            raise ValueError("A bounded private permissions file is required")
        with path.open("rb") as source:
            raw = source.read(32 * 1024 + 1)
        if len(raw) > 32 * 1024:
            raise ValueError("Oversized permission map")
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate permission identity")
                result[key] = value
            return result
        return cls(settings.chat_id, json.loads(raw, object_pairs_hook=unique_pairs))

    def allows(self, chat_id, user_id, permission="artwork.submit"):
        return type(chat_id) is int and type(user_id) is int and chat_id == self.chat_id \
            and permission in self.grants.get(user_id, ())
