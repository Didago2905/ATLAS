"""Synthetic in-memory vocabulary fixtures; no source files, databases or network."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import unittest
from unittest.mock import patch

from app.editorial.candidate_lookup import BeerCandidate, MuseumSource, MuseumVocabularyCandidate
from app.editorial import typo_suggestions as suggestions


def candidate(value, field="brewery", artwork="fixture-artwork"):
    reference = MuseumSource(artwork, 2, "brewery" if field == "brewery" else "beer_style",
                             "probable", "Original evidence", "tap_list", False)
    return MuseumVocabularyCandidate(field, value, "exact", (reference,))


class TypoSuggestionTests(unittest.TestCase):
    def test_short_ipa_uses_normalized_match_without_fuzzy(self):
        vocabulary = [candidate("IPA", "style"), candidate("Imperial IPA", "style")]
        with patch.object(suggestions, "_distance", side_effect=AssertionError("Fuzzy must not run")):
            result = suggestions.suggest_vocabulary("ipa", field="style", candidates=vocabulary)
        self.assertEqual([(r.candidate.value, r.match) for r in result], [("IPA", "normalized")])

    def test_exact_match_ranks_first_and_bypasses_fuzzy(self):
        vocabulary = [candidate("TIBURON"), candidate("Tiburón"), candidate("Tiburonx")]
        with patch.object(suggestions, "_distance", side_effect=AssertionError("Fuzzy must not run")):
            result = suggestions.suggest_vocabulary("Tiburón", field="brewery", candidates=vocabulary)
        self.assertEqual([r.match for r in result], ["exact", "normalized"])
        self.assertEqual(result[0].candidate.value, "Tiburón")

    def test_ciprez_suggests_cyprez(self):
        value = candidate("Cyprez")
        result = suggestions.suggest_vocabulary("ciprez", field="brewery", candidates=[value])
        self.assertEqual(len(result), 1)
        self.assertIs(result[0].candidate, value)
        self.assertEqual((result[0].match, result[0].edit_distance), ("fuzzy", 1))

    def test_wentland_suggests_wendlandt_without_confirming_identity(self):
        result = suggestions.suggest_vocabulary("wentland", field="brewery", candidates=[candidate("Wendlandt")])
        self.assertEqual([r.candidate.value for r in result], ["Wendlandt"])
        self.assertEqual(result[0].edit_distance, 2)
        self.assertFalse(hasattr(result[0], "confirmation"))

    def test_distinct_ipa_styles_are_not_equated(self):
        values = ("IPA", "Double IPA", "Imperial IPA", "Triple IPA")
        for query in values:
            other = [candidate(v, "style") for v in values if v != query]
            with self.subTest(query=query):
                self.assertEqual(suggestions.suggest_vocabulary(query, field="style", candidates=other), ())

    def test_style_typo_preserves_words_and_acronyms(self):
        vocabulary = [candidate("Imperial IPA", "style")]
        result = suggestions.suggest_vocabulary("Imperal IPA", field="style", candidates=vocabulary)
        self.assertEqual(result[0].candidate.value, "Imperial IPA")
        for query in ("Imperial IPL", "Imperial", "Triple Imperial IPA"):
            with self.subTest(query=query):
                self.assertEqual(suggestions.suggest_vocabulary(query, field="style", candidates=vocabulary), ())

    def test_short_queries_do_not_run_fuzzy(self):
        with patch.object(suggestions, "_distance", side_effect=AssertionError("Short fuzzy forbidden")):
            for query in ("i", "ip", "cyp"):
                self.assertEqual(suggestions.suggest_vocabulary(query, field="brewery", candidates=[candidate("Cyprez")]), ())

    def test_ambiguous_spellings_return_empty_without_arbitrary_selection(self):
        values = [candidate("Cyprez"), candidate("Cipres")]
        self.assertEqual(suggestions.suggest_vocabulary("ciprez", field="brewery", candidates=values), ())

    def test_semantic_fields_are_not_cross_matched(self):
        self.assertEqual(suggestions.suggest_vocabulary("ciprez", field="brewery", candidates=[candidate("Cyprez", "style")]), ())
        self.assertEqual(suggestions.suggest_vocabulary("ipa", field="style", candidates=[candidate("IPA", "brewery")]), ())

    def test_no_candidates_or_weak_candidates_return_empty(self):
        self.assertEqual(suggestions.suggest_vocabulary("ciprez", field="brewery", candidates=[]), ())
        self.assertEqual(suggestions.suggest_vocabulary("ciprez", field="brewery", candidates=[candidate("Otra cervecería")]), ())

    def test_input_spelling_provenance_and_candidates_are_unchanged(self):
        query = "  Ciprez  "
        values = [candidate("Cyprez")]
        before = deepcopy(values)
        with patch("sqlite3.connect", side_effect=AssertionError("No database access")), \
                patch("socket.socket.connect", side_effect=AssertionError("No network access")), \
                patch("builtins.open", side_effect=AssertionError("No file access")):
            result = suggestions.suggest_vocabulary(query, field="brewery", candidates=values)
        self.assertEqual(result[0].original_input, query)
        self.assertIs(result[0].candidate.references, values[0].references)
        self.assertEqual(values, before)
        self.assertEqual(result[0].candidate.references[0].confidence, "probable")
        with self.assertRaises(FrozenInstanceError):
            result[0].match = "exact"

    def test_at_most_three_without_merging_orthographic_sources(self):
        values = [candidate(v, artwork=str(index)) for index, v in enumerate(("Cyprez", "CYPREZ", "Cypréz", "CypRéz"))]
        result = suggestions.suggest_vocabulary("ciprez", field="brewery", candidates=values)
        self.assertEqual(len(result), 3)
        self.assertTrue(all(any(r.candidate is v for v in values) for r in result))
        self.assertTrue(all(len(r.candidate.references) == 1 for r in result))

    def test_input_order_does_not_change_ranking(self):
        values = [candidate("Cyprez"), candidate("CYPREZ")]
        result = suggestions.suggest_vocabulary("ciprez", field="brewery", candidates=values)
        self.assertEqual(result, suggestions.suggest_vocabulary("ciprez", field="brewery", candidates=reversed(values)))

    def test_invalid_queries_fields_and_identity_candidates_are_rejected(self):
        for query in (None, "", "  ", "x" * 256):
            with self.subTest(query=query), self.assertRaises(ValueError):
                suggestions.suggest_vocabulary(query, field="brewery", candidates=[])
        with self.assertRaises(ValueError):
            suggestions.suggest_vocabulary("IPA", field="name", candidates=[])
        with self.assertRaises(ValueError):
            suggestions.suggest_vocabulary("IPA", field="style", candidates=[BeerCandidate(1, "IPA", "Marca", "IPA", True, False, "exact")])


if __name__ == "__main__":
    unittest.main()
