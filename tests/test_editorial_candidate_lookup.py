"""Read-only candidate adapters: synthetic SQLite/JSON only, no live configuration."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app.editorial import candidate_lookup as lookup


class CandidateLookupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog = self.root / "catalog#fixture.sqlite3"
        self.url = "sqlite:///" + self.catalog.as_posix()
        connection = sqlite3.connect(self.catalog)
        try:
            connection.execute("CREATE TABLE beers(id INTEGER PRIMARY KEY,name TEXT,brewery TEXT,style TEXT,is_available BOOLEAN,is_deleted BOOLEAN)")
            connection.executemany("INSERT INTO beers VALUES(?,?,?,?,?,?)", [
                (1, "Ámbar", "Tiburón", "IPA", 1, 0),
                (2, "AMBAR", "TIBURON", "Ipa", 0, 0),
                (3, "Ámbar", "Tiburón", "IPA", 0, 1),
                (4, "Ámbar", "Otra", "Porter", 1, 0),
                (5, "Ámbar", "Tiburón", "IPA", None, None),
                (6, "Leviatán", "Tiburón", "Double IPA", 0, 0),
            ])
            connection.commit()
        finally:
            connection.close()
        self.registry = self.root / "museum.json"
        self.entries = [
            {"id": "art-one", "category": "tap_list", "published": False, "semantic_products": json.dumps([
                {"brewery": {"value": "Tiburón", "confidence": "probable", "evidence": "Atribución sin promover"},
                 "beer_style": {"value": "IPA", "confidence": "confirmed", "evidence": "Texto visible"}}])},
            {"id": "art-two", "type": "botellas", "semantic_products": [
                {"brewery": {"value": "TIBURON", "confidence": "confirmed", "evidence": "MARCA ORIGINAL"},
                 "beer_style": {"value": "Ipa", "confidence": "unknown", "evidence": "Sin confirmar"}}]},
            {"id": "art-three", "category": "carta_nueva", "published": True, "semantic_products": [
                {"brewery": {"value": "Tiburón", "confidence": "confirmed", "evidence": "Otra obra"},
                 "beer_style": {"value": "Imperial IPA", "confidence": "confirmed", "evidence": "Estilo diferente"}}]},
            {"id": "legacy", "name": "Otra cervecería", "style": "Inventado", "semantic_products": ""},
            {"id": "empty"},
        ]
        self.write_registry()
        guard = patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden"))
        guard.start()
        self.addCleanup(guard.stop)

    def write_registry(self):
        self.registry.write_text(json.dumps(self.entries, ensure_ascii=False), encoding="utf-8")

    def test_exact_identity_matches_all_supplied_fields_without_confirming(self):
        result = lookup.lookup_beers(self.url, name="Ámbar", brewery="Tiburón", style="IPA", mode="exact")
        self.assertEqual([c.beer_id for c in result], [1, 3, 5])
        self.assertEqual(result[0].name, "Ámbar")
        self.assertEqual(result[0].brewery, "Tiburón")
        self.assertEqual(result[0].style, "IPA")
        self.assertEqual(result[0].source, "sql")
        self.assertTrue(all(c.match == "exact" for c in result))
        self.assertFalse(hasattr(result[0], "confirmation"))
        with self.assertRaises(FrozenInstanceError):
            result[0].name = "Modified"

    def test_normalized_identity_preserves_original_spelling_and_unavailable_beers(self):
        result = lookup.lookup_beers(self.url, name="ambar", brewery="tiburon", style="ipa")
        self.assertEqual([c.beer_id for c in result], [1, 2, 3, 5])
        self.assertEqual(result[1].name, "AMBAR")
        self.assertEqual(result[1].brewery, "TIBURON")
        self.assertFalse(result[1].is_available)
        self.assertIsNone(result[-1].is_available)
        self.assertIsNone(result[-1].is_deleted)

    def test_deleted_records_are_labeled_and_can_be_explicitly_excluded(self):
        all_candidates = lookup.lookup_beers(self.url, name="Ámbar", mode="exact")
        self.assertTrue(next(c for c in all_candidates if c.beer_id == 3).is_deleted)
        filtered = lookup.lookup_beers(self.url, name="Ámbar", mode="exact", include_deleted=False)
        self.assertEqual([c.beer_id for c in filtered], [1, 4, 5])

    def test_exact_results_rank_before_normalized_and_limits_are_stable(self):
        self.assertEqual(lookup.lookup_beers(self.url, name="AMBAR", limit=1)[0].beer_id, 2)
        self.assertEqual([c.beer_id for c in lookup.lookup_beers(self.url, name="AMBAR")], [2, 1, 3, 4, 5])

    def test_no_substring_fuzzy_alias_or_cross_field_identity_lookup(self):
        for name in ("Leviatan typo", "Levia", "IPA", "Tiburón", "Ámbar' OR 1=1 --"):
            self.assertEqual(lookup.lookup_beers(self.url, name=name), ())
        self.assertEqual(lookup.lookup_beers(self.url, name="Ámbar", brewery="Otra", style="IPA"), ())

    def test_missing_non_sqlite_and_invalid_sources_never_create_a_database(self):
        missing = self.root / "missing.sqlite3"
        for url in ("sqlite:///" + missing.as_posix(), "sqlite:///:memory:", self.url + "?mode=rw",
                    "postgresql://user:secret@invalid/catalog", "not a database URL"):
            with self.subTest(url=url), self.assertRaises(lookup.CandidateLookupError) as caught:
                lookup.lookup_beers(url, name="Ámbar")
            self.assertNotIn("secret", str(caught.exception))
        self.assertFalse(missing.exists())

    def test_connection_is_read_only_query_only_authorized_and_closed(self):
        original_connect = sqlite3.connect
        calls, states = [], []
        test = self
        class GuardConnection(sqlite3.Connection):
            def set_authorizer(self, callback):
                test.assertEqual(self.execute("PRAGMA query_only").fetchone(), (1,))
                with test.assertRaises(sqlite3.OperationalError):
                    self.execute("UPDATE beers SET name='forbidden'")
                result = super().set_authorizer(callback)
                with test.assertRaises(sqlite3.DatabaseError):
                    self.execute("DELETE FROM beers")
                states.append("guarded")
                return result

            def close(self):
                states.append("closed")
                return super().close()

        def connect(*args, **kwargs):
            calls.append((args, deepcopy(kwargs)))
            return original_connect(*args, **kwargs, factory=GuardConnection)

        before = self.catalog.read_bytes()
        with patch.object(lookup.sqlite3, "connect", side_effect=connect):
            lookup.lookup_beers(self.url, name="Ámbar")
        self.assertIn("mode=ro", calls[0][0][0])
        self.assertIn("%23", calls[0][0][0])
        self.assertTrue(calls[0][1]["uri"])
        self.assertEqual(states, ["guarded", "closed"])
        self.assertEqual(self.catalog.read_bytes(), before)

    def test_schema_failure_has_sanitized_error_and_no_creation(self):
        empty = self.root / "empty.sqlite3"
        sqlite3.connect(empty).close()
        with self.assertRaises(lookup.CandidateLookupError) as caught:
            lookup.lookup_beers("sqlite:///" + empty.as_posix(), name="Ámbar")
        self.assertNotIn("SELECT", str(caught.exception))

    def test_museum_handles_encoded_and_native_products_and_preserves_references(self):
        result = lookup.lookup_museum_vocabulary(self.registry, field="brewery", query="Tiburón")
        self.assertEqual([c.value for c in result], ["Tiburón", "TIBURON"])
        self.assertEqual([r.artwork_id for r in result[0].references], ["art-one", "art-three"])
        ref = result[0].references[0]
        self.assertEqual((ref.product_index, ref.source_field), (0, "brewery"))
        self.assertEqual((ref.confidence, ref.evidence), ("probable", "Atribución sin promover"))
        self.assertFalse(ref.published)
        self.assertEqual(ref.collection, "tap_list")
        self.assertEqual(result[1].references[0].collection, "botellas")
        self.assertIsNone(result[1].references[0].published)
        self.assertEqual(result[0].field, "brewery")
        self.assertEqual(result[0].source, "museum")
        self.assertFalse(hasattr(result[0], "confirmation"))

    def test_museum_exact_lookup_never_merges_original_spellings(self):
        result = lookup.lookup_museum_vocabulary(self.registry, field="brewery", query="TIBURON", mode="exact")
        self.assertEqual([c.value for c in result], ["TIBURON"])
        self.entries.append({"id": "spaces", "semantic_products": [{"brewery": {"value": " Tiburón "}}]})
        self.write_registry()
        result = lookup.lookup_museum_vocabulary(self.registry, field="brewery", query="tiburon")
        self.assertEqual({c.value for c in result}, {"Tiburón", "TIBURON", " Tiburón "})

    def test_museum_style_and_brewery_indexes_are_separate(self):
        result = lookup.lookup_museum_vocabulary(self.registry, field="style", query="IPA")
        self.assertEqual([c.value for c in result], ["IPA", "Ipa"])
        self.assertEqual(result[0].references[0].source_field, "beer_style")
        self.assertEqual(lookup.lookup_museum_vocabulary(self.registry, field="brewery", query="IPA"), ())
        self.assertEqual(lookup.lookup_museum_vocabulary(self.registry, field="style", query="Tiburón"), ())
        self.assertEqual(lookup.lookup_museum_vocabulary(self.registry, field="style", query="Imperial"), ())
        self.assertEqual(lookup.lookup_museum_vocabulary(self.registry, field="style", query="Inventado"), ())

    def test_museum_limit_applies_to_candidates_not_provenance(self):
        result = lookup.lookup_museum_vocabulary(self.registry, field="brewery", query="Tiburón", limit=1)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0].references), 2)

    def test_malformed_registry_fails_without_returning_partial_or_raw_content(self):
        for raw in ('[{"private-marker":', '{}', '[{"id":"a","semantic_products":"bad-private-marker"}]',
                    '[{"id":"a","semantic_products":[{"brewery":{"value":5}}]}]',
                    '[{"semantic_products":[{"brewery":{"value":"Tiburón"}}]}]'):
            self.registry.write_text(raw, encoding="utf-8")
            with self.subTest(raw=raw), self.assertRaises(lookup.CandidateLookupError) as caught:
                lookup.lookup_museum_vocabulary(self.registry, field="brewery", query="Tiburón")
            self.assertNotIn("private-marker", str(caught.exception))

    def test_invalid_inputs_fail_before_source_access(self):
        for query in ("", "  ", None, "a" * 256):
            with self.subTest(query=query), self.assertRaises(ValueError):
                lookup.lookup_beers(self.url, name=query)
        for opts in ({"mode": "fuzzy"}, {"limit": 0}, {"limit": True}, {"limit": 101}):
            with self.subTest(opts=opts), self.assertRaises(ValueError):
                lookup.lookup_beers(self.url, name="Ámbar", **opts)
        with self.assertRaises(ValueError):
            lookup.lookup_beers(self.url, name="Ámbar", include_deleted="false")
        with self.assertRaises(ValueError):
            lookup.lookup_museum_vocabulary(self.registry, field="name", query="Ámbar")

    def test_both_sources_are_byte_identical_after_lookup(self):
        before = self.catalog.read_bytes(), self.registry.read_bytes()
        lookup.lookup_beers(self.url, name="Ámbar")
        lookup.lookup_museum_vocabulary(self.registry, field="brewery", query="tiburon")
        self.assertEqual((self.catalog.read_bytes(), self.registry.read_bytes()), before)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), [self.catalog.name, self.registry.name])


if __name__ == "__main__":
    unittest.main()
