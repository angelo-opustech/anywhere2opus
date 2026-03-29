from contextlib import asynccontextmanager
from datetime import datetime

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import create_tables
from app.api.routes.providers import router as providers_router
from app.api.routes.resources import router as resources_router
from app.api.routes.migrations import router as migrations_router
from app.api.routes.configuration import router as configuration_router

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "anywhere2opus_startup",
        app=settings.app_name,
        env=settings.app_env,
        debug=settings.app_debug,
    )
    create_tables()
    yield
    logger.info("anywhere2opus_shutdown", app=settings.app_name)


app = FastAPI(
    title="anywhere2opus",
    version="1.0.0",
    description=(
        "Cloud Migration API — connect to AWS, GCP, Azure, OCI, and CloudStack (Opus) "
        "to discover, manage, and migrate cloud resources between providers."
    ),
    contact={
        "name": "Opus Technology",
        "url": "https://opustech.com.br",
    },
    license_info={"name": "MIT"},
    lifespan=lifespan,
    debug=settings.app_debug,
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
API_PREFIX = "/api/v1"

app.include_router(providers_router, prefix=API_PREFIX)
app.include_router(resources_router, prefix=API_PREFIX)
app.include_router(migrations_router, prefix=API_PREFIX)
app.include_router(configuration_router, prefix=API_PREFIX)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Health"], summary="Application health check")
async def health_check():
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/", tags=["Health"], include_in_schema=False)
async def root():
    return JSONResponse(
        content={
            "app": "anywhere2opus",
            "version": "1.0.0",
            "docs": "/docs",
            "redoc": "/redoc",
            "health": "/health",
        }
    )
