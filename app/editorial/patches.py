"""Typed sparse intentions and pure copies. No catalog imports or persistence."""
from copy import deepcopy
from typing import Annotated, Generic, Literal, Mapping, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_serializer


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


def text_type(limit: int):
    return Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=limit)]


Price = Annotated[float, Field(strict=True, ge=0, le=1_000_000, allow_inf_nan=False)]
ABV = Annotated[float, Field(strict=True, ge=0, le=100, allow_inf_nan=False)]
IBU = Annotated[float, Field(strict=True, ge=0, le=2000, allow_inf_nan=False)]
T = TypeVar("T")


class Keep(DomainModel):
    op: Literal["keep"]


class Skip(DomainModel):
    op: Literal["skip"]


class Unknown(DomainModel):
    op: Literal["unknown"]


class Clear(DomainModel):
    op: Literal["clear"]


class SetValue(DomainModel, Generic[T]):
    op: Literal["set"]
    value: T


NoChange = Keep | Skip | Unknown
NameIntent = Annotated[NoChange | SetValue[text_type(255)], Field(discriminator="op")]
StyleIntent = Annotated[NoChange | SetValue[text_type(100)], Field(discriminator="op")]
OriginIntent = Annotated[NoChange | Clear | SetValue[text_type(255)], Field(discriminator="op")]
ColorIntent = Annotated[NoChange | Clear | SetValue[text_type(80)], Field(discriminator="op")]
DescriptionIntent = Annotated[NoChange | Clear | SetValue[text_type(800)], Field(discriminator="op")]
ABVIntent = Annotated[NoChange | Clear | SetValue[ABV], Field(discriminator="op")]
IBUIntent = Annotated[NoChange | Clear | SetValue[IBU], Field(discriminator="op")]
PriceIntent = Annotated[NoChange | Clear | SetValue[Price], Field(discriminator="op")]
PRICE_KEYS = ("taster", "pinta_chica", "pinta_grande", "jarra_chica", "jarra_grande")
BEER_FIELDS = ("name", "brewery", "style", "origin", "color", "description", "abv", "ibu")


class SparseModel(DomainModel):
    @model_serializer(mode="wrap")
    def omit_missing_intentions(self, handler):
        return {key: value for key, value in handler(self).items() if value is not None}

    @field_validator("*", mode="before")
    @classmethod
    def explicit_null_is_not_an_intent(cls, value):
        if value is None:
            raise ValueError("Null is not a patch intention; omit the field or choose an explicit operation")
        return value


class PricePatch(SparseModel):
    taster: PriceIntent | None = None
    pinta_chica: PriceIntent | None = None
    pinta_grande: PriceIntent | None = None
    jarra_chica: PriceIntent | None = None
    jarra_grande: PriceIntent | None = None


class CommercialPatch(SparseModel):
    name: NameIntent | None = None
    brewery: NameIntent | None = None
    style: StyleIntent | None = None
    origin: OriginIntent | None = None
    color: ColorIntent | None = None
    description: DescriptionIntent | None = None
    abv: ABVIntent | None = None
    ibu: IBUIntent | None = None
    prices: PricePatch = Field(default_factory=PricePatch)


def patch_intentions(patch: CommercialPatch):
    for key in BEER_FIELDS:
        intent = getattr(patch, key)
        if intent is not None:
            yield key, intent
    for key in PRICE_KEYS:
        intent = getattr(patch.prices, key)
        if intent is not None:
            yield "prices." + key, intent


def validate_patch(patch: CommercialPatch | Mapping, *, allow_clear: frozenset[str] = frozenset()) -> CommercialPatch:
    raw = patch.model_dump(mode="json", exclude_none=True) if isinstance(patch, CommercialPatch) else patch
    validated = CommercialPatch.model_validate(raw)
    for path, intent in patch_intentions(validated):
        if isinstance(intent, Clear) and path not in allow_clear:
            raise ValueError("Explicit clear permission required for " + path)
    return validated


def apply_commercial_patch(original: Mapping, patch: CommercialPatch | Mapping, *,
                           allow_clear: frozenset[str] = frozenset()) -> dict:
    """Clear optional scalars to null; clear a price by removing only that key."""
    validated = validate_patch(patch, allow_clear=allow_clear)
    result = deepcopy(dict(original))
    for path, intent in patch_intentions(validated):
        if isinstance(intent, (Keep, Skip, Unknown)):
            continue
        if path.startswith("prices."):
            current = result.get("prices")
            if current is not None and not isinstance(current, dict):
                raise ValueError("Existing prices must be an object or null")
            prices = deepcopy(current) if current is not None else {}
            key = path.split(".")[1]
            if isinstance(intent, Clear):
                prices.pop(key, None)
                # Removing an absent key must not materialize an empty price object.
                if current is not None:
                    result["prices"] = prices
            else:
                prices[key] = intent.value
                result["prices"] = prices
        else:
            result[path] = None if isinstance(intent, Clear) else intent.value
    return result


def correct_patch_field(patch: CommercialPatch, path: str, intent: Mapping, *,
                        allow_clear: frozenset[str] = frozenset()) -> CommercialPatch:
    """Validate one answer; no-op answers preserve previously entered intentions."""
    if path not in BEER_FIELDS and path not in {"prices." + key for key in PRICE_KEYS}:
        raise ValueError("Unsupported commercial field")
    raw = patch.model_dump(mode="json", exclude_none=True)
    single = {"prices": {path.split(".")[1]: dict(intent)}} if path.startswith("prices.") else {path: dict(intent)}
    checked = validate_patch(single, allow_clear=allow_clear)
    value = next(patch_intentions(checked))[1]
    if isinstance(value, (Keep, Skip, Unknown)):
        return CommercialPatch.model_validate(raw)
    if path.startswith("prices."):
        raw.setdefault("prices", {})[path.split(".")[1]] = value.model_dump(mode="json")
    else:
        raw[path] = value.model_dump(mode="json")
    # Existing clear intentions are retained; they still need permission at application.
    return CommercialPatch.model_validate(raw)
