from typing import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.provider_service import ProviderService
from app.services.resource_service import ResourceService
from app.services.migration_service import MigrationService


def get_provider_service(db: Session = Depends(get_db)) -> ProviderService:
    """FastAPI dependency that returns a ProviderService instance."""
    return ProviderService(db)


def get_resource_service(db: Session = Depends(get_db)) -> ResourceService:
    """FastAPI dependency that returns a ResourceService instance."""
    return ResourceService(db)


def get_migration_service(db: Session = Depends(get_db)) -> MigrationService:
    """FastAPI dependency that returns a MigrationService instance."""
    return MigrationService(db)
