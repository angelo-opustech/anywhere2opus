from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field


class ClientBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Client name")
    description: Optional[str] = Field(None, description="Optional description")


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


class ClientRead(ClientBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ClientList(BaseModel):
    total: int
    items: List[ClientRead]
