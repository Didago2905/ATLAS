from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import engine, Base
import app.models.beer
from app.api import admin
from app.api import public

app = FastAPI(title=settings.app_name)

origins = [
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Crear tablas al iniciar
Base.metadata.create_all(bind=engine)

# Registrar routers
app.include_router(admin.router)

app.include_router(public.router)


@app.get("/")
def read_root():
    return {"message": f"{settings.app_name} is alive"}
