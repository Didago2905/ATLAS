from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.core.config import settings
from app.core.database import engine, Base
import app.models.beer
from app.api import admin, public

app = FastAPI(
    title=settings.app_name,
    swagger_ui_parameters={"persistAuthorization": True}
)

# 🔥 CORS (VERSIÓN LIMPIA Y ÚNICA)
origins = [
    "http://localhost:5173",
    "http://192.168.100.19:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 👇 CONFIGURACIÓN OPENAPI PERSONALIZADA
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=settings.app_name,
        version="1.0.0",
        description="API ATLAS",
        routes=app.routes,
    )

    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    }

    openapi_schema["security"] = [{"BearerAuth": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# ----------------------------

# Crear tablas al iniciar
Base.metadata.create_all(bind=engine)

# Registrar routers
app.include_router(admin.router)
app.include_router(public.router)


@app.get("/")
def read_root():
    return {"message": f"{settings.app_name} is alive"}