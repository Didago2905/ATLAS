"""Read-only candidates, never identity confirmations or canonical vocabulary.

Sources must be supplied explicitly. Importing this module does not load ATLAS
configuration, the operational engine, publication services or Telegram.
"""
from contextlib import closing, contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Literal
import unicodedata

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

Match = Literal["exact", "normalized"]
VocabularyField = Literal["brewery", "style"]


class CandidateLookupError(ValueError):
    """Fixed source errors without SQL, credentials or private payloads."""


@dataclass(frozen=True)
class BeerCandidate:
    beer_id: int
    name: str | None
    brewery: str | None
    style: str | None
    is_available: bool | None
    is_deleted: bool | None
    match: Match
    source: Literal["sql"] = "sql"


@dataclass(frozen=True)
class MuseumSource:
    artwork_id: str
    product_index: int
    source_field: Literal["brewery", "beer_style"]
    confidence: str | None
    evidence: str | None
    collection: str | None
    published: bool | None


@dataclass(frozen=True)
class MuseumVocabularyCandidate:
    field: VocabularyField
    value: str
    match: Match
    references: tuple[MuseumSource, ...]
    source: Literal["museum"] = "museum"


def _key(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", value).casefold()
                   if not unicodedata.combining(c)).strip()


def _query(value: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 255:
        raise ValueError("Lookup requires a nonblank string of at most 255 characters")


def _options(mode: Match, limit: int) -> None:
    if mode not in ("exact", "normalized"):
        raise ValueError("Only exact and normalized lookup are supported")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Candidate limit must be an integer from 1 to 100")


def _match(value: str | None, query: str, mode: Match) -> Match | None:
    if value == query:
        return "exact"
    if mode == "normalized" and isinstance(value, str) and _key(value) == _key(query):
        return "normalized"
    return None


def _flag(value) -> bool | None:
    if value is None:
        return None
    if type(value) not in (int, bool) or value not in (0, 1):
        raise CandidateLookupError("Catalog contains an invalid availability/deletion flag")
    return bool(value)


def _sqlite_file(database_url: str) -> Path:
    try:
        parsed = make_url(database_url)
        if parsed.drivername not in ("sqlite", "sqlite+pysqlite") or not parsed.database \
                or parsed.database == ":memory:" or parsed.query or parsed.host or parsed.username or parsed.password:
            raise ValueError()
        path = Path(parsed.database).resolve(strict=True)
        if not path.is_file():
            raise ValueError()
        return path
    except (ValueError, TypeError, OSError, ArgumentError):
        raise CandidateLookupError("An existing explicit SQLite file URL is required") from None


@contextmanager
def _catalog_connection(database_url):
    path = _sqlite_file(database_url)
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=15)) as connection:
            connection.execute("PRAGMA query_only=ON")
            if connection.execute("SELECT query_only FROM pragma_query_only").fetchone() != (1,):
                raise CandidateLookupError("Read-only catalog protection unavailable")

            def authorize(action, table, column, database, trigger):
                if action == sqlite3.SQLITE_READ:
                    return sqlite3.SQLITE_OK if table == "beers" else sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_FUNCTION) else sqlite3.SQLITE_DENY

            connection.set_authorizer(authorize)
            connection.row_factory = sqlite3.Row
            yield connection
    except sqlite3.Error:
        raise CandidateLookupError("Cannot read beer candidates from the supplied catalog") from None


def read_commercial_beer(database_url, beer_id):
    """Allowlisted current commercial snapshot. No ORM or operational engine."""
    if type(beer_id) is not int or not 0 < beer_id < 2**63:
        raise CandidateLookupError("A positive beer ID is required")
    with _catalog_connection(database_url) as connection:
        row = connection.execute("SELECT name,brewery,style,origin,color,description,abv,ibu,prices,is_deleted "
                                 "FROM beers WHERE id=?", (beer_id,)).fetchone()
    if row is None or _flag(row['is_deleted']) is not False:
        raise CandidateLookupError("Beer unavailable for commercial preparation")
    result = dict(row)
    result.pop('is_deleted')
    if isinstance(result['prices'], str):
        try:
            result['prices'] = json.loads(result['prices'])
        except (ValueError, TypeError):
            raise CandidateLookupError("Invalid catalog prices") from None
    if result['prices'] is not None and not isinstance(result['prices'], dict):
        raise CandidateLookupError("Invalid catalog prices")
    return result


def lookup_beers(database_url: str, *, name: str, brewery: str | None = None,
                 style: str | None = None, mode: Match = "normalized", limit: int = 10,
                 include_deleted: bool = True, beer_id: int | None = None) -> tuple[BeerCandidate, ...]:
    """AND-match supplied identity fields; include unavailable and label deleted.

    Exact means literal equality. Normalized additionally ignores case, accents
    and surrounding whitespace, without substring, punctuation or alias matching.
    Each invocation reads one SELECT snapshot; it never confirms an identity.
    """
    _options(mode, limit)
    filters = {"name": name}
    if brewery is not None:
        filters["brewery"] = brewery
    if style is not None:
        filters["style"] = style
    for value in filters.values():
        _query(value)
    if type(include_deleted) is not bool:
        raise ValueError("include_deleted must be boolean")
    if beer_id is not None and (type(beer_id) is not int or not 0 < beer_id < 2**63):
        raise ValueError("A positive beer ID is required")
    with _catalog_connection(database_url) as connection:
        rows = connection.execute("SELECT id,name,brewery,style,is_available,is_deleted FROM beers ORDER BY id").fetchall()
    candidates = []
    for row in rows:
        if beer_id is not None and row["id"] != beer_id:
            continue
        matches = [_match(row[field], value, mode) for field, value in filters.items()]
        if any(match is None for match in matches):
            continue
        deleted = _flag(row["is_deleted"])
        if deleted is True and not include_deleted:
            continue
        if type(row["id"]) is not int or not 0 < row["id"] < 2**63 \
                or any(value is not None and not isinstance(value, str) for value in
                       (row["name"], row["brewery"], row["style"])):
            raise CandidateLookupError("Catalog contains an invalid beer candidate")
        candidates.append(BeerCandidate(row["id"], row["name"], row["brewery"], row["style"],
                                        _flag(row["is_available"]), deleted,
                                        "exact" if all(match == "exact" for match in matches) else "normalized"))
    return tuple(sorted(candidates, key=lambda item: (item.match != "exact", item.beer_id))[:limit])


def lookup_museum_vocabulary(registry: Path, *, field: VocabularyField, query: str,
                             mode: Match = "normalized", limit: int = 10) -> tuple[MuseumVocabularyCandidate, ...]:
    """Read brewery/style semantic values; retain distinct original spellings.

    Confidence does not confirm an identity or promote a probable attribution.
    Historical/unpublished sources are retained and labeled. No fallback to an
    artwork title or top-level style is inferred for legacy entries.
    """
    _options(mode, limit)
    _query(query)
    if field not in ("brewery", "style"):
        raise ValueError("Museum vocabulary supports only brewery and style")
    try:
        with Path(registry).open("rb") as source:
            raw = source.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError()
        entries = json.loads(raw)
        if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
            raise ValueError()
        source_field = "brewery" if field == "brewery" else "beer_style"
        grouped: dict[str, list[MuseumSource]] = {}
        for entry in entries:
            products = entry.get("semantic_products")
            if products is None or products == "":
                continue
            if isinstance(products, str):
                products = json.loads(products)
            if products is None:
                continue
            if not isinstance(products, list) or any(not isinstance(product, dict) for product in products):
                raise ValueError()
            for index, product in enumerate(products):
                metadata = product.get(source_field)
                if metadata is None:
                    continue
                if not isinstance(metadata, dict):
                    raise ValueError()
                value = metadata.get("value")
                if value is None:
                    continue
                if not isinstance(value, str):
                    raise ValueError()
                if not value.strip() or _match(value, query, mode) is None:
                    continue
                artwork_id = entry.get("id")
                confidence, evidence = metadata.get("confidence"), metadata.get("evidence")
                collection = entry.get("category") or entry.get("type")
                published = entry.get("published")
                if not isinstance(artwork_id, str) or not artwork_id.strip() \
                        or any(v is not None and not isinstance(v, str) for v in (confidence, evidence, collection)) \
                        or published is not None and type(published) is not bool:
                    raise ValueError()
                grouped.setdefault(value, []).append(MuseumSource(
                    artwork_id, index, source_field, confidence, evidence, collection, published))
        candidates = [MuseumVocabularyCandidate(field, value, _match(value, query, mode), tuple(refs))
                      for value, refs in grouped.items()]
        return tuple(sorted(candidates, key=lambda item: (item.match != "exact", item.value))[:limit])
    except (OSError, ValueError, TypeError):
        raise CandidateLookupError("Cannot read semantic vocabulary from the supplied Museum registry") from None
