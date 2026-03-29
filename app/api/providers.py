import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.provider import CloudProvider, ProviderType
from app.schemas.provider import (
    CloudProviderCreate,
    CloudProviderUpdate,
    CloudProviderRead,
    CloudProviderList,
)
from app.providers.factory import get_provider

router = APIRouter()


@router.get("/", response_model=CloudProviderList)
def list_providers(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    provider_type: Optional[ProviderType] = None,
    db: Session = Depends(get_db),
):
    query = db.query(CloudProvider)
    if provider_type:
        query = query.filter(CloudProvider.type == provider_type)
    total = query.count()
    items = query.offset(skip).limit(limit).all()
    return CloudProviderList(total=total, items=[CloudProviderRead.model_validate(i) for i in items])


@router.post("/", response_model=CloudProviderRead, status_code=201)
def create_provider(payload: CloudProviderCreate, db: Session = Depends(get_db)):
    provider = CloudProvider(
        name=payload.name,
        type=payload.type,
        is_active=payload.is_active,
        credentials_json=payload.credentials_to_json(),
    )
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return CloudProviderRead.model_validate(provider)


@router.get("/{provider_id}", response_model=CloudProviderRead)
def get_provider_by_id(provider_id: int, db: Session = Depends(get_db)):
    provider = db.query(CloudProvider).filter(CloudProvider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return CloudProviderRead.model_validate(provider)


@router.patch("/{provider_id}", response_model=CloudProviderRead)
def update_provider(provider_id: int, payload: CloudProviderUpdate, db: Session = Depends(get_db)):
    provider = db.query(CloudProvider).filter(CloudProvider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    if payload.name is not None:
        provider.name = payload.name
    if payload.is_active is not None:
        provider.is_active = payload.is_active
    if payload.credentials is not None:
        provider.credentials_json = payload.credentials_to_json()
    db.commit()
    db.refresh(provider)
    return CloudProviderRead.model_validate(provider)


@router.delete("/{provider_id}", status_code=204)
def delete_provider(provider_id: int, db: Session = Depends(get_db)):
    provider = db.query(CloudProvider).filter(CloudProvider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    db.delete(provider)
    db.commit()


@router.post("/{provider_id}/test-connection")
def test_provider_connection(provider_id: int, db: Session = Depends(get_db)):
    provider = db.query(CloudProvider).filter(CloudProvider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    creds = json.loads(provider.credentials_json) if provider.credentials_json else None
    try:
        cloud = get_provider(provider.type, credentials=creds)
        ok = cloud.test_connection()
        return {"provider_id": provider_id, "connected": ok}
    except Exception as e:
        return {"provider_id": provider_id, "connected": False, "error": str(e)}


@router.get("/{provider_id}/discover")
def discover_resources(provider_id: int, region: Optional[str] = None, db: Session = Depends(get_db)):
    provider = db.query(CloudProvider).filter(CloudProvider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    creds = json.loads(provider.credentials_json) if provider.credentials_json else None
    cloud = get_provider(provider.type, credentials=creds)
    return {
        "provider_id": provider_id,
        "virtual_machines": cloud.list_vms(region=region),
        "networks": cloud.list_networks(region=region),
        "storage": cloud.list_storage(region=region),
    }
