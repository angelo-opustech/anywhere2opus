from fastapi import APIRouter

from app.api.providers import router as providers_router
from app.api.resources import router as resources_router
from app.api.migrations import router as migrations_router

api_router = APIRouter()

api_router.include_router(providers_router, prefix="/providers", tags=["Providers"])
api_router.include_router(resources_router, prefix="/resources", tags=["Resources"])
api_router.include_router(migrations_router, prefix="/migrations", tags=["Migrations"])
