from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_migration_service
from app.models.migration import MigrationStatus
from app.schemas.migration import (
    MigrationJobCreate,
    MigrationJobList,
    MigrationJobRead,
    MigrationJobStatus,
    MigrationJobUpdate,
)
from app.services.migration_service import MigrationService

router = APIRouter(prefix="/migrations", tags=["Migrations"])


@router.get("", response_model=MigrationJobList, summary="List all migration jobs")
def list_migrations(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    job_status: Optional[MigrationStatus] = Query(
        None, alias="status", description="Filter by migration status"
    ),
    svc: MigrationService = Depends(get_migration_service),
):
    jobs, total = svc.list_migrations(skip=skip, limit=limit, status=job_status)
    return MigrationJobList(
        total=total,
        items=[MigrationJobRead.model_validate(j) for j in jobs],
    )


@router.post("", response_model=MigrationJobRead, status_code=status.HTTP_201_CREATED,
             summary="Create a new migration job")
def create_migration(
    payload: MigrationJobCreate,
    svc: MigrationService = Depends(get_migration_service),
):
    try:
        job = svc.create_migration(payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return MigrationJobRead.model_validate(job)


@router.get("/{migration_id}", response_model=MigrationJobRead,
            summary="Get a migration job by ID")
def get_migration(
    migration_id: int,
    svc: MigrationService = Depends(get_migration_service),
):
    try:
        job = svc.get_migration_or_raise(migration_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return MigrationJobRead.model_validate(job)


@router.post("/{migration_id}/start", response_model=MigrationJobRead,
             summary="Start a pending migration job")
def start_migration(
    migration_id: int,
    svc: MigrationService = Depends(get_migration_service),
):
    try:
        job = svc.start_migration(migration_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Migration execution error: {e}",
        )
    return MigrationJobRead.model_validate(job)


@router.post("/{migration_id}/cancel", response_model=MigrationJobRead,
             summary="Cancel a running or pending migration job")
def cancel_migration(
    migration_id: int,
    svc: MigrationService = Depends(get_migration_service),
):
    try:
        job = svc.cancel_migration(migration_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return MigrationJobRead.model_validate(job)


@router.get("/{migration_id}/status", response_model=MigrationJobStatus,
            summary="Get the current status of a migration job")
def get_migration_status(
    migration_id: int,
    svc: MigrationService = Depends(get_migration_service),
):
    try:
        job = svc.get_migration_status(migration_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return MigrationJobStatus.model_validate(job)
