import json
from typing import Optional

import structlog
from sqlalchemy.orm import Session

from app.models.provider import CloudProvider
from app.models.resource import CloudResource, ResourceType, ResourceStatus
from app.providers.factory import get_provider

logger = structlog.get_logger(__name__)

_RESOURCE_TYPE_MAP = {
    "virtual_machines": ResourceType.VM,
    "networks": ResourceType.NETWORK,
    "storage": ResourceType.STORAGE,
}


def discover_and_sync(
    db: Session,
    provider_id: int,
    region: Optional[str] = None,
) -> dict[str, int]:
    """Discover resources from a cloud provider and sync them to the database.

    Returns a dict with counts of created/updated resources per type.
    """
    provider = db.query(CloudProvider).filter(CloudProvider.id == provider_id).first()
    if not provider:
        raise ValueError(f"Provider {provider_id} not found")

    creds = json.loads(provider.credentials_json) if provider.credentials_json else None
    cloud = get_provider(provider.type, credentials=creds)

    results = {
        "virtual_machines": cloud.list_vms(region=region),
        "networks": cloud.list_networks(region=region),
        "storage": cloud.list_storage(region=region),
    }

    counts: dict[str, int] = {}

    for category, items in results.items():
        resource_type = _RESOURCE_TYPE_MAP.get(category)
        if not resource_type:
            continue
        count = 0
        for item in items:
            external_id = str(item.get("id", ""))
            existing = (
                db.query(CloudResource)
                .filter(
                    CloudResource.provider_id == provider_id,
                    CloudResource.external_id == external_id,
                )
                .first()
            )
            if existing:
                existing.name = item.get("name", existing.name)
                existing.region = item.get("region")
                existing.specs_json = json.dumps(item.get("specs")) if item.get("specs") else existing.specs_json
            else:
                resource = CloudResource(
                    provider_id=provider_id,
                    resource_type=resource_type,
                    name=item.get("name", external_id),
                    region=item.get("region"),
                    external_id=external_id,
                    status=ResourceStatus.ACTIVE,
                    specs_json=json.dumps(item.get("specs")) if item.get("specs") else None,
                )
                db.add(resource)
                count += 1

        counts[category] = count
        logger.info(
            "discovery_sync",
            provider_id=provider_id,
            category=category,
            new_resources=count,
        )

    db.commit()
    return counts
