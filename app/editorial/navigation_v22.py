"""Pure 2.2 navigation; never interprets or rewrites a 2.1 interview history."""
from typing import Annotated, Literal, Mapping
from uuid import UUID

from pydantic import Field

from app.editorial.patches import BEER_FIELDS, PRICE_KEYS, DomainModel, correct_patch_field
from app.editorial.proposal_v22 import (
    BrewerySubject, CommercialAction, NewBeer, Proposal22, UnknownSubject, content_fingerprint,
)

Version = Annotated[int, Field(strict=True, gt=0, le=2**63 - 1)]
Path = Annotated[str, Field(strict=True, min_length=1, max_length=180)]


class NavigationState(DomainModel):
    schema_version: Literal["2.2"] = "2.2"
    case_id: UUID
    interaction_version: Version = 1
    content_revision: Version
    current_path: Path = "summary"
    history: tuple[Path, ...] = Field(default=(), max_length=100)


class CallbackContext(DomainModel):
    case_id: UUID
    interaction_version: Version
    content_revision: Version


def valid_paths(proposal: Proposal22) -> tuple[str, ...]:
    """Stable object IDs, never positional list indexes or caller-supplied paths."""
    paths = []
    for beer in proposal.beers:
        base = f"beer/{beer.id}"
        paths.append(base + "/identity")
        if isinstance(beer, NewBeer):
            paths.extend(base + "/" + key for key in BEER_FIELDS)
            paths.extend(base + "/prices." + key for key in PRICE_KEYS)
    for action in proposal.actions:
        if isinstance(action, CommercialAction):
            paths.extend(f"commercial/{action.id}/{key}" for key in BEER_FIELDS)
            paths.extend(f"commercial/{action.id}/prices.{key}" for key in PRICE_KEYS)
    for artwork in proposal.artworks:
        base = f"artwork/{artwork.id}"
        paths.extend(base + "/" + key for key in ("source", "roles", "used_for", "museum.collection", "museum.title", "museum.year"))
        for subject in artwork.represents:
            field = "name" if isinstance(subject, BrewerySubject) else "notes" if isinstance(subject, UnknownSubject) else "identity"
            paths.append(base + f"/subject/{subject.id}/{field}")
    return (*paths, "summary")


def callback_context(state: NavigationState) -> CallbackContext:
    return CallbackContext(case_id=state.case_id, interaction_version=state.interaction_version,
                           content_revision=state.content_revision)


def reconcile_paths(proposal: Proposal22, state: NavigationState) -> NavigationState:
    """Resume/correct by filtering history against the new branch; invalidate old buttons."""
    if state.case_id != proposal.case_id or state.content_revision > proposal.revision:
        raise ValueError("Navigation state does not belong to this proposal revision")
    allowed = valid_paths(proposal)
    history = tuple(path for path in state.history if path in allowed)
    current = state.current_path if state.current_path in allowed else history[-1] if history else allowed[0]
    return NavigationState(case_id=proposal.case_id, interaction_version=state.interaction_version + 1,
                           content_revision=proposal.revision, current_path=current, history=history)


def start_navigation(proposal: Proposal22) -> NavigationState:
    return NavigationState(case_id=proposal.case_id, content_revision=proposal.revision,
                           current_path=valid_paths(proposal)[0])


def assert_callback(proposal: Proposal22, state: NavigationState, token: CallbackContext) -> None:
    Proposal22.model_validate(proposal.model_dump(mode="json"))
    if state.case_id != proposal.case_id or token != callback_context(state) \
            or state.content_revision != proposal.revision or state.current_path not in valid_paths(proposal):
        raise ValueError("Stale or incompatible interview callback")


def navigate(proposal: Proposal22, state: NavigationState, token: CallbackContext, *,
             action: Literal["next", "back", "summary", "correct", "skip", "keep", "unknown"],
             target: str | None = None) -> NavigationState:
    assert_callback(proposal, state, token)
    allowed = valid_paths(proposal)
    history = tuple(path for path in state.history if path in allowed)
    if action == "back":
        current = history[-1] if history else allowed[0]
        history = history[:-1]
    else:
        history = (*history[-99:], state.current_path)
        if action == "summary":
            current = "summary"
        elif action == "correct":
            if target not in allowed:
                raise ValueError("Correction path is not valid in the current branch")
            current = target
        elif action in {"next", "skip", "keep", "unknown"}:
            current = allowed[min(allowed.index(state.current_path) + 1, len(allowed) - 1)]
        else:
            raise ValueError("Unsupported navigation action")
    return NavigationState(case_id=proposal.case_id, interaction_version=state.interaction_version + 1,
                           content_revision=proposal.revision, current_path=current, history=history)


def correct_proposal(proposal: Proposal22, state: NavigationState, token: CallbackContext,
                     corrected: Proposal22) -> tuple[Proposal22, NavigationState]:
    """Accept an already typed domain correction, not an arbitrary deep-path assignment."""
    assert_callback(proposal, state, token)
    if corrected.case_id != proposal.case_id or corrected.revision != proposal.revision \
            or corrected.intake_origin != proposal.intake_origin:
        raise ValueError("Correction cannot replace case identity, intake or revision")
    # model_copy is not a validation API; revalidate before comparing or accepting data.
    corrected = Proposal22.model_validate(corrected.model_dump(mode="json"))
    if content_fingerprint(corrected) != content_fingerprint(proposal):
        raw = corrected.model_dump(mode="json")
        raw.update(revision=proposal.revision + 1, readiness="incomplete", preparation=None,
                   change_summary="Corrección explícita de propuesta")
        corrected = Proposal22.model_validate(raw)
    else:
        corrected = Proposal22.model_validate(proposal.model_dump(mode="json"))
    return corrected, reconcile_paths(corrected, state)


def answer_commercial(proposal: Proposal22, state: NavigationState, token: CallbackContext, *,
                      action_id: UUID, field: str, intent: Mapping,
                      allow_clear: frozenset[str] = frozenset()) -> tuple[Proposal22, NavigationState]:
    assert_callback(proposal, state, token)
    if state.current_path != f"commercial/{action_id}/{field}":
        raise ValueError("Answer does not match the current commercial question")
    index = next((i for i, action in enumerate(proposal.actions) if action.id == action_id and isinstance(action, CommercialAction)), None)
    if index is None:
        raise ValueError("Missing commercial action")
    patch = correct_patch_field(proposal.actions[index].patch, field, intent, allow_clear=allow_clear)
    raw = proposal.model_dump(mode="json")
    raw["actions"][index]["patch"] = patch.model_dump(mode="json")
    # Any content edit reopens a prepared proposal; it never preserves an old closure.
    raw.update(readiness="incomplete", preparation=None)
    updated, next_state = correct_proposal(proposal, state, token, Proposal22.model_validate(raw))
    return updated, navigate(updated, next_state, callback_context(next_state), action="next")
