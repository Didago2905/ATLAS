"""Pure spelling suggestions over already-loaded Phase 2A vocabulary candidates."""
from dataclasses import dataclass
from typing import Iterable, Literal

from app.editorial.candidate_lookup import MuseumVocabularyCandidate, VocabularyField, _key, _match, _query


@dataclass(frozen=True)
class VocabularySuggestion:
    original_input: str
    candidate: MuseumVocabularyCandidate
    match: Literal["exact", "normalized", "fuzzy"]
    edit_distance: int


def _distance(left: str, right: str, maximum: int) -> int:
    """Bounded Levenshtein distance, not a semantic similarity or alias rule."""
    if abs(len(left) - len(right)) > maximum:
        return maximum + 1
    row = list(range(len(right) + 1))
    for index, char in enumerate(left, 1):
        next_row = [index]
        for column, other in enumerate(right, 1):
            next_row.append(min(next_row[-1] + 1, row[column] + 1, row[column - 1] + (char != other)))
        if min(next_row) > maximum:
            return maximum + 1
        row = next_row
    return row[-1]


def suggest_vocabulary(query: str, *, field: VocabularyField,
                       candidates: Iterable[MuseumVocabularyCandidate]) -> tuple[VocabularySuggestion, ...]:
    """Return at most three suggestions, without lookup, mutation or confirmation.

    Exact/normalized matches bypass fuzzy work, including for short queries. Fuzzy
    matching permits one edit for short words or two for inputs of 8+ characters.
    Word count and initials must agree; short tokens (IPA, IPL, BA, DDH) must match
    exactly. Near-tied best spellings suppress fuzzy suggestions rather than picking
    an arbitrary winner. Orthographic variants keep their separate source objects.
    """
    _query(query)
    if field not in ("brewery", "style"):
        raise ValueError("Suggestions support only brewery and style")
    pool = tuple(candidates)
    if any(not isinstance(candidate, MuseumVocabularyCandidate) for candidate in pool):
        raise ValueError("Suggestions require vocabulary candidates, not beer identities")
    pool = tuple(candidate for candidate in pool if candidate.field == field)
    direct = [VocabularySuggestion(query, candidate, match, 0) for candidate in pool
              if (match := _match(candidate.value, query, "normalized")) is not None]
    if direct:
        return tuple(sorted(direct, key=lambda item: (item.match != "exact", item.candidate.value))[:3])
    key = _key(query)
    if len(key) <= 3:
        return ()
    words = key.split()
    maximum = 1 if len(key) < 8 else 2
    ranked = []
    for candidate in pool:
        value = _key(candidate.value)
        other_words = value.split()
        if len(value) > 255 or len(words) != len(other_words):
            continue
        if any(a[0] != b[0] or (min(len(a), len(b)) <= 3 and a != b)
               for a, b in zip(words, other_words)):
            continue
        distance = _distance(key, value, maximum)
        if distance > maximum:
            continue
        score = 1 - distance / max(len(key), len(value))
        if score >= 0.75:
            ranked.append((score, value, VocabularySuggestion(query, candidate, "fuzzy", distance)))
    ranked.sort(key=lambda item: (-item[0], item[2].edit_distance, item[2].candidate.value))
    if ranked and any(value != ranked[0][1] and ranked[0][0] - score <= 0.05
                      for score, value, _ in ranked[1:]):
        return ()
    return tuple(item[2] for item in ranked[:3])
