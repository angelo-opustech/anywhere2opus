from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_provider_service, get_resource_service
from app.models.provider import ProviderType
from app.schemas.provider import (
    CloudProviderCreate,
    CloudProviderList,
    CloudProviderRead,
    CloudProviderUpdate,
)
from app.services.provider_service import ProviderService
from app.services.resource_service import ResourceService

router = APIRouter(prefix="/providers", tags=["Providers"])


@router.get("", response_model=CloudProviderList, summary="List all cloud providers")
def list_providers(
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=200, description="Max results per page"),
    active_only: bool = Query(False, description="Return only active providers"),
    client_id: Optional[int] = Query(None, description="Filter by client ID"),
    svc: ProviderService = Depends(get_provider_service),
):
    providers, total = svc.list_providers(skip=skip, limit=limit, active_only=active_only, client_id=client_id)
    return CloudProviderList(
        total=total,
        items=[CloudProviderRead.model_validate(p) for p in providers],
    )


@router.post("", response_model=CloudProviderRead, status_code=status.HTTP_201_CREATED,
             summary="Create a cloud provider")
def create_provider(
    payload: CloudProviderCreate,
    svc: ProviderService = Depends(get_provider_service),
):
    provider = svc.create_provider(payload)
    return CloudProviderRead.model_validate(provider)


@router.get("/{provider_id}", response_model=CloudProviderRead, summary="Get a provider by ID")
def get_provider(
    provider_id: int,
    svc: ProviderService = Depends(get_provider_service),
):
    try:
        provider = svc.get_provider_or_raise(provider_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return CloudProviderRead.model_validate(provider)


@router.put("/{provider_id}", response_model=CloudProviderRead, summary="Update a provider")
def update_provider(
    provider_id: int,
    payload: CloudProviderUpdate,
    svc: ProviderService = Depends(get_provider_service),
):
    try:
        provider = svc.update_provider(provider_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return CloudProviderRead.model_validate(provider)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Delete a provider")
def delete_provider(
    provider_id: int,
    svc: ProviderService = Depends(get_provider_service),
):
    try:
        svc.delete_provider(provider_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{provider_id}/sync", summary="Discover and sync resources from a provider")
def sync_provider(
    provider_id: int,
    region: Optional[str] = Query(None, description="Limit discovery to a specific region"),
    resource_svc: ResourceService = Depends(get_resource_service),
    provider_svc: ProviderService = Depends(get_provider_service),
):
    try:
        provider_svc.get_provider_or_raise(provider_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    try:
        summary = resource_svc.sync_provider_resources(provider_id, region=region)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Sync failed: {e}",
        )
    return summary


@router.post("/{provider_id}/test", summary="Test connectivity to a provider")
def test_provider(
    provider_id: int,
    svc: ProviderService = Depends(get_provider_service),
):
    try:
        provider = svc.get_provider_or_raise(provider_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    connected = svc.test_connection(provider_id)
    return {
        "provider_id": provider_id,
        "provider_name": provider.name,
        "provider_type": provider.type,
        "connected": connected,
    }
