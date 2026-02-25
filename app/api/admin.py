from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.beer import Beer
from app.schemas.beer import BeerCreate, BeerResponse
from fastapi import Query

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post("/beers", response_model=BeerResponse)
def create_beer(beer: BeerCreate, db: Session = Depends(get_db)):
    new_beer = Beer(**beer.dict())

    db.add(new_beer)
    db.commit()
    db.refresh(new_beer)

    return new_beer


from fastapi import HTTPException
from app.schemas.beer import BeerAvailabilityUpdate


@router.patch("/beers/{beer_id}/availability", response_model=BeerResponse)
def update_availability(
    beer_id: int, availability: BeerAvailabilityUpdate, db: Session = Depends(get_db)
):
    beer = db.query(Beer).filter(Beer.id == beer_id).first()

    if not beer:
        raise HTTPException(status_code=404, detail="Beer not found")

    beer.is_available = availability.is_available

    db.commit()
    db.refresh(beer)

    return beer


from app.schemas.beer import BeerUpdate


@router.put("/beers/{beer_id}", response_model=BeerResponse)
def update_beer(beer_id: int, beer_update: BeerUpdate, db: Session = Depends(get_db)):
    beer = db.query(Beer).filter(Beer.id == beer_id).first()

    if not beer:
        raise HTTPException(status_code=404, detail="Beer not found")

    update_data = beer_update.dict(exclude_unset=True)

    for key, value in update_data.items():
        setattr(beer, key, value)

    db.commit()
    db.refresh(beer)

    return beer


from typing import List


@router.get("/beers", response_model=List[BeerResponse])
def list_beers_admin(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    order_by: str = Query("created_at"),
    direction: str = Query("desc"),
    db: Session = Depends(get_db),
):
    query = db.query(Beer)

    # Orden dinámico
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


from fastapi import HTTPException


@router.delete("/beers/{beer_id}")
def delete_beer(beer_id: int, db: Session = Depends(get_db)):
    beer = db.query(Beer).filter(Beer.id == beer_id).first()

    if not beer:
        raise HTTPException(status_code=404, detail="Beer not found")

    db.delete(beer)
    db.commit()

    return {"message": f"Beer {beer_id} deleted successfully"}
