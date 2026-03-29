from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.migration import MigrationJob, MigrationStatus
from app.models.provider import CloudProvider
from app.schemas.migration import (
    MigrationJobCreate,
    MigrationJobUpdate,
    MigrationJobRead,
    MigrationJobList,
    MigrationJobStatus,
)

router = APIRouter()


@router.get("/", response_model=MigrationJobList)
def list_migrations(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[MigrationStatus] = None,
    db: Session = Depends(get_db),
):
    query = db.query(MigrationJob)
    if status:
        query = query.filter(MigrationJob.status == status)
    total = query.count()
    items = query.order_by(MigrationJob.created_at.desc()).offset(skip).limit(limit).all()
    return MigrationJobList(total=total, items=[MigrationJobRead.model_validate(i) for i in items])


@router.post("/", response_model=MigrationJobRead, status_code=201)
def create_migration(payload: MigrationJobCreate, db: Session = Depends(get_db)):
    # Validate source and target providers exist
    source = db.query(CloudProvider).filter(CloudProvider.id == payload.source_provider_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source provider not found")
    target = db.query(CloudProvider).filter(CloudProvider.id == payload.target_provider_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target provider not found")

    job = MigrationJob(
        name=payload.name,
        source_provider_id=payload.source_provider_id,
        target_provider_id=payload.target_provider_id,
        resources_json=payload.resources_to_json(),
        status=MigrationStatus.PENDING,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return MigrationJobRead.model_validate(job)


@router.get("/{migration_id}", response_model=MigrationJobRead)
def get_migration(migration_id: int, db: Session = Depends(get_db)):
    job = db.query(MigrationJob).filter(MigrationJob.id == migration_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Migration not found")
    return MigrationJobRead.model_validate(job)


@router.get("/{migration_id}/status", response_model=MigrationJobStatus)
def get_migration_status(migration_id: int, db: Session = Depends(get_db)):
    job = db.query(MigrationJob).filter(MigrationJob.id == migration_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Migration not found")
    return MigrationJobStatus.model_validate(job)


@router.patch("/{migration_id}", response_model=MigrationJobRead)
def update_migration(migration_id: int, payload: MigrationJobUpdate, db: Session = Depends(get_db)):
    job = db.query(MigrationJob).filter(MigrationJob.id == migration_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Migration not found")
    if payload.name is not None:
        job.name = payload.name
    if payload.status is not None:
        job.status = payload.status
        if payload.status == MigrationStatus.RUNNING and job.started_at is None:
            job.started_at = datetime.now(timezone.utc)
        if payload.status in (MigrationStatus.COMPLETED, MigrationStatus.FAILED, MigrationStatus.CANCELLED):
            job.completed_at = datetime.now(timezone.utc)
    if payload.progress_percent is not None:
        job.progress_percent = payload.progress_percent
    if payload.error_message is not None:
        job.error_message = payload.error_message
    if payload.resources is not None:
        job.resources_json = payload.resources_to_json()
    db.commit()
    db.refresh(job)
    return MigrationJobRead.model_validate(job)


@router.post("/{migration_id}/start", response_model=MigrationJobStatus)
def start_migration(migration_id: int, db: Session = Depends(get_db)):
    job = db.query(MigrationJob).filter(MigrationJob.id == migration_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Migration not found")
    if job.status != MigrationStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Cannot start migration in status {job.status.value}")
    job.status = MigrationStatus.RUNNING
    job.started_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return MigrationJobStatus.model_validate(job)


@router.post("/{migration_id}/cancel", response_model=MigrationJobStatus)
def cancel_migration(migration_id: int, db: Session = Depends(get_db)):
    job = db.query(MigrationJob).filter(MigrationJob.id == migration_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Migration not found")
    if job.status in (MigrationStatus.COMPLETED, MigrationStatus.CANCELLED):
        raise HTTPException(status_code=400, detail=f"Cannot cancel migration in status {job.status.value}")
    job.status = MigrationStatus.CANCELLED
    job.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return MigrationJobStatus.model_validate(job)


@router.delete("/{migration_id}", status_code=204)
def delete_migration(migration_id: int, db: Session = Depends(get_db)):
    job = db.query(MigrationJob).filter(MigrationJob.id == migration_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Migration not found")
    if job.status == MigrationStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Cannot delete a running migration")
    db.delete(job)
    db.commit()
