"""Preparation-only 2.2 contracts. References are assertions, not live lookups."""
from hashlib import sha256
import json
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.editorial.patches import (CommercialPatch, DomainModel, SetValue, Clear, patch_intentions, text_type,
                                   BEER_FIELDS, PRICE_KEYS, apply_commercial_patch)
from app.editorial.proposal import Museum, ProposedBeer

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
PositiveID = Annotated[int, Field(strict=True, gt=0, le=2**63 - 1)]
Text = text_type(255)


class Interaction(DomainModel):
    method: Literal["human_confirmation"]
    reference: text_type(128)


class IdentitySnapshot(DomainModel):
    # Match keys may normalize spelling; stale-reference fingerprints must not.
    name: Annotated[str, Field(strict=True, min_length=1, max_length=255)]
    brewery: Annotated[str, Field(strict=True, min_length=1, max_length=255)]
    style: Annotated[str, Field(strict=True, min_length=1, max_length=100)]
    origin: Annotated[str, Field(strict=True, min_length=1, max_length=255)] | None = None
    record_version: Annotated[str, Field(strict=True, min_length=1, max_length=128)] | None = None

    @field_validator("name", "brewery", "style", "origin", "record_version")
    @classmethod
    def nonblank_snapshot(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Snapshot values cannot be blank")
        return value


def identity_fingerprint(snapshot: IdentitySnapshot | dict, *, beer_id: int) -> str:
    if type(beer_id) is not int or not 0 < beer_id < 2**63:
        raise ValueError("A positive beer ID is required for the fingerprint")
    value = IdentitySnapshot.model_validate(snapshot)
    return sha256(json.dumps({"beer_id": beer_id, "snapshot": value.model_dump(mode="json")}, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True).encode()).hexdigest()


class ExistingBeer(DomainModel):
    kind: Literal["existing"]
    id: UUID
    beer_id: PositiveID
    snapshot: IdentitySnapshot
    expected_fingerprint: Digest
    confirmation: Interaction

    @model_validator(mode="after")
    def coherent_snapshot(self):
        if identity_fingerprint(self.snapshot, beer_id=self.beer_id) != self.expected_fingerprint:
            raise ValueError("Existing beer fingerprint does not match its identity snapshot")
        return self


class NewBeer(DomainModel):
    kind: Literal["new"]
    id: UUID
    candidate: ProposedBeer = Field(default_factory=ProposedBeer)


class UnresolvedBeer(DomainModel):
    kind: Literal["unresolved"]
    id: UUID
    entered_name: Text | None = None
    notes: text_type(800) | None = None


BeerIdentity = Annotated[ExistingBeer | NewBeer | UnresolvedBeer, Field(discriminator="kind")]


def assert_identity_current(reference: ExistingBeer, current: IdentitySnapshot | dict, *, beer_id: int) -> None:
    if beer_id != reference.beer_id or identity_fingerprint(current, beer_id=beer_id) != reference.expected_fingerprint:
        raise ValueError("Stale beer identity reference; human confirmation must be renewed")


class PrivateAsset(DomainModel):
    kind: Literal["private"]
    asset_id: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]
    expected_sha256: Digest | None = None


class MuseumReference(DomainModel):
    kind: Literal["museum"]
    artwork_id: UUID
    expected_sha256: Digest | None = None


AssetSource = Annotated[PrivateAsset | MuseumReference, Field(discriminator="kind")]


class BeerSubject(DomainModel):
    kind: Literal["beer"]
    id: UUID
    beer_identity_id: UUID


class BrewerySubject(DomainModel):
    kind: Literal["brewery"]
    id: UUID
    name: Text


class UnknownSubject(DomainModel):
    kind: Literal["unknown"]
    id: UUID
    notes: text_type(800) | None = None


Subject = Annotated[BeerSubject | BrewerySubject | UnknownSubject, Field(discriminator="kind")]


class Artwork(DomainModel):
    id: UUID
    source: AssetSource
    roles: tuple[Literal["beer_card", "tap_board", "label"], ...] = Field(default=(), max_length=3)
    museum: Museum = Field(default_factory=Museum)
    represents: tuple[Subject, ...] = Field(default=(), max_length=20)
    used_for: tuple[UUID, ...] = Field(default=(), max_length=50)

    @model_validator(mode="after")
    def unique_relations(self):
        if len(set(self.roles)) != len(self.roles) or len(set(self.used_for)) != len(self.used_for):
            raise ValueError("Duplicate artwork role or use relationship")
        if len({s.id for s in self.represents}) != len(self.represents):
            raise ValueError("Duplicate represented subject identifier")
        return self


class CommercialAction(DomainModel):
    kind: Literal["commercial_change"]
    id: UUID
    beer_identity_id: UUID
    patch: CommercialPatch = Field(default_factory=CommercialPatch)


class CreateBeerAction(CommercialAction):
    kind: Literal["beer_create"]
    is_available: Literal[False] = False

    @field_validator("is_available", mode="before")
    @classmethod
    def unavailable_only(cls, value):
        if value is not False:
            raise ValueError("New beer proposals must remain unavailable")
        return value


class ReplaceCardAction(DomainModel):
    kind: Literal["replace_beer_card"]
    id: UUID
    beer_identity_id: UUID
    artwork_id: UUID


class RegisterArtworkAction(DomainModel):
    kind: Literal["museum_register"]
    id: UUID
    artwork_id: UUID


class ReuseArtworkAction(DomainModel):
    kind: Literal["museum_reuse"]
    id: UUID
    artwork_id: UUID


class ArtworkUseAction(DomainModel):
    kind: Literal["artwork_relationship"]
    id: UUID
    artwork_id: UUID
    beer_identity_id: UUID


Action = Annotated[CommercialAction | CreateBeerAction | ReplaceCardAction | RegisterArtworkAction | ReuseArtworkAction |
                   ArtworkUseAction, Field(discriminator="kind")]
VocabularyField = Literal["name", "brewery", "style", "origin", "color"]


class SQLProvenance(DomainModel):
    source: Literal["sql"]
    beer_id: PositiveID
    field: VocabularyField
    expected_fingerprint: Digest | None = None


class MuseumProvenance(DomainModel):
    source: Literal["museum"]
    artwork_id: UUID
    product_index: Annotated[int, Field(strict=True, ge=0)]
    field: VocabularyField
    confidence: Literal["confirmed", "probable", "unknown"]
    evidence: Annotated[str, Field(strict=True, max_length=4000)]


Provenance = Annotated[SQLProvenance | MuseumProvenance, Field(discriminator="source")]


class VocabularyCandidate(DomainModel):
    id: UUID
    value: Text
    provenance: tuple[Provenance, ...] = Field(min_length=1, max_length=20)
    method: Literal["exact", "normalized", "alias", "fuzzy"]
    score: Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)] | None = None


class VocabularyDecision(DomainModel):
    id: UUID
    field: VocabularyField
    original_input: Annotated[str, Field(strict=True, min_length=1, max_length=800)]
    normalized_key: text_type(800)
    candidates: tuple[VocabularyCandidate, ...] = Field(default=(), max_length=10)
    decision: Literal["confirmed", "rejected", "unresolved"]
    selected_candidate_id: UUID | None = None
    interaction: Interaction | None = None

    @model_validator(mode="after")
    def selection_is_explicit(self):
        ids = {c.id for c in self.candidates}
        if len(ids) != len(self.candidates):
            raise ValueError("Duplicate vocabulary candidate")
        if any(p.field != self.field for c in self.candidates for p in c.provenance):
            raise ValueError("Vocabulary provenance must refer to the same semantic field")
        if self.decision == "confirmed":
            if self.selected_candidate_id not in ids or self.interaction is None:
                raise ValueError("Vocabulary confirmation requires a candidate and an interaction reference")
        elif self.selected_candidate_id is not None:
            raise ValueError("Unconfirmed vocabulary cannot have a selected candidate")
        if self.decision == "rejected" and self.interaction is None:
            raise ValueError("Vocabulary rejection requires an interaction reference")
        return self


class Preparation(DomainModel):
    interaction: Interaction
    content_revision: PositiveID
    content_fingerprint: Digest


class Proposal22(DomainModel):
    schema_version: Literal["2.2"]
    case_id: UUID
    intake_origin: Literal["telegram_document", "telegram_photo", "data_only", "imported"]
    revision: PositiveID
    beers: tuple[BeerIdentity, ...] = Field(default=(), max_length=50)
    artworks: tuple[Artwork, ...] = Field(default=(), max_length=50)
    actions: tuple[Action, ...] = Field(default=(), max_length=100)
    vocabulary: tuple[VocabularyDecision, ...] = Field(default=(), max_length=100)
    readiness: Literal["incomplete", "technically_valid", "prepared_for_review"] = "incomplete"
    preparation: Preparation | None = None
    change_summary: text_type(200) = "Inicio de propuesta"

    @model_validator(mode="after")
    def references_are_coherent(self):
        for values in (self.beers, self.artworks, self.actions, self.vocabulary):
            if len({item.id for item in values}) != len(values):
                raise ValueError("Duplicate stable identifier")
        existing_ids = [b.beer_id for b in self.beers if isinstance(b, ExistingBeer)]
        if len(set(existing_ids)) != len(existing_ids):
            raise ValueError("An existing beer must have one identity per case")
        sources = [(a.source.kind, a.source.asset_id if isinstance(a.source, PrivateAsset) else a.source.artwork_id)
                   for a in self.artworks]
        if len(set(sources)) != len(sources):
            raise ValueError("Reuse the same artwork with multiple roles or relationships instead of duplicating its reference")
        beers = {b.id: b for b in self.beers}
        art = {a.id: a for a in self.artworks}
        for artwork in self.artworks:
            related = set(artwork.used_for) | {s.beer_identity_id for s in artwork.represents if isinstance(s, BeerSubject)}
            if not related.issubset(beers):
                raise ValueError("Artwork refers to a missing beer identity")
        for action in self.actions:
            if hasattr(action, "beer_identity_id") and action.beer_identity_id not in beers:
                raise ValueError("Action refers to a missing beer identity")
            if hasattr(action, "artwork_id") and action.artwork_id not in art:
                raise ValueError("Action refers to a missing artwork")
            if isinstance(action, CreateBeerAction) and not isinstance(beers[action.beer_identity_id], NewBeer):
                raise ValueError("Creation requires a new beer identity")
            if isinstance(action, CreateBeerAction):
                optional = (set(BEER_FIELDS) - {"name", "brewery", "style"}) | {"prices." + k for k in PRICE_KEYS}
                candidate = ProposedBeer.model_validate(apply_commercial_patch({}, action.patch, allow_clear=frozenset(optional)))
                if beers[action.beer_identity_id].candidate != candidate:
                    raise ValueError("New beer values must match their explicit commercial intentions")
            if isinstance(action, RegisterArtworkAction) and not isinstance(art[action.artwork_id].source, PrivateAsset):
                raise ValueError("Existing Museum artwork cannot be registered again")
            if isinstance(action, ReuseArtworkAction) and not isinstance(art[action.artwork_id].source, MuseumReference):
                raise ValueError("Museum reuse requires an existing Museum reference")
            if isinstance(action, ReplaceCardAction) and "beer_card" not in art[action.artwork_id].roles:
                raise ValueError("Card replacement requires an explicit beer_card role")
            if isinstance(action, ArtworkUseAction) and action.beer_identity_id not in art[action.artwork_id].used_for:
                raise ValueError("Relationship action must match an explicit used_for relationship")
        if self.readiness != "incomplete" and proposal_issues(self):
            raise ValueError("Proposal is not technically complete")
        if self.readiness == "prepared_for_review":
            if self.preparation is None or self.preparation.content_revision != self.revision \
                    or self.preparation.content_fingerprint != content_fingerprint(self):
                raise ValueError("Prepared status requires explicit closure of this content revision")
        elif self.preparation is not None:
            raise ValueError("Preparation reference is only valid for prepared_for_review")
        return self


def proposal_issues(proposal: Proposal22) -> tuple[str, ...]:
    issues = []
    beers = {b.id: b for b in proposal.beers}
    artworks = {a.id: a for a in proposal.artworks}
    if not proposal.actions:
        issues.append("No proposed actions")
    for action in proposal.actions:
        if hasattr(action, "beer_identity_id"):
            beer = beers[action.beer_identity_id]
            if isinstance(beer, UnresolvedBeer):
                issues.append("Operational identity unresolved")
            if isinstance(beer, NewBeer):
                if any(getattr(beer.candidate, field) is None for field in ("name", "brewery", "style")):
                    issues.append("New beer requires name, brewery and style")
            if isinstance(beer, ExistingBeer) and isinstance(action, CommercialAction) and not any(
                    isinstance(value, (SetValue, Clear)) for _, value in patch_intentions(action.patch)):
                issues.append("Commercial action has no changes")
        if isinstance(action, RegisterArtworkAction):
            metadata = artworks[action.artwork_id].museum
            if metadata.title is None or metadata.collection is None:
                issues.append("Museum registration requires title and collection")
    return tuple(dict.fromkeys(issues))


def content_fingerprint(proposal: Proposal22) -> str:
    data = proposal.model_dump(mode="json", exclude={"revision", "readiness", "preparation", "change_summary"})
    return sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def assess_readiness(proposal: Proposal22) -> Proposal22:
    proposal = Proposal22.model_validate(proposal.model_dump(mode="json"))
    if proposal.readiness == "prepared_for_review":
        return Proposal22.model_validate(proposal.model_dump(mode="json"))
    raw = proposal.model_dump(mode="json")
    raw.update(readiness="technically_valid" if not proposal_issues(proposal) else "incomplete", preparation=None)
    return Proposal22.model_validate(raw)


def prepare_for_review(proposal: Proposal22, interaction: Interaction, *, expected_revision: int) -> Proposal22:
    proposal = Proposal22.model_validate(proposal.model_dump(mode="json"))
    interaction = Interaction.model_validate(interaction)
    if type(expected_revision) is not int or proposal.revision != expected_revision:
        raise ValueError("Stale preparation request")
    if proposal.readiness == "prepared_for_review":
        raise ValueError("Proposal is already prepared for review")
    if proposal_issues(proposal):
        raise ValueError("Incomplete proposal cannot be prepared for review")
    raw = proposal.model_dump(mode="json")
    raw.update(revision=proposal.revision + 1, readiness="prepared_for_review", change_summary="Preparación explícita para revisión",
               preparation={"interaction": interaction.model_dump(mode="json"), "content_revision": proposal.revision + 1,
                            "content_fingerprint": content_fingerprint(proposal)})
    return Proposal22.model_validate(raw)
