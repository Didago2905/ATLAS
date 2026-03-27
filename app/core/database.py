from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from typing import Generator

from app.core.config import settings

# 🔗 Usar configuración centralizada
DATABASE_URL = settings.database_url

# ⚙️ Engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}  # solo para SQLite
)

# 🧠 Sesión
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# 🧱 Base para modelos
Base = declarative_base()


# 🔄 Dependency para FastAPI
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()