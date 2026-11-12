"""Read-only preparation, not approval or an executable catalog write command."""
from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Literal, Mapping
from uuid import UUID

from pydantic import TypeAdapter

from app.editorial.candidate_lookup import read_commercial_beer, CandidateLookupError
from app.editorial.navigation_v22 import NavigationState, assert_callback, callback_context
from app.editorial.patches import BEER_FIELDS, PRICE_KEYS, Price, CommercialPatch, apply_commercial_patch, validate_patch
from app.editorial.proposal_v22 import (
    Proposal22, ExistingBeer, CommercialAction, IdentitySnapshot, Interaction, assert_identity_current,
)

CLEARABLE = frozenset(set(BEER_FIELDS) - {'name', 'brewery', 'style'} | {'prices.' + key for key in PRICE_KEYS})


class PreparationError(ValueError):
    """Fixed codes only; never include Pydantic inputs, SQL or private data."""


@dataclass(frozen=True)
class FieldDiff:
    path: tuple[str, ...]
    before_present: bool
    before: object = field(repr=False)
    after_present: bool
    after: object = field(repr=False)


@dataclass(frozen=True)
class CommercialPreparation:
    case_id: UUID
    proposal_revision: int
    action_id: UUID
    beer_id: int
    expected_identity_fingerprint: str
    identity_confirmation: Interaction = field(repr=False)
    baseline_sha256: str
    current_sha256: str
    status: Literal['prepared', 'conflict', 'noop']
    identity_current: bool
    conflicts: tuple[FieldDiff, ...] = field(repr=False)
    changes: tuple[FieldDiff, ...] = field(repr=False)
    current: dict = field(repr=False)
    proposed: dict = field(repr=False)
    approval_required: bool = field(default=True, init=False)


def _digest(snapshot):
    encoded = json.dumps(snapshot, sort_keys=True, ensure_ascii=True, allow_nan=False)
    if len(encoded) > 64 * 1024:
        raise ValueError()
    return sha256(encoded.encode()).hexdigest()


def _snapshot(value):
    if not isinstance(value, dict) or set(value) != set(BEER_FIELDS) | {'prices'}:
        raise ValueError()
    # Preserve raw spelling, nulls and legacy price keys. Do not normalize source values.
    IdentitySnapshot(**{key: value[key] for key in ('name', 'brewery', 'style')})
    for key in ('origin', 'color', 'description'):
        if value[key] is not None and not isinstance(value[key], str):
            raise ValueError()
    for key in ('abv', 'ibu'):
        if value[key] is not None:
            CommercialPatch.model_validate({key: {'op':'set', 'value':value[key]}})
    prices = value['prices']
    if prices is not None:
        if not isinstance(prices, dict) or len(prices) > 100:
            raise ValueError()
        for key, amount in prices.items():
            if not isinstance(key, str) or not key.strip() or len(key) > 255:
                raise ValueError()
            if amount is not None:
                TypeAdapter(Price).validate_python(amount)
    _digest(value)
    return deepcopy(value)


def _diff(before, after):
    result = []
    for key in BEER_FIELDS:
        if before[key] != after[key]:
            result.append(FieldDiff((key,), True, deepcopy(before[key]), True, deepcopy(after[key])))
    old, new = before['prices'] or {}, after['prices'] or {}
    price_changes = []
    for key in sorted(set(old) | set(new)):
        if (key in old) != (key in new) or old.get(key) != new.get(key):
            price_changes.append(FieldDiff(('prices', key), key in old, deepcopy(old.get(key)), key in new, deepcopy(new.get(key))))
    result.extend(price_changes)
    if not price_changes and (before['prices'] is None) != (after['prices'] is None):
        result.append(FieldDiff(('prices',), True, deepcopy(before['prices']), True, deepcopy(after['prices'])))
    return tuple(result)


def _validated_inputs(proposal, interview_context):
    try:
        payload = proposal.model_dump(mode='json', warnings=False) if isinstance(proposal, Proposal22) else deepcopy(dict(proposal))
        p = Proposal22.model_validate(payload)  # Also rejects unchecked model_copy mutations.
        if len(p.beers) != 1 or len(p.actions) != 1 or p.artworks or p.vocabulary:
            raise ValueError()
        beer, action = p.beers[0], p.actions[0]
        if not isinstance(beer, ExistingBeer) or type(action) is not CommercialAction or action.beer_identity_id != beer.id:
            raise ValueError()
        context = deepcopy(dict(interview_context))
        data = context['commercial']
        if context.get('flow') != 'carta_identity' or context.get('phase') != 'commercial' or data.get('mode') != 'edit':
            raise ValueError()
        nav = NavigationState.model_validate(context['navigation'])
        assert_callback(p, nav, callback_context(nav))
        baseline = _snapshot(data['baseline'])
        digest = _digest(baseline)
        if digest != data['baseline_sha256']:
            raise ValueError()
        reference_values = {key: baseline[key] for key in ('name', 'brewery', 'style')}
        if beer.snapshot.origin is not None:
            reference_values['origin'] = baseline['origin']
        if beer.snapshot.record_version is not None:
            raise ValueError()  # No SQL record_version source exists; never invent it.
        assert_identity_current(beer, IdentitySnapshot(**reference_values), beer_id=beer.beer_id)
        patch = validate_patch(action.patch, allow_clear=CLEARABLE)
    except (ValueError, TypeError, KeyError, AttributeError):
        raise PreparationError('invalid_or_ambiguous_proposal_context') from None
    return p, beer, action, baseline, digest, patch


def _prepare_with_reader(proposal, interview_context, read_current):
    p, beer, action, baseline, digest, patch = _validated_inputs(proposal, interview_context)
    try:
        current = _snapshot(read_current(beer.beer_id))
    except CandidateLookupError:
        raise PreparationError('catalog_unavailable_or_beer_missing_deleted') from None
    except (ValueError, TypeError, OSError):
        raise PreparationError('invalid_current_commercial_values') from None
    identity_current = True
    try:
        values = {key: current[key] for key in ('name', 'brewery', 'style')}
        if beer.snapshot.origin is not None:
            values['origin'] = current['origin']
        assert_identity_current(beer, IdentitySnapshot(**values), beer_id=beer.beer_id)
    except ValueError:
        identity_current = False
    conflicts = _diff(baseline, current)
    proposed = apply_commercial_patch(current, patch, allow_clear=CLEARABLE)
    changes = _diff(current, proposed)
    status = 'conflict' if conflicts or not identity_current else 'prepared' if changes else 'noop'
    return CommercialPreparation(p.case_id, p.revision, action.id, beer.beer_id,
                                 beer.expected_fingerprint, beer.confirmation, digest, _digest(current),
                                 status, identity_current, conflicts, changes, deepcopy(current), deepcopy(proposed))


def prepare_commercial_update(database_url: str, *, proposal: Proposal22 | Mapping,
                              interview_context: Mapping) -> CommercialPreparation:
    """Strictly read-only public preparation API; not approval or authorization."""
    return _prepare_with_reader(proposal, interview_context,
                                lambda beer_id: read_commercial_beer(database_url, beer_id))
