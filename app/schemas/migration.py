from datetime import datetime
from typing import Optional, Any, Dict, List

from pydantic import BaseModel, Field, model_validator
import json

from app.models.migration import MigrationStatus


class MigrationJobBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Migration job name")
    source_provider_id: int = Field(..., description="Source cloud provider ID")
    target_provider_id: int = Field(..., description="Target cloud provider ID")

    @model_validator(mode="after")
    def validate_different_providers(self):
        if self.source_provider_id == self.target_provider_id:
            raise ValueError("source_provider_id and target_provider_id must be different")
        return self


class MigrationJobCreate(MigrationJobBase):
    resources: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="List of resource definitions to migrate",
    )

    def resources_to_json(self) -> Optional[str]:
        if self.resources is None:
            return None
        return json.dumps(self.resources)


class MigrationJobUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    status: Optional[MigrationStatus] = None
    resources: Optional[List[Dict[str, Any]]] = None
    progress_percent: Optional[float] = Field(None, ge=0.0, le=100.0)
    error_message: Optional[str] = None

    def resources_to_json(self) -> Optional[str]:
        if self.resources is None:
            return None
        return json.dumps(self.resources)


class MigrationJobRead(MigrationJobBase):
    id: int
    status: MigrationStatus
    resources_json: Optional[str] = None
    progress_percent: float
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @property
    def resources(self) -> Optional[List[Dict[str, Any]]]:
        if self.resources_json is None:
            return None
        try:
            return json.loads(self.resources_json)
        except (json.JSONDecodeError, TypeError):
            return None


class MigrationJobList(BaseModel):
    total: int
    items: List[MigrationJobRead]


class MigrationJobStatus(BaseModel):
    id: int
    name: str
    status: MigrationStatus
    progress_percent: float
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
