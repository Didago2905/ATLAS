from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.database import get_db
from app.core.security import verify_token
from app.models.beer import Beer
from app.schemas.beer import (
    BeerCreate,
    BeerResponse,
    BeerUpdate,
    BeerAvailabilityUpdate,
)
from app.services import beer_service

router = APIRouter(prefix="/admin", tags=["Admin"])


from pydantic import BaseModel
from app.core.auth import create_access_token


class LoginRequest(BaseModel):
    password: str


@router.post("/login")
def login(data: LoginRequest):

    if data.password != "atlas123":
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": "admin"})

    return {
        "access_token": token,
        "token_type": "bearer"
    }


# 🍺 CREATE
@router.post("/beers", response_model=BeerResponse)
def create_beer(
    beer: BeerCreate,
    db: Session = Depends(get_db),
    _=Depends(verify_token),
):
    return beer_service.create_beer(db, beer)


# 🔄 UPDATE DISPONIBILIDAD
@router.patch("/beers/{beer_id}/availability", response_model=BeerResponse)
def update_availability(
    beer_id: int,
    availability: BeerAvailabilityUpdate,
    db: Session = Depends(get_db),
    _=Depends(verify_token),
):
    return beer_service.update_availability(db, beer_id, availability)


# ✏ UPDATE COMPLETO
@router.put("/beers/{beer_id}", response_model=BeerResponse)
def update_beer(
    beer_id: int,
    beer_update: BeerUpdate,
    db: Session = Depends(get_db),
    _=Depends(verify_token),
):
    print("BEER UPDATE RECEIVED:", beer_update)
    return beer_service.update_beer(db, beer_id, beer_update)


# 📋 LISTADO ADMIN
@router.get("/beers", response_model=List[BeerResponse])
def list_beers_admin(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    order_by: str = Query("created_at"),
    direction: str = Query("desc"),
    db: Session = Depends(get_db),
    _=Depends(verify_token),
):
    query = db.query(Beer)

    if hasattr(Beer, order_by):
        column = getattr(Beer, order_by)
        if direction == "desc":
            query = query.order_by(column.desc())
        else:
            query = query.order_by(column.asc())
    else:
        query = query.order_by(Beer.created_at.desc())

    query = query.offset(skip).limit(limit)

    return query.all()


# 🗑 DELETE
@router.delete("/beers/{beer_id}")
def delete_beer(
    beer_id: int,
    db: Session = Depends(get_db),
    _=Depends(verify_token),
):
    print("ROUTER: llamando a soft_delete_beer service")
    beer_service.soft_delete_beer(db, beer_id)

    return {"message": f"Beer {beer_id} soft deleted successfully"}


@router.get("/beers/stats")
def beer_stats(
    db: Session = Depends(get_db),
    _=Depends(verify_token),
):
    return beer_service.get_beer_stats(db)
