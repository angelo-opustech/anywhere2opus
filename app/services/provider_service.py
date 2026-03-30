from typing import List, Optional

import structlog
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.provider import CloudProvider, ProviderType
from app.providers.base import BaseProvider
from app.providers.factory import get_provider
from app.schemas.provider import CloudProviderCreate, CloudProviderUpdate
from app.utils.crypto import decrypt_credentials, encrypt_credentials

logger = structlog.get_logger(__name__)


class ProviderService:
    """Business logic for cloud provider management."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list_providers(
        self, skip: int = 0, limit: int = 100, active_only: bool = False,
        client_id: Optional[int] = None,
    ) -> tuple[List[CloudProvider], int]:
        query = self.db.query(CloudProvider)
        if active_only:
            query = query.filter(CloudProvider.is_active == True)  # noqa: E712
        if client_id is not None:
            query = query.filter(
                or_(CloudProvider.client_id == client_id, CloudProvider.client_id.is_(None))
            )
        total = query.count()
        providers = query.offset(skip).limit(limit).all()
        return providers, total

    def get_provider(self, provider_id: int) -> Optional[CloudProvider]:
        return (
            self.db.query(CloudProvider)
            .filter(CloudProvider.id == provider_id)
            .first()
        )

    def get_provider_or_raise(self, provider_id: int) -> CloudProvider:
        provider = self.get_provider(provider_id)
        if provider is None:
            raise ValueError(f"Provider {provider_id} not found")
        return provider

    def create_provider(self, data: CloudProviderCreate) -> CloudProvider:
        provider = CloudProvider(
            name=data.name,
            type=data.type,
            is_active=data.is_active,
            credentials_json=encrypt_credentials(data.credentials) if data.credentials is not None else None,
            client_id=data.client_id,
        )
        self.db.add(provider)
        self.db.commit()
        self.db.refresh(provider)
        logger.info("provider_created", provider_id=provider.id, name=provider.name)
        return provider

    def update_provider(
        self, provider_id: int, data: CloudProviderUpdate
    ) -> CloudProvider:
        provider = self.get_provider_or_raise(provider_id)
        if data.name is not None:
            provider.name = data.name
        if data.is_active is not None:
            provider.is_active = data.is_active
        if data.credentials is not None:
            provider.credentials_json = encrypt_credentials(data.credentials)
        self.db.commit()
        self.db.refresh(provider)
        logger.info("provider_updated", provider_id=provider_id)
        return provider

    def delete_provider(self, provider_id: int) -> bool:
        provider = self.get_provider_or_raise(provider_id)
        self.db.delete(provider)
        self.db.commit()
        logger.info("provider_deleted", provider_id=provider_id)
        return True

    # ------------------------------------------------------------------
    # Provider client factory
    # ------------------------------------------------------------------

    def get_provider_client(self, provider_model: CloudProvider) -> BaseProvider:
        """Instantiate a provider client using stored credentials when available."""
        creds: dict = {}
        if provider_model.credentials_json:
            try:
                creds = decrypt_credentials(provider_model.credentials_json)
            except Exception as exc:
                logger.warning(
                    "invalid_credentials_json",
                    provider_id=provider_model.id,
                    error=str(exc),
                )
        return get_provider(provider_model.type, credentials=creds)

    def test_connection(self, provider_id: int) -> bool:
        """Test connectivity for a provider.  Returns True if successful."""
        provider = self.get_provider_or_raise(provider_id)
        try:
            client = self.get_provider_client(provider)
            return client.test_connection()
        except Exception as e:
            logger.warning("provider_connection_test_failed", provider_id=provider_id, error=str(e))
            return False
