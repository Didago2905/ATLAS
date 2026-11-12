from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone
from fastapi import HTTPException

from app.models.beer import Beer
from app.schemas.beer import (
    BeerCreate,
    BeerUpdate,
    BeerAvailabilityUpdate,
)

import json
import os


def _lock_tap(db):
    # Serialize SQLite capacity checks BEFORE reading availability or positions.
    connection = db.connection()
    if connection.dialect.name == 'sqlite':
        if connection.connection.driver_connection.in_transaction:
            raise HTTPException(409, 'Tap change requires a fresh transaction')
        connection.exec_driver_sql('BEGIN IMMEDIATE')


def _inside_tap(beer):
    return beer.is_available is True and beer.is_deleted is False and beer.tap_position is not None


def _record_tap_entry(db, beer, was_inside):
    if was_inside or not _inside_tap(beer):
        return
    with db.no_autoflush:
        query = db.query(Beer).filter(Beer.is_available == True, Beer.is_deleted == False,
                                     Beer.tap_position != None)
        if beer.id is not None:
            query = query.filter(Beer.id != beer.id)
        if query.count() >= 16:
            db.rollback()
            raise HTTPException(400, 'Tap lleno (16 cervezas máximo)')
    beer.tap_entered_at = datetime.now(timezone.utc).replace(tzinfo=None)


def soft_delete_beer(db: Session, beer_id: int):
    beer = db.query(Beer).filter(Beer.id == beer_id).first()

    if not beer:
        raise HTTPException(status_code=404, detail="Beer not found")

    beer.is_deleted = True

    db.commit()
    db.refresh(beer)

    return beer


def create_beer(db: Session, beer_data: BeerCreate):
    _lock_tap(db)
    data = beer_data.dict()

    # Asegurar defaults
    if "is_available" not in data or data["is_available"] is None:
        data["is_available"] = True

    if "is_deleted" not in data or data["is_deleted"] is None:
        data["is_deleted"] = False

    new_beer = Beer(**data)
    _record_tap_entry(db, new_beer, False)

    db.add(new_beer)
    db.commit()
    db.refresh(new_beer)

    return new_beer


def update_beer(db: Session, beer_id: int, beer_data: BeerUpdate):
    if 'is_available' in beer_data.model_fields_set:
        _lock_tap(db)
    beer = db.query(Beer).populate_existing().filter(Beer.id == beer_id).first()

    if not beer:
        raise HTTPException(status_code=404, detail="Beer not found")

    update_data = beer_data.dict(exclude_unset=True)
    was_inside = _inside_tap(beer)
    print("SERVICE UPDATE DATA:", update_data)

    # ❌ evitar que frontend rompa tap_position
    update_data.pop("tap_position", None)

    # 🔥 1. aplicar update normal
    for key, value in update_data.items():
        setattr(beer, key, value)

    # 🔥 2. lógica tap
    if "is_available" in update_data:

        if beer.is_available:

            if beer.tap_position is None:

                next_pos = get_next_tap_position(db)

                if next_pos is None:
                    db.rollback()
                    raise HTTPException(
                        status_code=400, detail="Tap lleno (16 cervezas máximo)"
                    )

                beer.tap_position = next_pos
                print("ASSIGNED TAP POSITION:", next_pos)

        else:

            beer.tap_position = None
            print("REMOVED FROM TAP")

    _record_tap_entry(db, beer, was_inside)

        # ⭐ persistencia featured beers
    if "is_featured" in update_data:

        featured_beers = db.query(Beer).filter(Beer.is_featured == True).all()

        featured_ids = [b.id for b in featured_beers]

        latest_timestamp = max(
            [b.featured_updated_at or 0 for b in featured_beers], default=0
        )

        featured_path = "app/data/featured.json"

        with open(featured_path, "w") as f:
            json.dump(
                {"featured_beer_ids": featured_ids, "last_update": latest_timestamp},
                f,
                indent=2,
            )

    db.commit()
    db.refresh(beer)

    return beer


def update_availability(
    db: Session, beer_id: int, availability_data: BeerAvailabilityUpdate
):
    _lock_tap(db)
    beer = db.query(Beer).populate_existing().filter(Beer.id == beer_id).first()

    if not beer:
        raise HTTPException(status_code=404, detail="Beer not found")

    was_inside = _inside_tap(beer)
    beer.is_available = availability_data.is_available
    _record_tap_entry(db, beer, was_inside)

    db.commit()
    db.refresh(beer)

    return beer


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


def get_tap_beers(db: Session):

    return (
        db.query(Beer)
        .filter(
            Beer.is_deleted == False,
            Beer.is_available == True,
            Beer.tap_position != None,
        )
        .order_by(Beer.tap_position.asc())
        .distinct(Beer.id)
        .all()
    )


def get_next_tap_position(db: Session):

    positions = db.query(Beer.tap_position).filter(Beer.tap_position != None).all()

    used = sorted([p[0] for p in positions if p[0] is not None])

    for i in range(1, 17):

        if i not in used:
            return i

    return None
