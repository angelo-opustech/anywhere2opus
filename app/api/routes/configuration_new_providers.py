"""Configuration endpoints for GCP, Azure, and OCI providers."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import structlog

from app.database import get_db
from app.models.provider import CloudProvider, ProviderType
from app.providers.factory import get_provider
from app.utils.crypto import decrypt_credentials, encrypt_credentials
from app.schemas.configuration import (
    GCPConfig, GCPTestResult, GCPSaveRequest, GCPSavedProvider, GCPProjectInfo,
    AzureConfig, AzureTestResult, AzureSaveRequest, AzureSavedProvider, AzureAccountInfo,
    OCIConfig, OCITestResult, OCISaveRequest, OCISavedProvider, OCITenancyInfo,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/configuration", tags=["Configuration & Testing"])


# ============================================================================
# GCP Configuration & Testing
# ============================================================================

@router.post(
    "/gcp/test",
    response_model=GCPTestResult,
    summary="Test GCP API connection",
    description="Test connectivity to GCP using service account key without saving configuration",
)
def test_gcp_connection(config: GCPConfig):
    try:
        logger.info("gcp_test_start", project_id=config.project_id)

        provider = get_provider(
            ProviderType.GCP,
            credentials={
                "project_id": config.project_id,
                "service_account_key_json": config.service_account_key_json,
                "default_region": config.default_region,
            },
        )

        project_info = provider.get_project_info()
        regions = provider.list_regions()

        logger.info(
            "gcp_test_success",
            project_id=config.project_id,
            regions_found=len(regions),
        )

        return GCPTestResult(
            connected=True,
            project_id=config.project_id,
            project_info=GCPProjectInfo(**project_info),
            regions_found=len(regions),
        )
    except Exception as e:
        logger.error("gcp_test_exception", error=str(e), project_id=config.project_id)
        return GCPTestResult(
            connected=False,
            project_id=config.project_id,
            error_message=str(e),
        )


@router.post(
    "/gcp/save",
    response_model=GCPSavedProvider,
    summary="Save GCP credentials securely",
    description="Validate GCP credentials and store them encrypted in the database",
    status_code=status.HTTP_201_CREATED,
)
def save_gcp_credentials(request: GCPSaveRequest, db: Session = Depends(get_db)):
    provider = get_provider(
        ProviderType.GCP,
        credentials={
            "project_id": request.project_id,
            "service_account_key_json": request.service_account_key_json,
            "default_region": request.default_region,
        },
    )

    project_info = provider.get_project_info()
    project_name = project_info.get("project_name", request.project_id)
    name = request.name or f"GCP {project_name}"

    credentials_payload = {
        "project_id": request.project_id,
        "service_account_key_json": request.service_account_key_json,
        "default_region": request.default_region,
        "project_name": project_name,
    }
    encrypted = encrypt_credentials(credentials_payload)

    existing = (
        db.query(CloudProvider)
        .filter(CloudProvider.type == ProviderType.GCP)
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
            type=ProviderType.GCP,
            credentials_json=encrypted,
            is_active=True,
            client_id=request.client_id,
        )
        db.add(db_provider)

    db.commit()
    db.refresh(db_provider)

    logger.info("gcp_credentials_saved", provider_id=db_provider.id, project_id=request.project_id)

    return GCPSavedProvider(
        id=db_provider.id,
        name=db_provider.name,
        project_id=request.project_id,
        default_region=request.default_region,
        is_active=db_provider.is_active,
        created_at=db_provider.created_at.isoformat(),
    )


@router.get(
    "/gcp/providers",
    response_model=List[GCPSavedProvider],
    summary="List saved GCP providers",
    description="Return all saved GCP credentials with masked metadata",
)
def list_gcp_providers(db: Session = Depends(get_db)):
    providers = (
        db.query(CloudProvider)
        .filter(CloudProvider.type == ProviderType.GCP)
        .filter(CloudProvider.is_active == True)
        .order_by(CloudProvider.created_at.desc())
        .all()
    )

    result = []
    for provider in providers:
        project_id = "unknown"
        region = "us-central1"
        try:
            creds = decrypt_credentials(provider.credentials_json)
            project_id = creds.get("project_id")
            region = creds.get("default_region", region)
        except Exception:
            pass

        result.append(
            GCPSavedProvider(
                id=provider.id,
                name=provider.name,
                project_id=project_id,
                default_region=region,
                is_active=provider.is_active,
                created_at=provider.created_at.isoformat(),
            )
        )

    return result


@router.get(
    "/gcp/providers/{provider_id}/resources",
    summary="List all resources for a saved GCP provider",
    description="Uses saved credentials to discover GCP compute, storage, network and catalog resources",
)
def get_gcp_provider_resources(provider_id: int, db: Session = Depends(get_db)):
    db_provider = (
        db.query(CloudProvider)
        .filter(CloudProvider.id == provider_id)
        .filter(CloudProvider.type == ProviderType.GCP)
        .first()
    )
    if not db_provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    creds = decrypt_credentials(db_provider.credentials_json)
    provider = get_provider(ProviderType.GCP, credentials=creds)

    vms = provider.list_vms()
    buckets = provider.list_storage()
    networks = provider.list_networks()
    regions = provider.list_regions()

    logger.info(
        "gcp_resources_fetched",
        provider_id=provider_id,
        vms=len(vms),
        buckets=len(buckets),
        networks=len(networks),
    )

    return {
        "provider_id": provider_id,
        "provider_name": db_provider.name,
        "summary": {
            "virtual_machines": len(vms),
            "buckets": len(buckets),
            "networks": len(networks),
            "regions": len(regions),
        },
        "resources": {
            "virtual_machines": vms,
            "buckets": buckets,
            "networks": networks,
        },
        "catalog": {
            "regions": regions,
        },
    }


# ============================================================================
# Azure Configuration & Testing
# ============================================================================

@router.post(
    "/azure/test",
    response_model=AzureTestResult,
    summary="Test Azure API connection",
    description="Test connectivity to Azure using service principal without saving configuration",
)
def test_azure_connection(config: AzureConfig):
    try:
        logger.info("azure_test_start", subscription_id=config.subscription_id)

        provider = get_provider(
            ProviderType.AZURE,
            credentials={
                "subscription_id": config.subscription_id,
                "tenant_id": config.tenant_id,
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "default_location": config.default_location,
            },
        )

        account_info = provider.get_account_info()
        regions = provider.list_regions()

        logger.info(
            "azure_test_success",
            subscription_id=config.subscription_id,
            regions_found=len(regions),
        )

        return AzureTestResult(
            connected=True,
            subscription_id=config.subscription_id,
            account_info=AzureAccountInfo(**account_info),
            regions_found=len(regions),
        )
    except Exception as e:
        logger.error("azure_test_exception", error=str(e), subscription_id=config.subscription_id)
        return AzureTestResult(
            connected=False,
            subscription_id=config.subscription_id,
            error_message=str(e),
        )


@router.post(
    "/azure/save",
    response_model=AzureSavedProvider,
    summary="Save Azure credentials securely",
    description="Validate Azure credentials and store them encrypted in the database",
    status_code=status.HTTP_201_CREATED,
)
def save_azure_credentials(request: AzureSaveRequest, db: Session = Depends(get_db)):
    provider = get_provider(
        ProviderType.AZURE,
        credentials={
            "subscription_id": request.subscription_id,
            "tenant_id": request.tenant_id,
            "client_id": request.client_id,
            "client_secret": request.client_secret,
            "default_location": request.default_location,
        },
    )

    account_info = provider.get_account_info()
    sub_name = account_info.get("subscription_name", request.subscription_id)
    name = request.name or f"Azure {sub_name}"

    credentials_payload = {
        "subscription_id": request.subscription_id,
        "tenant_id": request.tenant_id,
        "client_id": request.client_id,
        "client_secret": request.client_secret,
        "default_location": request.default_location,
    }
    encrypted = encrypt_credentials(credentials_payload)

    existing = (
        db.query(CloudProvider)
        .filter(CloudProvider.type == ProviderType.AZURE)
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
            type=ProviderType.AZURE,
            credentials_json=encrypted,
            is_active=True,
            client_id=request.client_id,
        )
        db.add(db_provider)

    db.commit()
    db.refresh(db_provider)

    logger.info("azure_credentials_saved", provider_id=db_provider.id, subscription_id=request.subscription_id)

    return AzureSavedProvider(
        id=db_provider.id,
        name=db_provider.name,
        subscription_id=request.subscription_id,
        tenant_id=request.tenant_id,
        default_location=request.default_location,
        is_active=db_provider.is_active,
        created_at=db_provider.created_at.isoformat(),
    )


@router.get(
    "/azure/providers",
    response_model=List[AzureSavedProvider],
    summary="List saved Azure providers",
    description="Return all saved Azure credentials with masked metadata",
)
def list_azure_providers(db: Session = Depends(get_db)):
    providers = (
        db.query(CloudProvider)
        .filter(CloudProvider.type == ProviderType.AZURE)
        .filter(CloudProvider.is_active == True)
        .order_by(CloudProvider.created_at.desc())
        .all()
    )

    result = []
    for provider in providers:
        subscription_id = "unknown"
        tenant_id = "unknown"
        location = "eastus"
        try:
            creds = decrypt_credentials(provider.credentials_json)
            subscription_id = creds.get("subscription_id")
            tenant_id = creds.get("tenant_id")
            location = creds.get("default_location", location)
        except Exception:
            pass

        result.append(
            AzureSavedProvider(
                id=provider.id,
                name=provider.name,
                subscription_id=subscription_id,
                tenant_id=tenant_id,
                default_location=location,
                is_active=provider.is_active,
                created_at=provider.created_at.isoformat(),
            )
        )

    return result


@router.get(
    "/azure/providers/{provider_id}/resources",
    summary="List all resources for a saved Azure provider",
    description="Uses saved credentials to discover Azure compute, storage, network and catalog resources",
)
def get_azure_provider_resources(provider_id: int, db: Session = Depends(get_db)):
    db_provider = (
        db.query(CloudProvider)
        .filter(CloudProvider.id == provider_id)
        .filter(CloudProvider.type == ProviderType.AZURE)
        .first()
    )
    if not db_provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    creds = decrypt_credentials(db_provider.credentials_json)
    provider = get_provider(ProviderType.AZURE, credentials=creds)

    vms = provider.list_vms()
    storages = provider.list_storage()
    networks = provider.list_networks()
    regions = provider.list_regions()

    logger.info(
        "azure_resources_fetched",
        provider_id=provider_id,
        vms=len(vms),
        storages=len(storages),
        networks=len(networks),
    )

    return {
        "provider_id": provider_id,
        "provider_name": db_provider.name,
        "summary": {
            "virtual_machines": len(vms),
            "storage_accounts": len(storages),
            "networks": len(networks),
            "regions": len(regions),
        },
        "resources": {
            "virtual_machines": vms,
            "storage_accounts": storages,
            "networks": networks,
        },
        "catalog": {
            "regions": regions,
        },
    }


# ============================================================================
# OCI Configuration & Testing
# ============================================================================

@router.post(
    "/oci/test",
    response_model=OCITestResult,
    summary="Test OCI API connection",
    description="Test connectivity to OCI using API credentials without saving configuration",
)
def test_oci_connection(config: OCIConfig):
    try:
        logger.info("oci_test_start", tenancy_ocid=config.tenancy_ocid)

        provider = get_provider(
            ProviderType.OCI,
            credentials={
                "user_ocid": config.user_ocid,
                "fingerprint": config.fingerprint,
                "tenancy_ocid": config.tenancy_ocid,
                "region": config.region,
                "private_key_content": config.private_key_content,
            },
        )

        tenancy_info = provider.get_tenancy_info()
        regions = provider.list_regions()

        logger.info(
            "oci_test_success",
            tenancy_ocid=config.tenancy_ocid,
            regions_found=len(regions),
        )

        return OCITestResult(
            connected=True,
            tenancy_ocid=config.tenancy_ocid,
            account_info=OCITenancyInfo(**tenancy_info),
            regions_found=len(regions),
        )
    except Exception as e:
        logger.error("oci_test_exception", error=str(e), tenancy_ocid=config.tenancy_ocid)
        return OCITestResult(
            connected=False,
            tenancy_ocid=config.tenancy_ocid,
            error_message=str(e),
        )


@router.post(
    "/oci/save",
    response_model=OCISavedProvider,
    summary="Save OCI credentials securely",
    description="Validate OCI credentials and store them encrypted in the database",
    status_code=status.HTTP_201_CREATED,
)
def save_oci_credentials(request: OCISaveRequest, db: Session = Depends(get_db)):
    provider = get_provider(
        ProviderType.OCI,
        credentials={
            "user_ocid": request.user_ocid,
            "fingerprint": request.fingerprint,
            "tenancy_ocid": request.tenancy_ocid,
            "region": request.region,
            "private_key_content": request.private_key_content,
        },
    )

    tenancy_info = provider.get_tenancy_info()
    tenancy_name = tenancy_info.get("tenancy_name", request.tenancy_ocid)
    name = request.name or f"OCI {tenancy_name}/{request.region}"

    credentials_payload = {
        "user_ocid": request.user_ocid,
        "fingerprint": request.fingerprint,
        "tenancy_ocid": request.tenancy_ocid,
        "region": request.region,
        "private_key_content": request.private_key_content,
    }
    encrypted = encrypt_credentials(credentials_payload)

    existing = (
        db.query(CloudProvider)
        .filter(CloudProvider.type == ProviderType.OCI)
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
            type=ProviderType.OCI,
            credentials_json=encrypted,
            is_active=True,
            client_id=request.client_id,
        )
        db.add(db_provider)

    db.commit()
    db.refresh(db_provider)

    logger.info("oci_credentials_saved", provider_id=db_provider.id, tenancy_ocid=request.tenancy_ocid)

    return OCISavedProvider(
        id=db_provider.id,
        name=db_provider.name,
        tenancy_ocid=request.tenancy_ocid,
        region=request.region,
        is_active=db_provider.is_active,
        created_at=db_provider.created_at.isoformat(),
    )


@router.get(
    "/oci/providers",
    response_model=List[OCISavedProvider],
    summary="List saved OCI providers",
    description="Return all saved OCI credentials with masked metadata",
)
def list_oci_providers(db: Session = Depends(get_db)):
    providers = (
        db.query(CloudProvider)
        .filter(CloudProvider.type == ProviderType.OCI)
        .filter(CloudProvider.is_active == True)
        .order_by(CloudProvider.created_at.desc())
        .all()
    )

    result = []
    for provider in providers:
        tenancy_id = "unknown"
        region = "us-ashburn-1"
        try:
            creds = decrypt_credentials(provider.credentials_json)
            tenancy_id = creds.get("tenancy_ocid")
            region = creds.get("region", region)
        except Exception:
            pass

        result.append(
            OCISavedProvider(
                id=provider.id,
                name=provider.name,
                tenancy_ocid=tenancy_id,
                region=region,
                is_active=provider.is_active,
                created_at=provider.created_at.isoformat(),
            )
        )

    return result


@router.get(
    "/oci/providers/{provider_id}/resources",
    summary="List all resources for a saved OCI provider",
    description="Uses saved credentials to discover OCI compute, storage, network and catalog resources",
)
def get_oci_provider_resources(provider_id: int, db: Session = Depends(get_db)):
    db_provider = (
        db.query(CloudProvider)
        .filter(CloudProvider.id == provider_id)
        .filter(CloudProvider.type == ProviderType.OCI)
        .first()
    )
    if not db_provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    creds = decrypt_credentials(db_provider.credentials_json)
    provider = get_provider(ProviderType.OCI, credentials=creds)

    vms = provider.list_vms()
    # Split storage by disk_class
    all_storage = provider.list_storage()
    flash_volumes = [s for s in all_storage if (s.get("specs") or {}).get("disk_class") == "flash"]
    sas_volumes   = [s for s in all_storage if (s.get("specs") or {}).get("disk_class") == "sas"]
    buckets       = [s for s in all_storage if (s.get("specs") or {}).get("disk_class") not in ("flash", "sas")]
    networks      = provider.list_networks()
    regions       = provider.list_regions()

    # Optional resources — return empty list on error so UI doesn't break
    try:
        load_balancers = provider.list_load_balancers()
    except Exception:
        load_balancers = []
    try:
        databases = provider.list_databases()
    except Exception:
        databases = []
    try:
        file_storage = provider.list_file_storage()
    except Exception:
        file_storage = []
    try:
        kubernetes = provider.list_kubernetes()
    except Exception:
        kubernetes = []

    logger.info(
        "oci_resources_fetched",
        provider_id=provider_id,
        vms=len(vms),
        flash_volumes=len(flash_volumes),
        sas_volumes=len(sas_volumes),
        buckets=len(buckets),
        networks=len(networks),
        load_balancers=len(load_balancers),
        databases=len(databases),
        file_storage=len(file_storage),
        kubernetes=len(kubernetes),
    )

    return {
        "provider_id": provider_id,
        "provider_name": db_provider.name,
        "summary": {
            "virtual_machines": len(vms),
            "flash_volumes": len(flash_volumes),
            "sas_volumes": len(sas_volumes),
            "buckets": len(buckets),
            "networks": len(networks),
            "load_balancers": len(load_balancers),
            "databases": len(databases),
            "file_storage": len(file_storage),
            "kubernetes": len(kubernetes),
            "regions": len(regions),
        },
        "resources": {
            "virtual_machines": vms,
            "flash_volumes": flash_volumes,
            "sas_volumes": sas_volumes,
            "buckets": buckets,
            "networks": networks,
            "load_balancers": load_balancers,
            "databases": databases,
            "file_storage": file_storage,
            "kubernetes": kubernetes,
        },
        "catalog": {
            "regions": regions,
        },
    }
