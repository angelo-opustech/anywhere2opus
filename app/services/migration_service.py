import json
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import structlog
from sqlalchemy.orm import Session

from app.models.migration import MigrationJob, MigrationStatus
from app.models.provider import CloudProvider
from app.models.resource import ResourceStatus
from app.schemas.migration import MigrationJobCreate, MigrationJobUpdate
from app.services.provider_service import ProviderService

logger = structlog.get_logger(__name__)


class MigrationService:
    """Service for managing cloud-to-cloud migration jobs."""

    def __init__(self, db: Session):
        self.db = db
        self._provider_service = ProviderService(db)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list_migrations(
        self,
        skip: int = 0,
        limit: int = 100,
        status: Optional[MigrationStatus] = None,
    ) -> Tuple[List[MigrationJob], int]:
        query = self.db.query(MigrationJob)
        if status is not None:
            query = query.filter(MigrationJob.status == status)
        total = query.count()
        jobs = query.order_by(MigrationJob.created_at.desc()).offset(skip).limit(limit).all()
        return jobs, total

    def get_migration(self, migration_id: int) -> Optional[MigrationJob]:
        return (
            self.db.query(MigrationJob)
            .filter(MigrationJob.id == migration_id)
            .first()
        )

    def get_migration_or_raise(self, migration_id: int) -> MigrationJob:
        job = self.get_migration(migration_id)
        if job is None:
            raise ValueError(f"Migration job {migration_id} not found")
        return job

    def create_migration(self, data: MigrationJobCreate) -> MigrationJob:
        # Validate that both providers exist
        self._provider_service.get_provider_or_raise(data.source_provider_id)
        self._provider_service.get_provider_or_raise(data.target_provider_id)

        job = MigrationJob(
            name=data.name,
            source_provider_id=data.source_provider_id,
            target_provider_id=data.target_provider_id,
            status=MigrationStatus.PENDING,
            resources_json=data.resources_to_json(),
            progress_percent=0.0,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        logger.info("migration_created", migration_id=job.id, name=job.name)
        return job

    def update_migration(self, migration_id: int, data: MigrationJobUpdate) -> MigrationJob:
        job = self.get_migration_or_raise(migration_id)
        if data.name is not None:
            job.name = data.name
        if data.status is not None:
            job.status = data.status
        if data.resources is not None:
            job.resources_json = data.resources_to_json()
        if data.progress_percent is not None:
            job.progress_percent = data.progress_percent
        if data.error_message is not None:
            job.error_message = data.error_message
        self.db.commit()
        self.db.refresh(job)
        return job

    # ------------------------------------------------------------------
    # Lifecycle operations
    # ------------------------------------------------------------------

    def start_migration(self, migration_id: int) -> MigrationJob:
        """Transition a PENDING migration to RUNNING and execute the workflow.

        The migration workflow:
          1. Validate source and target providers.
          2. Iterate over resources listed in resources_json.
          3. For each resource, fetch live details from the source provider.
          4. Update progress and finalize status.

        In production this should be dispatched to a background task queue
        (Celery, ARQ, etc.) — here it runs synchronously for simplicity.
        """
        job = self.get_migration_or_raise(migration_id)
        if job.status not in (MigrationStatus.PENDING, MigrationStatus.FAILED):
            raise ValueError(
                f"Cannot start migration in status '{job.status}'. "
                "Only PENDING or FAILED jobs can be started."
            )

        job.status = MigrationStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.progress_percent = 0.0
        job.error_message = None
        self.db.commit()

        try:
            source_provider = self._provider_service.get_provider_or_raise(
                job.source_provider_id
            )
            target_provider = self._provider_service.get_provider_or_raise(
                job.target_provider_id
            )

            source_client = self._provider_service.get_provider_client(source_provider)

            resources: list = []
            if job.resources_json:
                try:
                    resources = json.loads(job.resources_json)
                except (json.JSONDecodeError, TypeError):
                    pass

            if not resources:
                raise ValueError("No resources specified for migration")

            job.progress_percent = 5.0
            self.db.commit()

            migration_results = []
            total = len(resources)

            for idx, res in enumerate(resources):
                vm_id = res.get("vm_id") or res.get("id")
                if not vm_id:
                    logger.warning(
                        "migration_resource_no_id",
                        migration_id=migration_id,
                        resource=res,
                    )
                    continue

                logger.info(
                    "migration_processing_resource",
                    migration_id=migration_id,
                    vm_id=vm_id,
                    index=idx + 1,
                    total=total,
                )

                vm_details = source_client.get_vm(vm_id, region=res.get("region"))

                migration_results.append(
                    {
                        "source_vm_id": vm_id,
                        "source_vm_name": vm_details.get("name"),
                        "source_status": vm_details.get("status"),
                        "source_region": vm_details.get("region"),
                        "specs": vm_details.get("specs"),
                        "migration_step": "inspected",
                    }
                )

                job.progress_percent = 5.0 + ((idx + 1) / total) * 90.0
                self.db.commit()

            job.status = MigrationStatus.COMPLETED
            job.progress_percent = 100.0
            job.completed_at = datetime.now(timezone.utc)
            job.resources_json = json.dumps(migration_results)
            self.db.commit()
            logger.info("migration_completed", migration_id=migration_id)

        except Exception as exc:
            logger.error("migration_failed", migration_id=migration_id, error=str(exc))
            job.status = MigrationStatus.FAILED
            job.error_message = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            self.db.commit()

        self.db.refresh(job)
        return job

    def cancel_migration(self, migration_id: int) -> MigrationJob:
        """Cancel a migration that is PENDING or RUNNING."""
        job = self.get_migration_or_raise(migration_id)
        if job.status not in (MigrationStatus.PENDING, MigrationStatus.RUNNING):
            raise ValueError(
                f"Cannot cancel migration in status '{job.status}'. "
                "Only PENDING or RUNNING jobs can be cancelled."
            )
        job.status = MigrationStatus.CANCELLED
        job.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)
        logger.info("migration_cancelled", migration_id=migration_id)
        return job

    def get_migration_status(self, migration_id: int) -> MigrationJob:
        """Return the current status of a migration job."""
        return self.get_migration_or_raise(migration_id)
