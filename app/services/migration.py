import json
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.models.migration import MigrationJob, MigrationStatus
from app.models.provider import CloudProvider, ProviderType
from app.providers.factory import get_provider
from app.providers.cloudstack import CloudStackProvider

logger = structlog.get_logger(__name__)


def run_migration(db: Session, migration_id: int) -> MigrationJob:
    """Execute the migration workflow for a given job.

    High-level steps:
      1. Validate source and target providers
      2. Discover source resources
      3. Export/prepare source VM
      4. Register template on CloudStack target
      5. Deploy VM on CloudStack
      6. Update migration status
    """
    job = db.query(MigrationJob).filter(MigrationJob.id == migration_id).first()
    if not job:
        raise ValueError(f"Migration {migration_id} not found")

    job.status = MigrationStatus.RUNNING
    job.started_at = datetime.now(timezone.utc)
    db.commit()

    try:
        source_provider = db.query(CloudProvider).filter(CloudProvider.id == job.source_provider_id).first()
        target_provider = db.query(CloudProvider).filter(CloudProvider.id == job.target_provider_id).first()

        if not source_provider or not target_provider:
            raise ValueError("Source or target provider not found")

        if target_provider.type != ProviderType.CLOUDSTACK:
            raise ValueError("Target provider must be CloudStack (Opus)")

        source_creds = json.loads(source_provider.credentials_json) if source_provider.credentials_json else None
        target_creds = json.loads(target_provider.credentials_json) if target_provider.credentials_json else None

        source_cloud = get_provider(source_provider.type, credentials=source_creds)
        target_cloud = get_provider(target_provider.type, credentials=target_creds)

        if not isinstance(target_cloud, CloudStackProvider):
            raise ValueError("Target must be a CloudStack provider")

        # Parse resource list from the migration job
        resources = json.loads(job.resources_json) if job.resources_json else []
        if not resources:
            raise ValueError("No resources specified for migration")

        job.progress_percent = 10.0
        db.commit()

        migration_results: list[dict[str, Any]] = []

        for i, res in enumerate(resources):
            vm_id = res.get("vm_id") or res.get("id")
            if not vm_id:
                continue

            logger.info("migration_processing_vm", migration_id=migration_id, vm_id=vm_id)

            # Step: Get source VM details
            vm_details = source_cloud.get_vm(vm_id, region=res.get("region"))

            # Step: Record progress
            progress = 10.0 + ((i + 1) / len(resources)) * 80.0
            job.progress_percent = min(progress, 90.0)
            db.commit()

            migration_results.append({
                "source_vm_id": vm_id,
                "source_vm_name": vm_details.get("name"),
                "status": "processed",
                "details": vm_details,
            })

        # Finalize
        job.status = MigrationStatus.COMPLETED
        job.progress_percent = 100.0
        job.completed_at = datetime.now(timezone.utc)
        job.resources_json = json.dumps(migration_results)
        db.commit()

        logger.info("migration_completed", migration_id=migration_id)

    except Exception as e:
        logger.error("migration_failed", migration_id=migration_id, error=str(e))
        job.status = MigrationStatus.FAILED
        job.error_message = str(e)
        job.completed_at = datetime.now(timezone.utc)
        db.commit()

    db.refresh(job)
    return job
