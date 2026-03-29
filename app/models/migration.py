import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Enum as SAEnum, Text, ForeignKey, Float, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MigrationStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MigrationJob(Base):
    __tablename__ = "migration_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_provider_id: Mapped[int] = mapped_column(
        ForeignKey("cloud_providers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    target_provider_id: Mapped[int] = mapped_column(
        ForeignKey("cloud_providers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[MigrationStatus] = mapped_column(
        SAEnum(MigrationStatus, name="migrationstatus", create_type=True),
        default=MigrationStatus.PENDING,
        nullable=False,
        index=True,
    )
    resources_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    progress_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
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

    source_provider: Mapped["CloudProvider"] = relationship(  # noqa: F821
        "CloudProvider", foreign_keys=[source_provider_id]
    )
    target_provider: Mapped["CloudProvider"] = relationship(  # noqa: F821
        "CloudProvider", foreign_keys=[target_provider_id]
    )

    def __repr__(self) -> str:
        return (
            f"<MigrationJob id={self.id} name={self.name!r} status={self.status} "
            f"progress={self.progress_percent:.1f}%>"
        )
