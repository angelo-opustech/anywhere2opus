from datetime import datetime
from typing import Optional, Any, Dict, List

from pydantic import BaseModel, Field, field_validator
import json

from app.models.provider import ProviderType


class CloudProviderBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Provider display name")
    type: ProviderType = Field(..., description="Cloud provider type")
    is_active: bool = Field(True, description="Whether this provider is active")
    client_id: Optional[int] = Field(None, description="Client this provider belongs to")


class CloudProviderCreate(CloudProviderBase):
    credentials: Optional[Dict[str, Any]] = Field(
        None,
        description="Provider credentials as a dictionary. Will be stored as JSON.",
    )

    @field_validator("credentials", mode="before")
    @classmethod
    def validate_credentials(cls, v):
        if v is not None and not isinstance(v, dict):
            raise ValueError("credentials must be a dictionary")
        return v

    def credentials_to_json(self) -> Optional[str]:
        if self.credentials is None:
            return None
        return json.dumps(self.credentials)


class CloudProviderUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    is_active: Optional[bool] = None
    client_id: Optional[int] = Field(None, description="Client this provider belongs to")
    credentials: Optional[Dict[str, Any]] = None

    def credentials_to_json(self) -> Optional[str]:
        if self.credentials is None:
            return None
        return json.dumps(self.credentials)


class CloudProviderRead(CloudProviderBase):
    id: int
    client_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CloudProviderList(BaseModel):
    total: int
    items: List[CloudProviderRead]
