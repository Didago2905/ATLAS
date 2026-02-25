from sqlalchemy import Column, Integer, String, Float, Boolean, Text, DateTime
from datetime import datetime
from app.core.database import Base


class Beer(Base):
    __tablename__ = "beers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    brewery = Column(String(255), nullable=False)
    style = Column(String(100), nullable=False)

    abv = Column(Float, nullable=True)
    ibu = Column(Float, nullable=True)

    description = Column(Text, nullable=True)
    origin = Column(String(255), nullable=True)
    image_url = Column(String(500), nullable=True)

    is_available = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
