from typing import Any, Dict, List, Optional
import json
import structlog

from app.providers.base import BaseProvider

logger = structlog.get_logger(__name__)


class GCPProvider(BaseProvider):
    """GCP cloud provider using google-cloud-compute."""

    def __init__(
        self,
        project_id: str,
        service_account_key_file: Optional[str] = None,
        service_account_key_json: Optional[str] = None,
        default_region: str = "us-central1",
    ):
        self.project_id = project_id
        self.service_account_key_file = service_account_key_file
        self.service_account_key_json = service_account_key_json
        self.default_region = default_region
        self._credentials = self._build_credentials()

    def _build_credentials(self):
        try:
            if self.service_account_key_json:
                from google.oauth2 import service_account
                info = json.loads(self.service_account_key_json)
                return service_account.Credentials.from_service_account_info(
                    info,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
            elif self.service_account_key_file:
                from google.oauth2 import service_account
                return service_account.Credentials.from_service_account_file(
                    self.service_account_key_file,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
            else:
                import google.auth
                credentials, _ = google.auth.default(
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
                return credentials
        except Exception as e:
            logger.error("gcp_credentials_error", error=str(e))
            raise RuntimeError(f"GCP credentials build failed: {e}") from e

    def _instances_client(self):
        from google.cloud import compute_v1
        return compute_v1.InstancesClient(credentials=self._credentials)

    def _zones_client(self):
        from google.cloud import compute_v1
        return compute_v1.ZonesClient(credentials=self._credentials)

    def _regions_client(self):
        from google.cloud import compute_v1
        return compute_v1.RegionsClient(credentials=self._credentials)

    def _storage_client(self):
        from google.cloud import storage
        return storage.Client(project=self.project_id, credentials=self._credentials)

    def _networks_client(self):
        from google.cloud import compute_v1
        return compute_v1.NetworksClient(credentials=self._credentials)

    def list_vms(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        client = self._instances_client()
        vms = []
        try:
            request = {"project": self.project_id}
            agg_list = client.aggregated_list(request=request)
            for zone_name, instances_scoped_list in agg_list:
                for instance in instances_scoped_list.instances or []:
                    zone = zone_name.split("/")[-1] if "/" in zone_name else zone_name
                    instance_region = "-".join(zone.split("-")[:-1])
                    if region and instance_region != region:
                        continue
                    machine_type = instance.machine_type
                    if machine_type:
                        machine_type = machine_type.split("/")[-1]
                    vms.append(
                        {
                            "id": str(instance.id),
                            "name": instance.name,
                            "status": instance.status.lower() if instance.status else "unknown",
                            "region": instance_region,
                            "zone": zone,
                            "specs": {
                                "machine_type": machine_type,
                                "zone": zone,
                                "network_interfaces": [
                                    {
                                        "network": ni.network.split("/")[-1] if ni.network else None,
                                        "ip": ni.network_i_p,
                                    }
                                    for ni in (instance.network_interfaces or [])
                                ],
                                "disks": [
                                    {
                                        "source": d.source.split("/")[-1] if d.source else None,
                                        "boot": d.boot,
                                        "mode": d.mode,
                                    }
                                    for d in (instance.disks or [])
                                ],
                                "labels": dict(instance.labels) if instance.labels else {},
                            },
                        }
                    )
        except Exception as e:
            logger.error("gcp_list_vms_error", error=str(e))
            raise RuntimeError(f"GCP list_vms failed: {e}") from e
        return vms

    def list_storage(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        client = self._storage_client()
        storages = []
        try:
            for bucket in client.list_buckets():
                storages.append(
                    {
                        "id": bucket.name,
                        "name": bucket.name,
                        "size_gb": None,
                        "region": bucket.location.lower() if bucket.location else "unknown",
                        "type": "GCS",
                        "specs": {
                            "storage_class": bucket.storage_class,
                            "location_type": bucket.location_type,
                            "time_created": (
                                bucket.time_created.isoformat() if bucket.time_created else None
                            ),
                            "labels": dict(bucket.labels) if bucket.labels else {},
                        },
                    }
                )
        except Exception as e:
            logger.error("gcp_list_storage_error", error=str(e))
            raise RuntimeError(f"GCP list_storage failed: {e}") from e
        return storages

    def list_networks(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        client = self._networks_client()
        networks = []
        try:
            for network in client.list(project=self.project_id):
                networks.append(
                    {
                        "id": str(network.id),
                        "name": network.name,
                        "cidr": network.i_pv4_range if hasattr(network, "i_pv4_range") else None,
                        "region": "global",
                        "type": "VPC",
                        "specs": {
                            "auto_create_subnetworks": network.auto_create_subnetworks,
                            "subnetworks": [
                                s.split("/")[-1] for s in (network.subnetworks or [])
                            ],
                            "routing_config": (
                                network.routing_config.routing_mode
                                if network.routing_config
                                else None
                            ),
                            "description": network.description,
                        },
                    }
                )
        except Exception as e:
            logger.error("gcp_list_networks_error", error=str(e))
            raise RuntimeError(f"GCP list_networks failed: {e}") from e
        return networks

    def get_vm(self, vm_id: str, region: Optional[str] = None) -> Dict[str, Any]:
        client = self._instances_client()
        try:
            agg_list = client.aggregated_list(request={"project": self.project_id})
            for _, instances_scoped_list in agg_list:
                for instance in instances_scoped_list.instances or []:
                    if str(instance.id) == vm_id or instance.name == vm_id:
                        zone = instance.zone.split("/")[-1] if instance.zone else "unknown"
                        instance_region = "-".join(zone.split("-")[:-1])
                        machine_type = instance.machine_type
                        if machine_type:
                            machine_type = machine_type.split("/")[-1]
                        return {
                            "id": str(instance.id),
                            "name": instance.name,
                            "status": instance.status.lower() if instance.status else "unknown",
                            "region": instance_region,
                            "zone": zone,
                            "specs": {
                                "machine_type": machine_type,
                                "zone": zone,
                            },
                        }
            raise ValueError(f"VM {vm_id} not found in project {self.project_id}")
        except Exception as e:
            logger.error("gcp_get_vm_error", vm_id=vm_id, error=str(e))
            raise RuntimeError(f"GCP get_vm failed: {e}") from e

    def _find_instance_zone(self, vm_id: str) -> tuple:
        """Returns (instance_name, zone) for the given vm_id (name or numeric id)."""
        client = self._instances_client()
        agg_list = client.aggregated_list(request={"project": self.project_id})
        for _, instances_scoped_list in agg_list:
            for instance in instances_scoped_list.instances or []:
                if str(instance.id) == vm_id or instance.name == vm_id:
                    zone = instance.zone.split("/")[-1] if instance.zone else ""
                    return instance.name, zone
        raise ValueError(f"VM {vm_id} not found")

    def start_vm(self, vm_id: str, region: Optional[str] = None) -> Dict[str, Any]:
        client = self._instances_client()
        try:
            name, zone = self._find_instance_zone(vm_id)
            operation = client.start(project=self.project_id, zone=zone, instance=name)
            operation.result(timeout=300)
            return self.get_vm(vm_id, region)
        except Exception as e:
            logger.error("gcp_start_vm_error", vm_id=vm_id, error=str(e))
            raise RuntimeError(f"GCP start_vm failed: {e}") from e

    def stop_vm(self, vm_id: str, region: Optional[str] = None) -> Dict[str, Any]:
        client = self._instances_client()
        try:
            name, zone = self._find_instance_zone(vm_id)
            operation = client.stop(project=self.project_id, zone=zone, instance=name)
            operation.result(timeout=300)
            return self.get_vm(vm_id, region)
        except Exception as e:
            logger.error("gcp_stop_vm_error", vm_id=vm_id, error=str(e))
            raise RuntimeError(f"GCP stop_vm failed: {e}") from e

    def list_regions(self) -> List[Dict[str, Any]]:
        client = self._regions_client()
        regions = []
        try:
            for region in client.list(project=self.project_id):
                regions.append(
                    {
                        "id": region.name,
                        "name": region.name,
                        "status": region.status.lower() if region.status else "unknown",
                        "zones": [z.split("/")[-1] for z in (region.zones or [])],
                    }
                )
        except Exception as e:
            logger.error("gcp_list_regions_error", error=str(e))
            raise RuntimeError(f"GCP list_regions failed: {e}") from e
        return regions
