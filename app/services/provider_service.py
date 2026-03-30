import json
from typing import List, Optional

import structlog
from sqlalchemy.orm import Session

from app.config import settings
from app.models.provider import CloudProvider, ProviderType
from app.providers.base import BaseProvider
from app.providers.aws import AWSProvider
from app.providers.gcp import GCPProvider
from app.providers.azure import AzureProvider
from app.providers.oci import OCIProvider
from app.providers.cloudstack import CloudStackProvider
from app.schemas.provider import CloudProviderCreate, CloudProviderUpdate

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
            query = query.filter(CloudProvider.client_id == client_id)
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
            credentials_json=data.credentials_to_json(),
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
            provider.credentials_json = data.credentials_to_json()
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
        """Instantiate and return the appropriate BaseProvider subclass for
        the given CloudProvider ORM model.  Credentials stored in
        ``credentials_json`` override the global settings from environment
        variables so that per-provider credentials can be configured at
        runtime through the API.
        """
        creds: dict = {}
        if provider_model.credentials_json:
            try:
                creds = json.loads(provider_model.credentials_json)
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    "invalid_credentials_json", provider_id=provider_model.id
                )

        provider_type = provider_model.type

        if provider_type == ProviderType.AWS:
            return AWSProvider(
                access_key_id=creds.get("aws_access_key_id") or settings.aws_access_key_id or "",
                secret_access_key=creds.get("aws_secret_access_key") or settings.aws_secret_access_key or "",
                region=creds.get("region") or settings.aws_default_region,
                session_token=creds.get("aws_session_token") or settings.aws_session_token,
            )

        if provider_type == ProviderType.GCP:
            return GCPProvider(
                project_id=creds.get("project_id") or settings.gcp_project_id or "",
                service_account_key_file=creds.get("service_account_key_file")
                or settings.gcp_service_account_key_file,
                service_account_key_json=creds.get("service_account_key_json")
                or settings.gcp_service_account_key_json,
                default_region=creds.get("region", "us-central1"),
            )

        if provider_type == ProviderType.AZURE:
            return AzureProvider(
                subscription_id=creds.get("subscription_id") or settings.azure_subscription_id or "",
                tenant_id=creds.get("tenant_id") or settings.azure_tenant_id or "",
                client_id=creds.get("client_id") or settings.azure_client_id or "",
                client_secret=creds.get("client_secret") or settings.azure_client_secret or "",
                default_location=creds.get("location", "eastus"),
            )

        if provider_type == ProviderType.OCI:
            return OCIProvider(
                user_ocid=creds.get("user_ocid") or settings.oci_user_ocid or "",
                fingerprint=creds.get("fingerprint") or settings.oci_fingerprint or "",
                tenancy_ocid=creds.get("tenancy_ocid") or settings.oci_tenancy_ocid or "",
                region=creds.get("region") or settings.oci_region,
                private_key_file=creds.get("private_key_file") or settings.oci_private_key_file,
                private_key_content=creds.get("private_key_content") or settings.oci_private_key_content,
                compartment_id=creds.get("compartment_id"),
            )

        if provider_type == ProviderType.CLOUDSTACK:
            return CloudStackProvider(
                api_url=creds.get("api_url") or settings.opus_url or "",
                api_key=creds.get("api_key") or settings.opus_api_key or "",
                secret_key=creds.get("secret_key") or settings.opus_secret_key or "",
                zone_id=creds.get("zone_id") or settings.opus_zone_id,
            )

        raise ValueError(f"Unsupported provider type: {provider_type}")

    def test_connection(self, provider_id: int) -> bool:
        """Test connectivity for a provider.  Returns True if successful."""
        provider = self.get_provider_or_raise(provider_id)
        try:
            client = self.get_provider_client(provider)
            return client.test_connection()
        except Exception as e:
            logger.warning("provider_connection_test_failed", provider_id=provider_id, error=str(e))
            return False
