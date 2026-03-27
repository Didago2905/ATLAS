from sqlalchemy.orm import Session
from app.models.beer import Beer
from fastapi import HTTPException
from app.schemas.beer import BeerUpdate
from app.schemas.beer import BeerAvailabilityUpdate


def soft_delete_beer(db: Session, beer_id: int):
    beer = db.query(Beer).filter(Beer.id == beer_id).first()

    if not beer:
        raise HTTPException(status_code=404, detail="Beer not found")

    beer.is_deleted = True
    db.commit()
    db.refresh(beer)

    return beer


from app.schemas.beer import BeerCreate


def create_beer(db: Session, beer_data: BeerCreate):
    data = beer_data.dict()
    
    # Asegurar defaults
    if "is_available" not in data or data["is_available"] is None:
        data["is_available"] = True
        
    if "is_deleted" not in data or data["is_deleted"] is None:
        data["is_deleted"] = False
        
    new_beer = Beer(**data)          

    db.add(new_beer)
    db.commit()
    db.refresh(new_beer)

    return new_beer


from app.schemas.beer import BeerUpdate


def update_beer(db: Session, beer_id: int, beer_data: BeerUpdate):
    beer = db.query(Beer).filter(Beer.id == beer_id).first()

    if not beer:
        raise HTTPException(status_code=404, detail="Beer not found")

    update_data = beer_data.dict(exclude_unset=True)
    print("SERVICE UPDATE DATA:", update_data)

    for key, value in update_data.items():
        setattr(beer, key, value)

    db.commit()
    db.refresh(beer)

    return beer


from app.schemas.beer import BeerAvailabilityUpdate


def update_availability(
    db: Session, beer_id: int, availability_data: BeerAvailabilityUpdate
):
    beer = db.query(Beer).filter(Beer.id == beer_id).first()

    if not beer:
        raise HTTPException(status_code=404, detail="Beer not found")

    beer.is_available = availability_data.is_available

    db.commit()
    db.refresh(beer)

    return beer


from sqlalchemy import func


def get_beer_stats(db: Session):
    total_beers = db.query(func.count(Beer.id)).scalar()

    active_beers = (
        db.query(func.count(Beer.id)).filter(Beer.is_deleted == False).scalar()
    )

    deleted_beers = (
        db.query(func.count(Beer.id)).filter(Beer.is_deleted == True).scalar()
    )

    available_beers = (
        db.query(func.count(Beer.id))
        .filter(Beer.is_available == True, Beer.is_deleted == False)
        .scalar()
    )

    average_abv = db.query(func.avg(Beer.abv)).filter(Beer.is_deleted == False).scalar()

    styles = (
        db.query(Beer.style, func.count(Beer.id))
        .filter(Beer.is_deleted == False)
        .group_by(Beer.style)
        .all()
    )

    styles_breakdown = {style: count for style, count in styles}

    return {
        "total_beers": total_beers,
        "active_beers": active_beers,
        "deleted_beers": deleted_beers,
        "available_beers": available_beers,
        "average_abv": round(average_abv, 2) if average_abv else 0,
        "styles_breakdown": styles_breakdown,
    }
