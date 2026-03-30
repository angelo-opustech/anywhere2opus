import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Enum as SAEnum, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ResourceType(str, enum.Enum):
    VM = "VM"
    STORAGE = "STORAGE"
    NETWORK = "NETWORK"
    DATABASE = "DATABASE"
    LOADBALANCER = "LOADBALANCER"
    KUBERNETES = "KUBERNETES"
    FILESTORE = "FILESTORE"


class ResourceStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    STOPPED = "STOPPED"
    MIGRATING = "MIGRATING"
    MIGRATED = "MIGRATED"


class CloudResource(Base):
    __tablename__ = "cloud_resources"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    provider_id: Mapped[int] = mapped_column(
        ForeignKey("cloud_providers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_type: Mapped[ResourceType] = mapped_column(
        SAEnum(ResourceType, name="resourcetype", create_type=True),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    region: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, index=True)
    specs_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[ResourceStatus] = mapped_column(
        SAEnum(ResourceStatus, name="resourcestatus", create_type=True),
        default=ResourceStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    provider: Mapped["CloudProvider"] = relationship(  # noqa: F821
        "CloudProvider", back_populates=None, foreign_keys=[provider_id]
    )

    def __repr__(self) -> str:
        return (
            f"<CloudResource id={self.id} name={self.name!r} "
            f"type={self.resource_type} status={self.status}>"
        )
