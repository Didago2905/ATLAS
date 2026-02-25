from pydantic import BaseModel
from typing import Optional


class BeerCreate(BaseModel):
    name: str
    brewery: str
    style: str
    abv: Optional[float] = None
    ibu: Optional[float] = None
    description: Optional[str] = None
    origin: Optional[str] = None
    image_url: Optional[str] = None


class BeerResponse(BaseModel):
    id: int
    name: str
    brewery: str
    style: str
    abv: Optional[float]
    ibu: Optional[float]
    description: Optional[str]
    origin: Optional[str]
    image_url: Optional[str]
    is_available: bool

    class Config:
        from_attributes = True


class BeerAvailabilityUpdate(BaseModel):
    is_available: bool


class BeerUpdate(BaseModel):
    name: Optional[str] = None
    brewery: Optional[str] = None
    style: Optional[str] = None
    abv: Optional[float] = None
    ibu: Optional[float] = None
    description: Optional[str] = None
    origin: Optional[str] = None
    image_url: Optional[str] = None
    is_available: Optional[bool] = None
