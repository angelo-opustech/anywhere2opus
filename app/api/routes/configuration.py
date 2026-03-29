"""Configuration and connection testing endpoints for cloud providers."""

import base64
import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import structlog

from app.config import settings
from app.database import get_db
from app.models.provider import CloudProvider, ProviderType
from app.providers.factory import get_provider
from app.schemas.configuration import (
    CloudStackAccountInfo,
    CloudStackConfig,
    CloudStackTestResult,
    CloudStackZonesList,
    CloudStackZone,
    CloudStackSaveRequest,
    CloudStackSavedProvider,
    ProviderConfigTest,
    ProviderTestResult,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/configuration", tags=["Configuration & Testing"])


def _get_fernet() -> Fernet:
    """Derive a Fernet key from the application secret_key."""
    key_bytes = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


# ============================================================================
# CloudStack Configuration & Testing
# ============================================================================

@router.post(
    "/cloudstack/test",
    response_model=CloudStackTestResult,
    summary="Test CloudStack API connection",
    description="Test connectivity to a CloudStack API without saving configuration"
)
def test_cloudstack_connection(config: CloudStackConfig):
    """Test connection to CloudStack API and return account/domain info."""
    try:
        logger.info("cloudstack_test_start", api_url=str(config.api_url), verify_ssl=config.verify_ssl)

        provider = get_provider(
            ProviderType.CLOUDSTACK,
            credentials={
                "api_url": str(config.api_url),
                "api_key": config.api_key,
                "secret_key": config.secret_key,
                "zone_id": config.zone_id,
            },
        )

        connected = provider.test_connection()

        if not connected:
            logger.warning("cloudstack_test_failed_no_response")
            return CloudStackTestResult(
                connected=False,
                api_url=str(config.api_url),
                error_message="Failed to connect - no response from API",
            )

        # Get account/domain info
        account_data = provider.get_account_info()
        account_info = CloudStackAccountInfo(**account_data) if account_data else None

        # Get zones
        try:
            zones_data = provider.list_regions()
            zones_count = len(zones_data)
        except Exception as e:
            logger.error("cloudstack_list_zones_failed", error=str(e))
            zones_count = 0
            zones_data = []

        logger.info(
            "cloudstack_test_success",
            api_url=str(config.api_url),
            zones_count=zones_count,
            account=account_info.account if account_info else None,
            domain=account_info.domain if account_info else None,
        )

        return CloudStackTestResult(
            connected=True,
            api_url=str(config.api_url),
            zones_found=zones_count,
            account_info=account_info,
            details={"zones": zones_data},
        )

    except Exception as e:
        logger.error("cloudstack_test_exception", error=str(e))
        return CloudStackTestResult(
            connected=False,
            api_url=str(config.api_url),
            error_message=str(e),
        )


@router.post(
    "/cloudstack/save",
    response_model=CloudStackSavedProvider,
    summary="Save CloudStack credentials securely",
    description="Test connection, identify account/domain, then store credentials encrypted in the database",
    status_code=status.HTTP_201_CREATED,
)
def save_cloudstack_credentials(
    request: CloudStackSaveRequest,
    db: Session = Depends(get_db),
):
    """Validate credentials, identify account/domain, and store encrypted in DB."""
    # Step 1: Test connection
    provider = get_provider(
        ProviderType.CLOUDSTACK,
        credentials={
            "api_url": str(request.api_url),
            "api_key": request.api_key,
            "secret_key": request.secret_key,
            "zone_id": request.zone_id,
        },
    )

    if not provider.test_connection():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot save: connection to CloudStack API failed.",
        )

    # Step 2: Get account/domain info
    account_data = provider.get_account_info()
    account = account_data.get("account", "unknown")
    domain = account_data.get("domain", "unknown")

    # Step 3: Auto-generate name if not provided
    name = request.name or f"CloudStack {domain}/{account}"

    # Step 4: Encrypt credentials
    fernet = _get_fernet()
    credentials_payload = {
        "api_url": str(request.api_url),
        "api_key": request.api_key,
        "secret_key": request.secret_key,
        "zone_id": request.zone_id,
        "verify_ssl": request.verify_ssl,
        "account": account,
        "domain": domain,
    }
    encrypted = fernet.encrypt(json.dumps(credentials_payload).encode()).decode()

    # Step 5: Upsert in DB (update if same api_url already saved)
    existing = (
        db.query(CloudProvider)
        .filter(CloudProvider.type == ProviderType.CLOUDSTACK)
        .filter(CloudProvider.name == name)
        .first()
    )

    if existing:
        existing.credentials_json = encrypted
        existing.is_active = True
        db_provider = existing
    else:
        db_provider = CloudProvider(
            name=name,
            type=ProviderType.CLOUDSTACK,
            credentials_json=encrypted,
            is_active=True,
        )
        db.add(db_provider)

    db.commit()
    db.refresh(db_provider)

    logger.info("cloudstack_credentials_saved", provider_id=db_provider.id, name=name, domain=domain, account=account)

    return CloudStackSavedProvider(
        id=db_provider.id,
        name=db_provider.name,
        api_url=str(request.api_url),
        account=account,
        domain=domain,
        is_active=db_provider.is_active,
        created_at=db_provider.created_at.isoformat(),
    )


@router.get(
    "/cloudstack/providers",
    response_model=List[CloudStackSavedProvider],
    summary="List saved CloudStack providers",
    description="Return all saved CloudStack credentials (sensitive data masked)",
)
def list_cloudstack_providers(db: Session = Depends(get_db)):
    """List all saved CloudStack providers with decrypted metadata (no keys exposed)."""
    providers = (
        db.query(CloudProvider)
        .filter(CloudProvider.type == ProviderType.CLOUDSTACK)
        .filter(CloudProvider.is_active == True)
        .order_by(CloudProvider.created_at.desc())
        .all()
    )

    fernet = _get_fernet()
    result = []
    for p in providers:
        account = None
        domain = None
        api_url = ""
        try:
            data = json.loads(fernet.decrypt(p.credentials_json.encode()).decode())
            account = data.get("account")
            domain = data.get("domain")
            api_url = data.get("api_url", "")
        except Exception:
            pass

        result.append(CloudStackSavedProvider(
            id=p.id,
            name=p.name,
            api_url=api_url,
            account=account,
            domain=domain,
            is_active=p.is_active,
            created_at=p.created_at.isoformat(),
        ))

    return result

