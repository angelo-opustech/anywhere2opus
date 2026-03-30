from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import create_tables
from app.api.routes.providers import router as providers_router
from app.api.routes.resources import router as resources_router
from app.api.routes.migrations import router as migrations_router
from app.api.routes.configuration import router as configuration_router
from app.api.routes.configuration_new_providers import router as configuration_new_providers_router

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
        "Cloud Migration API — connect to AWS, GCP, Azure, OCI, and Opus "
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
BASE_PATH = "/connectors"
API_PREFIX = "/api/v1"
PUBLISHED_API_PREFIX = f"{BASE_PATH}{API_PREFIX}"

app.include_router(providers_router, prefix=API_PREFIX)
app.include_router(resources_router, prefix=API_PREFIX)
app.include_router(migrations_router, prefix=API_PREFIX)
app.include_router(configuration_router, prefix=API_PREFIX)
app.include_router(configuration_new_providers_router, prefix=API_PREFIX)
app.include_router(providers_router, prefix=PUBLISHED_API_PREFIX)
app.include_router(resources_router, prefix=PUBLISHED_API_PREFIX)
app.include_router(migrations_router, prefix=PUBLISHED_API_PREFIX)
app.include_router(configuration_router, prefix=PUBLISHED_API_PREFIX)
app.include_router(configuration_new_providers_router, prefix=PUBLISHED_API_PREFIX)

# ---------------------------------------------------------------------------
# Static Files
# ---------------------------------------------------------------------------
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    app.mount(f"{BASE_PATH}/static", StaticFiles(directory=str(static_dir)), name="opus-static")


def _serve_index():
    static_file = Path(__file__).parent / "static" / "index.html"
    if static_file.exists():
        return FileResponse(str(static_file), media_type="text/html")
    return {"message": "Configuration interface not available"}


@app.get("/", tags=["Web"], summary="Empty root", status_code=204)
async def root():
    return Response(status_code=204)


@app.get(BASE_PATH, tags=["Web"], summary="Published Opus Configuration Interface")
async def opus_root():
    return _serve_index()


@app.get(f"{BASE_PATH}/", include_in_schema=False)
async def opus_root_slash():
    return _serve_index()


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
