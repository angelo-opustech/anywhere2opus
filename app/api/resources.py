from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.resource import CloudResource, ResourceType, ResourceStatus
from app.schemas.resource import (
    CloudResourceCreate,
    CloudResourceUpdate,
    CloudResourceRead,
    CloudResourceList,
)

router = APIRouter()


@router.get("/", response_model=CloudResourceList)
def list_resources(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    provider_id: Optional[int] = None,
    resource_type: Optional[ResourceType] = None,
    status: Optional[ResourceStatus] = None,
    db: Session = Depends(get_db),
):
    query = db.query(CloudResource)
    if provider_id:
        query = query.filter(CloudResource.provider_id == provider_id)
    if resource_type:
        query = query.filter(CloudResource.resource_type == resource_type)
    if status:
        query = query.filter(CloudResource.status == status)
    total = query.count()
    items = query.offset(skip).limit(limit).all()
    return CloudResourceList(total=total, items=[CloudResourceRead.model_validate(i) for i in items])


@router.post("/", response_model=CloudResourceRead, status_code=201)
def create_resource(payload: CloudResourceCreate, db: Session = Depends(get_db)):
    resource = CloudResource(
        provider_id=payload.provider_id,
        resource_type=payload.resource_type,
        name=payload.name,
        region=payload.region,
        external_id=payload.external_id,
        status=payload.status,
        specs_json=payload.specs_to_json(),
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return CloudResourceRead.model_validate(resource)


@router.get("/{resource_id}", response_model=CloudResourceRead)
def get_resource(resource_id: int, db: Session = Depends(get_db)):
    resource = db.query(CloudResource).filter(CloudResource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    return CloudResourceRead.model_validate(resource)


@router.patch("/{resource_id}", response_model=CloudResourceRead)
def update_resource(resource_id: int, payload: CloudResourceUpdate, db: Session = Depends(get_db)):
    resource = db.query(CloudResource).filter(CloudResource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    if payload.name is not None:
        resource.name = payload.name
    if payload.region is not None:
        resource.region = payload.region
    if payload.external_id is not None:
        resource.external_id = payload.external_id
    if payload.status is not None:
        resource.status = payload.status
    if payload.specs is not None:
        resource.specs_json = payload.specs_to_json()
    db.commit()
    db.refresh(resource)
    return CloudResourceRead.model_validate(resource)


@router.delete("/{resource_id}", status_code=204)
def delete_resource(resource_id: int, db: Session = Depends(get_db)):
    resource = db.query(CloudResource).filter(CloudResource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    db.delete(resource)
    db.commit()
