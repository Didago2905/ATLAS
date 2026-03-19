from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from app.core.database import get_db
from app.models.beer import Beer
from app.schemas.beer import BeerResponse


router = APIRouter(tags=["Public"])


@router.get("/beers", response_model=List[BeerResponse])
def get_beers(
    available: Optional[bool] = Query(None),
    style: Optional[str] = Query(None),
    min_abv: Optional[float] = Query(None),
    max_abv: Optional[float] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    order_by: str = Query("created_at"),
    direction: str = Query("desc"),
    db: Session = Depends(get_db),
):
    query = db.query(Beer)
    query = query.filter(
    Beer.is_deleted == False,
    Beer.is_available == True
)
    # Filtros
    if available is not None:
        query = query.filter(Beer.is_available == available)

    if style:
        query = query.filter(Beer.style.ilike(f"%{style}%"))

    if min_abv is not None:
        query = query.filter(Beer.abv >= min_abv)

    if max_abv is not None:
        query = query.filter(Beer.abv <= max_abv)

    # Ordenamiento dinámico seguro
    if hasattr(Beer, order_by):
        column = getattr(Beer, order_by)
        if direction == "desc":
            query = query.order_by(column.desc())
        else:
            query = query.order_by(column.asc())
    else:
        query = query.order_by(Beer.created_at.desc())

    # Paginación
    query = query.offset(skip).limit(limit)

    return query.all()
