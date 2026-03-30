import json
from typing import List, Optional, Tuple

import structlog
from sqlalchemy.orm import Session

from app.models.provider import CloudProvider
from app.models.resource import CloudResource, ResourceType, ResourceStatus
from app.services.provider_service import ProviderService

logger = structlog.get_logger(__name__)


class ResourceService:
    """Service for discovering and syncing cloud resources into the database."""

    def __init__(self, db: Session):
        self.db = db
        self._provider_service = ProviderService(db)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def list_resources(
        self,
        skip: int = 0,
        limit: int = 100,
        provider_id: Optional[int] = None,
        resource_type: Optional[ResourceType] = None,
        status: Optional[ResourceStatus] = None,
    ) -> Tuple[List[CloudResource], int]:
        query = self.db.query(CloudResource)
        if provider_id is not None:
            query = query.filter(CloudResource.provider_id == provider_id)
        if resource_type is not None:
            query = query.filter(CloudResource.resource_type == resource_type)
        if status is not None:
            query = query.filter(CloudResource.status == status)
        total = query.count()
        resources = query.offset(skip).limit(limit).all()
        return resources, total

    def get_resource(self, resource_id: int) -> Optional[CloudResource]:
        return (
            self.db.query(CloudResource)
            .filter(CloudResource.id == resource_id)
            .first()
        )

    def get_resource_or_raise(self, resource_id: int) -> CloudResource:
        resource = self.get_resource(resource_id)
        if resource is None:
            raise ValueError(f"Resource {resource_id} not found")
        return resource

    def list_resources_by_provider(
        self, provider_id: int, skip: int = 0, limit: int = 100
    ) -> Tuple[List[CloudResource], int]:
        return self.list_resources(skip=skip, limit=limit, provider_id=provider_id)

    # ------------------------------------------------------------------
    # Discovery / sync
    # ------------------------------------------------------------------

    def sync_provider_resources(
        self, provider_id: int, region: Optional[str] = None
    ) -> dict:
        """Discover all resource types from the given provider and upsert
        them into the database.

        Returns a summary dict with counts per resource type.
        """
        provider: CloudProvider = self._provider_service.get_provider_or_raise(provider_id)
        client = self._provider_service.get_provider_client(provider)

        summary: dict = {
            "provider_id": provider_id,
            "created": 0,
            "updated": 0,
            "errors": [],
        }

        # VMs
        try:
            vms = client.list_vms(region=region)
            vm_counts = self._upsert_resources(
                provider_id=provider_id,
                resource_type=ResourceType.VM,
                items=vms,
            )
            summary["vms_created"] = vm_counts["created"]
            summary["vms_updated"] = vm_counts["updated"]
            summary["created"] += vm_counts["created"]
            summary["updated"] += vm_counts["updated"]
        except Exception as e:
            logger.error("sync_vms_error", provider_id=provider_id, error=str(e))
            summary["errors"].append({"type": "VM", "error": str(e)})

        # Storage — classified by disk_class in item specs
        # flash (NVMe, >=20 VPUs)  →  STORAGE_FLASH
        # sas  (balanced/lower, <20 VPUs)  →  STORAGE_SAS
        # no disk_class (object storage, buckets)  →  STORAGE
        try:
            storages = client.list_storage(region=region)
            flash_items = [
                s for s in storages
                if (s.get("specs") or {}).get("disk_class") == "flash"
            ]
            sas_items = [
                s for s in storages
                if (s.get("specs") or {}).get("disk_class") == "sas"
            ]
            obj_items = [
                s for s in storages
                if (s.get("specs") or {}).get("disk_class") not in ("flash", "sas")
            ]
            flash_counts = self._upsert_resources(
                provider_id=provider_id,
                resource_type=ResourceType.STORAGE_FLASH,
                items=flash_items,
            )
            sas_counts = self._upsert_resources(
                provider_id=provider_id,
                resource_type=ResourceType.STORAGE_SAS,
                items=sas_items,
            )
            obj_counts = self._upsert_resources(
                provider_id=provider_id,
                resource_type=ResourceType.STORAGE,
                items=obj_items,
            )
            summary["storage_flash_created"] = flash_counts["created"]
            summary["storage_flash_updated"] = flash_counts["updated"]
            summary["storage_sas_created"] = sas_counts["created"]
            summary["storage_sas_updated"] = sas_counts["updated"]
            summary["storage_obj_created"] = obj_counts["created"]
            summary["storage_obj_updated"] = obj_counts["updated"]
            total_created = flash_counts["created"] + sas_counts["created"] + obj_counts["created"]
            total_updated = flash_counts["updated"] + sas_counts["updated"] + obj_counts["updated"]
            summary["created"] += total_created
            summary["updated"] += total_updated
        except Exception as e:
            logger.error("sync_storage_error", provider_id=provider_id, error=str(e))
            summary["errors"].append({"type": "STORAGE", "error": str(e)})

        # Networks
        try:
            networks = client.list_networks(region=region)
            network_counts = self._upsert_resources(
                provider_id=provider_id,
                resource_type=ResourceType.NETWORK,
                items=networks,
            )
            summary["networks_created"] = network_counts["created"]
            summary["networks_updated"] = network_counts["updated"]
            summary["created"] += network_counts["created"]
            summary["updated"] += network_counts["updated"]
        except Exception as e:
            logger.error("sync_networks_error", provider_id=provider_id, error=str(e))
            summary["errors"].append({"type": "NETWORK", "error": str(e)})

        # Load Balancers
        try:
            lbs = client.list_load_balancers(region=region)
            lb_counts = self._upsert_resources(
                provider_id=provider_id,
                resource_type=ResourceType.LOADBALANCER,
                items=lbs,
            )
            summary["loadbalancers_created"] = lb_counts["created"]
            summary["loadbalancers_updated"] = lb_counts["updated"]
            summary["created"] += lb_counts["created"]
            summary["updated"] += lb_counts["updated"]
        except Exception as e:
            logger.error("sync_loadbalancers_error", provider_id=provider_id, error=str(e))
            summary["errors"].append({"type": "LOADBALANCER", "error": str(e)})

        # Databases
        try:
            dbs = client.list_databases(region=region)
            db_counts = self._upsert_resources(
                provider_id=provider_id,
                resource_type=ResourceType.DATABASE,
                items=dbs,
            )
            summary["databases_created"] = db_counts["created"]
            summary["databases_updated"] = db_counts["updated"]
            summary["created"] += db_counts["created"]
            summary["updated"] += db_counts["updated"]
        except Exception as e:
            logger.error("sync_databases_error", provider_id=provider_id, error=str(e))
            summary["errors"].append({"type": "DATABASE", "error": str(e)})

        # File Storage (NFS)
        try:
            file_stores = client.list_file_storage(region=region)
            fs_counts = self._upsert_resources(
                provider_id=provider_id,
                resource_type=ResourceType.FILESTORE,
                items=file_stores,
            )
            summary["filestorage_created"] = fs_counts["created"]
            summary["filestorage_updated"] = fs_counts["updated"]
            summary["created"] += fs_counts["created"]
            summary["updated"] += fs_counts["updated"]
        except Exception as e:
            logger.error("sync_filestorage_error", provider_id=provider_id, error=str(e))
            summary["errors"].append({"type": "FILESTORE", "error": str(e)})

        # Kubernetes / Container Engine
        try:
            clusters = client.list_kubernetes(region=region)
            k8s_counts = self._upsert_resources(
                provider_id=provider_id,
                resource_type=ResourceType.KUBERNETES,
                items=clusters,
            )
            summary["kubernetes_created"] = k8s_counts["created"]
            summary["kubernetes_updated"] = k8s_counts["updated"]
            summary["created"] += k8s_counts["created"]
            summary["updated"] += k8s_counts["updated"]
        except Exception as e:
            logger.error("sync_kubernetes_error", provider_id=provider_id, error=str(e))
            summary["errors"].append({"type": "KUBERNETES", "error": str(e)})

        logger.info("sync_completed", **summary)
        return summary

    def _upsert_resources(
        self,
        provider_id: int,
        resource_type: ResourceType,
        items: List[dict],
    ) -> dict:
        """Insert or update cloud resources in the database.

        Returns counts of created and updated records.
        """
        created = 0
        updated = 0

        for item in items:
            external_id = str(item.get("id", ""))
            if not external_id:
                continue

            specs = item.get("specs")
            specs_json = json.dumps(specs) if specs is not None else None
            status_raw = (item.get("status") or "active").upper()
            try:
                status = ResourceStatus[status_raw]
            except KeyError:
                status = ResourceStatus.ACTIVE

            existing: Optional[CloudResource] = (
                self.db.query(CloudResource)
                .filter(
                    CloudResource.provider_id == provider_id,
                    CloudResource.external_id == external_id,
                    CloudResource.resource_type == resource_type,
                )
                .first()
            )

            if existing:
                existing.name = item.get("name", existing.name) or existing.name
                existing.region = item.get("region") or existing.region
                existing.specs_json = specs_json if specs_json is not None else existing.specs_json
                existing.status = status
                updated += 1
            else:
                resource = CloudResource(
                    provider_id=provider_id,
                    resource_type=resource_type,
                    name=item.get("name", external_id),
                    region=item.get("region"),
                    external_id=external_id,
                    status=status,
                    specs_json=specs_json,
                )
                self.db.add(resource)
                created += 1

        self.db.commit()
        return {"created": created, "updated": updated}
