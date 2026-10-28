from fastapi import APIRouter, Depends, Query, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy import case
import shutil
import os
import time

from app.core.database import get_db
from app.core.security import verify_token
from app.models.beer import Beer
from app.schemas.beer import (
    BeerCreate,
    BeerResponse,
    BeerUpdate,
    BeerAvailabilityUpdate,
)
from app.services import beer_service, museum_upload_service

router = APIRouter(prefix="/admin", tags=["Admin"])

from pydantic import BaseModel
from app.core.auth import create_access_token
from fastapi import Form

class LoginRequest(BaseModel):
    password: str


@router.post("/login")
def login(data: LoginRequest):

    if data.password != "atlas123":
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": "admin"})

    return {"access_token": token, "token_type": "bearer"}


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

    query = query.order_by(
        case((Beer.tap_position != None, 0), else_=1),
        Beer.tap_position.asc(),
        Beer.created_at.desc(),
    )

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


# 🔥 NUEVO ENDPOINT — UPLOAD IMAGEN
from fastapi import UploadFile, File, HTTPException
from PIL import Image
import os


@router.post("/beers/{beer_id}/upload-image")
def upload_beer_image(
    beer_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(verify_token),
):

    beer = db.get(Beer, beer_id)
    if beer is None or beer.is_deleted:
        raise HTTPException(status_code=404, detail="Beer not found")
    return museum_upload_service.upload_artwork(
        file, "tap", {
            "name": beer.name, "style": beer.style,
            "abv": str(beer.abv) if beer.abv is not None else "", "year": "",
        }, beer=beer, db=db,
    )


CARD_BACKGROUND_TARGET_SIZE = (1080, 1920)
CARD_BACKGROUND_JPEG_QUALITY = 84


def _resize_cover(img: Image.Image, target_width: int, target_height: int) -> Image.Image:
    src_width, src_height = img.size
    scale = max(target_width / src_width, target_height / src_height)
    resized_width = int(src_width * scale)
    resized_height = int(src_height * scale)
    resample = getattr(Image, "Resampling", Image).LANCZOS
    resized = img.resize((resized_width, resized_height), resample=resample)
    left = (resized_width - target_width) // 2
    top = (resized_height - target_height) // 2
    return resized.crop(
        (left, top, left + target_width, top + target_height)
    )


@router.post("/beers/{beer_id}/upload-card-background")
def upload_beer_card_background(
    beer_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(verify_token),
):
    folder = "frontend/public/images/beerCardBackgrounds"
    os.makedirs(folder, exist_ok=True)

    file_path = f"{folder}/{beer_id}.jpg"

    try:
        img = Image.open(file.file)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid image file"
        )

    img = img.convert("RGB")
    img = _resize_cover(
        img,
        *CARD_BACKGROUND_TARGET_SIZE
    )

    img.save(
        file_path,
        format="JPEG",
        quality=CARD_BACKGROUND_JPEG_QUALITY,
        optimize=True,
        progressive=True,
    )

    version = int(time.time())

    beercard_background_url = (
        f"/images/beerCardBackgrounds/{beer_id}.jpg?v={version}"
    )

    beer = db.query(Beer).get(beer_id)

    if not beer:
        raise HTTPException(
            status_code=404,
            detail="Beer not found"
        )

    print(
        "SAVING URL:",
        beercard_background_url
    )

    beer.beercard_background_url = (
        beercard_background_url
    )

    db.commit()

    print(
        "DB URL AFTER COMMIT:",
        beer.beercard_background_url
    )

    return {
        "beercard_background_url":
            beercard_background_url
    }


@router.post("/upload-image")
def upload_museum_image(
    file: UploadFile = File(...),
    type: str = "fichas/antiguas",
    db: Session = Depends(get_db),
    _=Depends(verify_token),
):

    return museum_upload_service.upload_artwork(file, type, register=False)


@router.post("/museum")


def upload_museum(
    file: UploadFile = File(...),
    name: str = Form(""),
    style: str = Form(""),
    abv: str = Form(""),
    year: str = Form(""),
    type: str = Form("fichas/antiguas"),
    db: Session = Depends(get_db),
    _=Depends(verify_token),
):

    return museum_upload_service.upload_artwork(
        file, type, {"name": name, "style": style, "abv": abv, "year": year},
    )
