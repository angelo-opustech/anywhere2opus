import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Boolean, DateTime, Enum as SAEnum, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ProviderType(str, enum.Enum):
    AWS = "AWS"
    GCP = "GCP"
    AZURE = "AZURE"
    OCI = "OCI"
    CLOUDSTACK = "CLOUDSTACK"


class CloudProvider(Base):
    __tablename__ = "cloud_providers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    client_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    type: Mapped[ProviderType] = mapped_column(
        SAEnum(ProviderType, name="providertype", create_type=True),
        nullable=False,
        index=True,
    )
    credentials_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    client: Mapped[Optional["Client"]] = relationship(  # noqa: F821
        "Client", back_populates="providers", foreign_keys=[client_id]
    )

    def __repr__(self) -> str:
        return f"<CloudProvider id={self.id} name={self.name!r} type={self.type}>"
