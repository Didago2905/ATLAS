from pydantic import BaseModel
from typing import Optional, Dict


class BeerCreate(BaseModel):
    name: str
    brewery: str
    style: str
    color: Optional[str] = None
    abv: Optional[float] = None
    ibu: Optional[float] = None
    description: Optional[str] = None
    origin: Optional[str] = None
    image_url: Optional[str] = None
    prices: Optional[Dict[str, float]] = None
    tap_position: Optional[int] = None  # 🔥 NUEVO


class BeerResponse(BaseModel):

    id: int
    name: str
    brewery: str
    style: str
    color: Optional[str]

    abv: Optional[float]
    ibu: Optional[float]

    description: Optional[str]
    origin: Optional[str]
    image_url: Optional[str]

    prices: Optional[Dict[str, float]] = None

    is_available: bool
    tap_position: Optional[int]  # 🔥 NUEVO

    class Config:
        from_attributes = True


class BeerAvailabilityUpdate(BaseModel):
    is_available: bool


class BeerUpdate(BaseModel):

    name: Optional[str] = None
    brewery: Optional[str] = None
    style: Optional[str] = None
    color: Optional[str] = None

    abv: Optional[float] = None
    ibu: Optional[float] = None

    description: Optional[str] = None
    origin: Optional[str] = None
    image_url: Optional[str] = None

    prices: Optional[Dict[str, float]] = None

    is_available: Optional[bool] = None
    tap_position: Optional[int] = None  # 🔥 NUEVO
