from typing import Any, Dict, Optional

import structlog

from app.config import settings
from app.models.provider import ProviderType
from app.providers.base import BaseProvider
from app.providers.aws import AWSProvider
from app.providers.gcp import GCPProvider
from app.providers.azure import AzureProvider
from app.providers.oci import OCIProvider
from app.providers.cloudstack import CloudStackProvider

logger = structlog.get_logger(__name__)


def get_provider(
    provider_type: ProviderType,
    credentials: Optional[Dict[str, Any]] = None,
) -> BaseProvider:
    """Factory: instantiate the appropriate cloud provider.

    If credentials dict is given, uses those. Otherwise falls back to app settings.
    """
    creds = credentials or {}

    if provider_type == ProviderType.AWS:
        return AWSProvider(
            access_key_id=creds.get("access_key_id", settings.aws_access_key_id or ""),
            secret_access_key=creds.get("secret_access_key", settings.aws_secret_access_key or ""),
            region=creds.get("region", settings.aws_default_region),
            session_token=creds.get("session_token", settings.aws_session_token),
        )

    if provider_type == ProviderType.GCP:
        return GCPProvider(
            project_id=creds.get("project_id", settings.gcp_project_id or ""),
            service_account_key_file=creds.get("service_account_key_file", settings.gcp_service_account_key_file),
            service_account_key_json=creds.get("service_account_key_json", settings.gcp_service_account_key_json),
        )

    if provider_type == ProviderType.AZURE:
        return AzureProvider(
            subscription_id=creds.get("subscription_id", settings.azure_subscription_id or ""),
            tenant_id=creds.get("tenant_id", settings.azure_tenant_id or ""),
            client_id=creds.get("client_id", settings.azure_client_id or ""),
            client_secret=creds.get("client_secret", settings.azure_client_secret or ""),
        )

    if provider_type == ProviderType.OCI:
        return OCIProvider(
            user_ocid=creds.get("user_ocid", settings.oci_user_ocid or ""),
            fingerprint=creds.get("fingerprint", settings.oci_fingerprint or ""),
            tenancy_ocid=creds.get("tenancy_ocid", settings.oci_tenancy_ocid or ""),
            region=creds.get("region", settings.oci_region),
            private_key_file=creds.get("private_key_file", settings.oci_private_key_file),
            private_key_content=creds.get("private_key_content", settings.oci_private_key_content),
        )

    if provider_type == ProviderType.CLOUDSTACK:
        return CloudStackProvider(
            api_url=creds.get("api_url", settings.cloudstack_url or ""),
            api_key=creds.get("api_key", settings.cloudstack_api_key or ""),
            secret_key=creds.get("secret_key", settings.cloudstack_secret_key or ""),
            zone_id=creds.get("zone_id", settings.cloudstack_zone_id),
        )

    raise ValueError(f"Unsupported provider type: {provider_type}")
