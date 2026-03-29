from datetime import datetime
from typing import Optional, Any, Dict, List

from pydantic import BaseModel, Field
import json

from app.models.resource import ResourceType, ResourceStatus


class CloudResourceBase(BaseModel):
    provider_id: int = Field(..., description="ID of the cloud provider")
    resource_type: ResourceType = Field(..., description="Type of cloud resource")
    name: str = Field(..., min_length=1, max_length=255, description="Resource name")
    region: Optional[str] = Field(None, max_length=128, description="Cloud region")
    external_id: Optional[str] = Field(None, max_length=512, description="Provider-side resource ID")
    status: ResourceStatus = Field(ResourceStatus.ACTIVE, description="Resource status")


class CloudResourceCreate(CloudResourceBase):
    specs: Optional[Dict[str, Any]] = Field(
        None,
        description="Resource specifications as a dictionary",
    )

    def specs_to_json(self) -> Optional[str]:
        if self.specs is None:
            return None
        return json.dumps(self.specs)


class CloudResourceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    region: Optional[str] = Field(None, max_length=128)
    external_id: Optional[str] = Field(None, max_length=512)
    status: Optional[ResourceStatus] = None
    specs: Optional[Dict[str, Any]] = None

    def specs_to_json(self) -> Optional[str]:
        if self.specs is None:
            return None
        return json.dumps(self.specs)


class CloudResourceRead(CloudResourceBase):
    id: int
    specs_json: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @property
    def specs(self) -> Optional[Dict[str, Any]]:
        if self.specs_json is None:
            return None
        try:
            return json.loads(self.specs_json)
        except (json.JSONDecodeError, TypeError):
            return None


class CloudResourceList(BaseModel):
    total: int
    items: List[CloudResourceRead]
