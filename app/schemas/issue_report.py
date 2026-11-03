import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


Dimension = Annotated[float, Field(ge=0, le=100_000)]
ShortText = Annotated[str, Field(max_length=200, pattern=r"^[^\x00-\x1f\x7f]*$")]
Category = Literal["Tap List", "Museo", "Información de cerveza", "Interacción / visualización", "Otro"]


class Dimensions(StrictModel):
    width: Dimension | None = None
    height: Dimension | None = None


class VisualViewport(Dimensions):
    offsetTop: Annotated[float, Field(ge=-100_000, le=100_000)] | None = None
    offsetLeft: Annotated[float, Field(ge=-100_000, le=100_000)] | None = None
    scale: Annotated[float, Field(gt=0, le=100)] | None = None


class Browser(StrictModel):
    name: Literal["Edge", "Opera", "Chrome", "Firefox", "Safari"] | None = None
    version: Annotated[str, Field(max_length=64, pattern=r"^\d+(?:\.\d+)*$")] | None = None


class Network(StrictModel):
    type: Literal["bluetooth", "cellular", "ethernet", "mixed", "none", "other", "unknown", "wifi", "wimax"] | None = None
    effectiveType: Literal["slow-2g", "2g", "3g", "4g"] | None = None
    downlinkMbps: Annotated[float, Field(ge=0, le=100_000)] | None = None
    rttMs: Annotated[float, Field(ge=0, le=1_000_000)] | None = None
    saveData: bool | None = None


class DiagnosticSnapshot(StrictModel):
    schemaVersion: Literal[1]
    timestamp: Annotated[str, Field(max_length=40)]
    timezone: ShortText | None = None
    utcOffsetMinutes: Annotated[int, Field(ge=-840, le=840)] | None = None
    route: Annotated[str, Field(max_length=256)]
    browser: Browser | None = None
    os: Literal["iOS/iPadOS", "Android", "Windows", "macOS (iPadOS posible)", "Linux"] | None = None
    viewport: Dimensions | None = None
    screen: Dimensions | None = None
    visualViewport: VisualViewport | None = None
    devicePixelRatio: Annotated[float, Field(gt=0, le=100)] | None = None
    orientation: Literal["portrait-primary", "portrait-secondary", "landscape-primary", "landscape-secondary"] | None = None
    online: bool | None = None
    network: Network | None = None

    @field_validator("timestamp")
    @classmethod
    def valid_timestamp(cls, value):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Timestamp must include timezone")
        return value

    @field_validator("route")
    @classmethod
    def safe_route(cls, value):
        # Only ATLAS public routes, without arbitrary path content/query/hash.
        if not re.fullmatch(r"/(?:museum|beer/[0-9]{1,12})?", value):
            raise ValueError("Unsupported public route")
        return value

    @field_validator("timezone")
    @classmethod
    def safe_timezone(cls, value):
        if value is not None and not re.fullmatch(r"[A-Za-z0-9_+./-]{1,100}", value):
            raise ValueError("Invalid timezone")
        return value


class IssueReportCreate(StrictModel):
    schema_version: Literal[1] = 1
    categories: Annotated[list[Category], Field(min_length=1, max_length=5)]
    description: Annotated[str, Field(min_length=20, max_length=2000)]
    diagnostic_consent: bool
    diagnostics: DiagnosticSnapshot | None = None
    idempotency_key: Annotated[str, Field(max_length=36)]

    @field_validator("description", mode="before")
    @classmethod
    def trim_description(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("categories")
    @classmethod
    def unique_categories(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("Duplicate categories")
        return sorted(value)

    @field_validator("idempotency_key")
    @classmethod
    def valid_key(cls, value):
        key = UUID(value)
        if key.version != 4 or str(key) != value.lower():
            raise ValueError("Use a UUID v4 idempotency key")
        return str(key)

    @model_validator(mode="after")
    def consent_and_size(self):
        if not self.diagnostic_consent and self.diagnostics is not None:
            raise ValueError("Diagnostics require consent")
        if self.diagnostics and len(self.diagnostics.model_dump_json().encode("utf-8")) > 16 * 1024:
            raise ValueError("Diagnostics exceed size limit")
        return self


class IssueReportReceipt(BaseModel):
    report_id: str
    stored_at: datetime
