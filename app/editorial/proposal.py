"""Versioned preparation-only contract. Never imports operational persistence."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

PRICE_KEYS = ('taster', 'pinta_chica', 'pinta_grande', 'jarra_chica', 'jarra_grande')
Operation = Literal['new', 'art', 'fix', 'board', 'event']
Target = Literal['beer_create', 'beer_update', 'beer_artwork', 'museum']


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)


class Prices(Contract):
    taster: float | None = Field(None, ge=0, le=1_000_000)
    pinta_chica: float | None = Field(None, ge=0, le=1_000_000)
    pinta_grande: float | None = Field(None, ge=0, le=1_000_000)
    jarra_chica: float | None = Field(None, ge=0, le=1_000_000)
    jarra_grande: float | None = Field(None, ge=0, le=1_000_000)

    @field_validator('*', mode='before')
    @classmethod
    def no_boolean(cls, value):
        if isinstance(value, bool):
            raise ValueError('Use a numeric amount')
        return value


class ProposedBeer(Contract):
    name: str | None = Field(None, min_length=1, max_length=255)
    brewery: str | None = Field(None, min_length=1, max_length=255)
    style: str | None = Field(None, min_length=1, max_length=100)
    origin: str | None = Field(None, min_length=1, max_length=255)
    color: str | None = Field(None, min_length=1, max_length=80)
    description: str | None = Field(None, min_length=1, max_length=800)
    abv: float | None = Field(None, ge=0, le=100)
    ibu: float | None = Field(None, ge=0, le=2000)
    prices: Prices = Field(default_factory=Prices)

    @field_validator('abv', 'ibu', mode='before')
    @classmethod
    def no_boolean(cls, value):
        if isinstance(value, bool):
            raise ValueError('Use a numeric value')
        return value


class Artwork(Contract):
    asset_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    subject: Literal['beer', 'brewery', 'multiple', 'unknown'] = 'unknown'
    subject_name: str | None = Field(None, min_length=1, max_length=255)


class Artworks(Contract):
    beer_card: Artwork | None = None
    tap_board: Artwork | None = None
    label: Artwork | None = None


class SemanticValue(Contract):
    value: str | None = Field(None, min_length=1, max_length=255)
    confidence: Literal['confirmed', 'probable', 'unknown'] = 'unknown'
    evidence: str | None = Field(None, max_length=500)


class SemanticCollaborators(Contract):
    value: list[str] | None = Field(None, max_length=20)
    confidence: Literal['confirmed', 'probable', 'unknown'] = 'unknown'
    evidence: str | None = Field(None, max_length=500)

    @field_validator('value')
    @classmethod
    def bounded_names(cls, value):
        if value and any(not name.strip() or len(name) > 255 for name in value):
            raise ValueError('Invalid collaborator')
        return value


class SemanticProduct(Contract):
    beer_name: SemanticValue = Field(default_factory=SemanticValue)
    beer_style: SemanticValue = Field(default_factory=SemanticValue)
    brewery: SemanticValue = Field(default_factory=SemanticValue)
    brewery_origin: SemanticValue = Field(default_factory=SemanticValue)
    collaborators: SemanticCollaborators = Field(default_factory=SemanticCollaborators)


class Museum(Contract):
    collection: Literal['tap_list', 'carta_vieja', 'carta_nueva', 'etiquetas'] | None = None
    title: str | None = Field(None, min_length=1, max_length=255)
    year: int | None = Field(None, ge=1800, le=2200)
    semantic_products: list[SemanticProduct] = Field(default_factory=list, max_length=20)


class Proposal(Contract):
    schema_version: Literal['2.1'] = '2.1'
    revision: int = Field(ge=1)
    operation: Operation
    targets: list[Target] = Field(default_factory=list, max_length=4)
    existing_beer_id: int | None = Field(None, gt=0, strict=True)
    beer: ProposedBeer = Field(default_factory=ProposedBeer)
    artworks: Artworks = Field(default_factory=Artworks)
    museum: Museum = Field(default_factory=Museum)
    tap_activation_intent: Literal['unspecified', 'no', 'later'] = 'unspecified'
    validation_status: Literal['incomplete', 'valid'] = 'incomplete'
    validation_issues: list[str] = Field(default_factory=list, max_length=30)
    change_summary: str = Field(default='Inicio de propuesta', max_length=200)

    def validated_snapshot(self):
        issues = []
        allowed = {'new': {'beer_create', 'museum'}, 'art': {'beer_artwork', 'museum'},
                   'fix': {'beer_update'}, 'board': {'museum'}, 'event': {'museum'}}[self.operation]
        if not self.targets or len(set(self.targets)) != len(self.targets) or not set(self.targets) <= allowed:
            issues.append('Selecciona destinos compatibles')
        if 'beer_create' in self.targets:
            for key in ('name', 'brewery', 'style'):
                if getattr(self.beer, key) is None:
                    issues.append('Falta cerveza: ' + key)
        if set(self.targets) & {'beer_update', 'beer_artwork'} and self.existing_beer_id is None:
            issues.append('Falta ID de cerveza existente (sin verificar)')
        if 'beer_update' in self.targets and not any(
                value is not None for key, value in self.beer.model_dump().items() if key != 'prices') \
                and not any(value is not None for value in self.beer.prices.model_dump().values()):
            issues.append('Falta al menos una corrección')
        if 'beer_artwork' in self.targets and self.artworks.beer_card is None:
            issues.append('Falta arte de ficha')
        if 'museum' in self.targets:
            if self.museum.collection is None:
                issues.append('Falta colección del Museo')
            if self.museum.title is None:
                issues.append('Falta título de obra')
            if not any(self.artworks.model_dump().values()):
                issues.append('Falta asignar una imagen a la propuesta')
        for role in ('beer_card', 'tap_board', 'label'):
            art = getattr(self.artworks, role)
            if art and art.subject in {'beer', 'brewery'} and art.subject_name is None:
                issues.append('Falta identificar el tema: ' + role)
        self.validation_issues = issues
        self.validation_status = 'incomplete' if issues else 'valid'
        return self


class UnsupportedProposalVersion(ValueError):
    """No payload values are included in version errors."""


def validate_proposal(payload):
    """Keep the original 2.1 class/defaults; never convert historical snapshots."""
    if not isinstance(payload, dict):
        raise ValueError("Proposal must be an object")
    version = payload.get("schema_version", "2.1")
    if version == "2.1":
        return Proposal.model_validate(payload)
    if version == "2.2":
        from app.editorial.proposal_v22 import Proposal22
        return Proposal22.model_validate(payload)
    raise UnsupportedProposalVersion("Unsupported Editorial proposal contract version")
