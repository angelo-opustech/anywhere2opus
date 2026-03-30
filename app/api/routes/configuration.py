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
    AWSAccountInfo,
    AWSConfig,
    AWSSaveRequest,
    AWSSavedProvider,
    AWSTestResult,
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


def _decrypt_provider_credentials(db_provider: CloudProvider) -> Dict[str, Any]:
    fernet = _get_fernet()
    try:
        return json.loads(fernet.decrypt(db_provider.credentials_json.encode()).decode())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to decrypt credentials: {e}")


# ============================================================================
# CloudStack Configuration & Testing
# ============================================================================


@router.post(
    "/aws/test",
    response_model=AWSTestResult,
    summary="Test AWS API connection",
    description="Test connectivity to AWS using access keys without saving configuration",
)
def test_aws_connection(config: AWSConfig):
    try:
        logger.info("aws_test_start", region=config.region)

        provider = get_provider(
            ProviderType.AWS,
            credentials={
                "access_key_id": config.access_key_id,
                "secret_access_key": config.secret_access_key,
                "region": config.region,
                "session_token": config.session_token,
            },
        )

        account_data = provider.get_account_info()
        regions = provider.list_regions()

        logger.info(
            "aws_test_success",
            region=config.region,
            account_id=account_data.get("account_id"),
            regions_found=len(regions),
        )

        return AWSTestResult(
            connected=True,
            region=config.region,
            account_id=account_data.get("account_id"),
            account_info=AWSAccountInfo(**account_data),
            regions_found=len(regions),
            details={"regions": regions[:20]},
        )
    except Exception as e:
        logger.error("aws_test_exception", error=str(e), region=config.region)
        return AWSTestResult(
            connected=False,
            region=config.region,
            error_message=str(e),
        )


@router.post(
    "/aws/save",
    response_model=AWSSavedProvider,
    summary="Save AWS credentials securely",
    description="Validate AWS credentials and store them encrypted in the database",
    status_code=status.HTTP_201_CREATED,
)
def save_aws_credentials(
    request: AWSSaveRequest,
    db: Session = Depends(get_db),
):
    provider = get_provider(
        ProviderType.AWS,
        credentials={
            "access_key_id": request.access_key_id,
            "secret_access_key": request.secret_access_key,
            "region": request.region,
            "session_token": request.session_token,
        },
    )

    account_data = provider.get_account_info()
    account_id = account_data.get("account_id", "unknown")
    arn = account_data.get("arn")
    name = request.name or f"AWS {account_id}/{request.region}"

    fernet = _get_fernet()
    credentials_payload = {
        "access_key_id": request.access_key_id,
        "secret_access_key": request.secret_access_key,
        "region": request.region,
        "session_token": request.session_token,
        "account_id": account_id,
        "arn": arn,
        "user_id": account_data.get("user_id"),
    }
    encrypted = fernet.encrypt(json.dumps(credentials_payload).encode()).decode()

    existing = (
        db.query(CloudProvider)
        .filter(CloudProvider.type == ProviderType.AWS)
        .filter(CloudProvider.name == name)
        .first()
    )

    if existing:
        existing.credentials_json = encrypted
        existing.is_active = True
        if request.client_id is not None:
            existing.client_id = request.client_id
        db_provider = existing
    else:
        db_provider = CloudProvider(
            name=name,
            type=ProviderType.AWS,
            credentials_json=encrypted,
            is_active=True,
            client_id=request.client_id,
        )
        db.add(db_provider)

    db.commit()
    db.refresh(db_provider)

    logger.info("aws_credentials_saved", provider_id=db_provider.id, account_id=account_id, region=request.region)

    return AWSSavedProvider(
        id=db_provider.id,
        name=db_provider.name,
        region=request.region,
        account_id=account_id,
        arn=arn,
        is_active=db_provider.is_active,
        created_at=db_provider.created_at.isoformat(),
    )


@router.get(
    "/aws/providers",
    response_model=List[AWSSavedProvider],
    summary="List saved AWS providers",
    description="Return all saved AWS credentials with masked metadata",
)
def list_aws_providers(db: Session = Depends(get_db)):
    providers = (
        db.query(CloudProvider)
        .filter(CloudProvider.type == ProviderType.AWS)
        .filter(CloudProvider.is_active == True)
        .order_by(CloudProvider.created_at.desc())
        .all()
    )

    result = []
    for provider in providers:
        account_id = None
        arn = None
        region = "us-east-1"
        try:
            creds = _decrypt_provider_credentials(provider)
            account_id = creds.get("account_id")
            arn = creds.get("arn")
            region = creds.get("region", region)
        except HTTPException:
            pass

        result.append(
            AWSSavedProvider(
                id=provider.id,
                name=provider.name,
                region=region,
                account_id=account_id,
                arn=arn,
                is_active=provider.is_active,
                created_at=provider.created_at.isoformat(),
            )
        )

    return result


@router.get(
    "/aws/providers/{provider_id}/resources",
    summary="List all resources for a saved AWS provider",
    description="Uses saved credentials to discover AWS compute, storage, network, IP and catalog resources",
)
def get_aws_provider_resources(
    provider_id: int,
    db: Session = Depends(get_db),
):
    db_provider = (
        db.query(CloudProvider)
        .filter(CloudProvider.id == provider_id)
        .filter(CloudProvider.type == ProviderType.AWS)
        .first()
    )
    if not db_provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    creds = _decrypt_provider_credentials(db_provider)
    provider = get_provider(ProviderType.AWS, credentials=creds)

    vms = provider.list_vms()
    volumes = provider.list_storage()
    buckets = provider.list_buckets()
    networks = provider.list_networks()
    elastic_ips = provider.list_elastic_ips()
    regions = provider.list_regions()
    instance_types = provider.list_instance_types(limit=80)
    images = provider.list_images(limit=60)

    logger.info(
        "aws_resources_fetched",
        provider_id=provider_id,
        vms=len(vms),
        volumes=len(volumes),
        buckets=len(buckets),
        networks=len(networks),
        elastic_ips=len(elastic_ips),
    )

    return {
        "provider_id": provider_id,
        "provider_name": db_provider.name,
        "summary": {
            "virtual_machines": len(vms),
            "volumes": len(volumes),
            "buckets": len(buckets),
            "networks": len(networks),
            "elastic_ips": len(elastic_ips),
            "regions": len(regions),
            "instance_types": len(instance_types),
            "images": len(images),
        },
        "resources": {
            "virtual_machines": vms,
            "volumes": volumes,
            "buckets": buckets,
            "networks": networks,
            "elastic_ips": elastic_ips,
        },
        "catalog": {
            "regions": regions,
            "instance_types": instance_types,
            "images": images,
        },
    }

@router.post(
    "/opus/test",
    response_model=CloudStackTestResult,
    summary="Test Opus API connection",
    description="Test connectivity to an Opus API without saving configuration"
)
def test_cloudstack_connection(config: CloudStackConfig):
    """Test connection to CloudStack API and return account/domain info."""
    try:
        logger.info("opus_test_start", api_url=str(config.api_url), verify_ssl=config.verify_ssl)

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
            logger.warning("opus_test_failed_no_response")
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
            logger.error("opus_list_zones_failed", error=str(e))
            zones_count = 0
            zones_data = []

        logger.info(
            "opus_test_success",
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
        logger.error("opus_test_exception", error=str(e))
        return CloudStackTestResult(
            connected=False,
            api_url=str(config.api_url),
            error_message=str(e),
        )


@router.post(
    "/opus/save",
    response_model=CloudStackSavedProvider,
    summary="Save Opus credentials securely",
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
    name = request.name or f"Opus {domain}/{account}"

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
        if request.client_id is not None:
            existing.client_id = request.client_id
        db_provider = existing
    else:
        db_provider = CloudProvider(
            name=name,
            type=ProviderType.CLOUDSTACK,
            credentials_json=encrypted,
            is_active=True,
            client_id=request.client_id,
        )
        db.add(db_provider)

    db.commit()
    db.refresh(db_provider)

    logger.info("opus_credentials_saved", provider_id=db_provider.id, name=name, domain=domain, account=account)

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
    "/opus/providers",
    response_model=List[CloudStackSavedProvider],
    summary="List saved Opus providers",
    description="Return all saved Opus credentials (sensitive data masked)",
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


@router.get(
    "/opus/providers/{provider_id}/resources",
    summary="List all resources for a saved Opus provider",
    description="Uses saved credentials to discover VMs, volumes, networks, public IPs, service offerings and templates",
)
def get_provider_resources(
    provider_id: int,
    db: Session = Depends(get_db),
):
    """Decrypt saved credentials and list all resources from CloudStack."""
    db_provider = (
        db.query(CloudProvider)
        .filter(CloudProvider.id == provider_id)
        .filter(CloudProvider.type == ProviderType.CLOUDSTACK)
        .first()
    )
    if not db_provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    fernet = _get_fernet()
    try:
        creds = json.loads(fernet.decrypt(db_provider.credentials_json.encode()).decode())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to decrypt credentials: {e}")

    provider = get_provider(
        ProviderType.CLOUDSTACK,
        credentials={
            "api_url": creds["api_url"],
            "api_key": creds["api_key"],
            "secret_key": creds["secret_key"],
            "zone_id": creds.get("zone_id"),
        },
    )

    # Collect all resources in parallel-friendly sequential calls
    vms       = provider.list_vms()
    volumes   = provider.list_storage()
    networks  = provider.list_networks()
    public_ips = provider.list_public_ips()
    zones     = provider.list_regions()
    offerings = provider.list_service_offerings()
    templates = provider.list_templates(template_filter="self")

    logger.info(
        "opus_resources_fetched",
        provider_id=provider_id,
        vms=len(vms),
        volumes=len(volumes),
        networks=len(networks),
        public_ips=len(public_ips),
    )

    return {
        "provider_id": provider_id,
        "provider_name": db_provider.name,
        "summary": {
            "virtual_machines": len(vms),
            "volumes": len(volumes),
            "networks": len(networks),
            "public_ips": len(public_ips),
            "zones": len(zones),
            "service_offerings": len(offerings),
            "templates": len(templates),
        },
        "resources": {
            "virtual_machines": vms,
            "volumes": volumes,
            "networks": networks,
            "public_ips": public_ips,
        },
        "catalog": {
            "zones": zones,
            "service_offerings": offerings,
            "templates": templates,
        },
    }
