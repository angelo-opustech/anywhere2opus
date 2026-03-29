from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_resource_service
from app.models.resource import ResourceType, ResourceStatus
from app.schemas.resource import CloudResourceList, CloudResourceRead
from app.services.resource_service import ResourceService

router = APIRouter(prefix="/resources", tags=["Resources"])


@router.get("", response_model=CloudResourceList, summary="List all discovered resources")
def list_resources(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    resource_type: Optional[ResourceType] = Query(None, description="Filter by resource type"),
    status_filter: Optional[ResourceStatus] = Query(None, alias="status", description="Filter by status"),
    svc: ResourceService = Depends(get_resource_service),
):
    resources, total = svc.list_resources(
        skip=skip,
        limit=limit,
        resource_type=resource_type,
        status=status_filter,
    )
    return CloudResourceList(
        total=total,
        items=[CloudResourceRead.model_validate(r) for r in resources],
    )


@router.get("/provider/{provider_id}", response_model=CloudResourceList,
            summary="List resources for a specific provider")
def list_resources_by_provider(
    provider_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    svc: ResourceService = Depends(get_resource_service),
):
    resources, total = svc.list_resources_by_provider(
        provider_id=provider_id, skip=skip, limit=limit
    )
    return CloudResourceList(
        total=total,
        items=[CloudResourceRead.model_validate(r) for r in resources],
    )


@router.get("/{resource_id}", response_model=CloudResourceRead, summary="Get a resource by ID")
def get_resource(
    resource_id: int,
    svc: ResourceService = Depends(get_resource_service),
):
    try:
        resource = svc.get_resource_or_raise(resource_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return CloudResourceRead.model_validate(resource)
