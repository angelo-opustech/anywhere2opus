from typing import Any, Dict, List, Optional
import structlog

from app.providers.base import BaseProvider

logger = structlog.get_logger(__name__)


class AzureProvider(BaseProvider):
    """Azure cloud provider using azure-mgmt-compute and azure-identity."""

    def __init__(
        self,
        subscription_id: str,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        default_location: str = "eastus",
    ):
        self.subscription_id = subscription_id
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.default_location = default_location
        self._credential = self._build_credential()

    def _build_credential(self):
        from azure.identity import ClientSecretCredential
        try:
            return ClientSecretCredential(
                tenant_id=self.tenant_id,
                client_id=self.client_id,
                client_secret=self.client_secret,
            )
        except Exception as e:
            logger.error("azure_credentials_error", error=str(e))
            raise RuntimeError(f"Azure credential build failed: {e}") from e

    def _compute_client(self):
        from azure.mgmt.compute import ComputeManagementClient
        return ComputeManagementClient(self._credential, self.subscription_id)

    def _network_client(self):
        from azure.mgmt.network import NetworkManagementClient
        return NetworkManagementClient(self._credential, self.subscription_id)

    def _storage_client(self):
        from azure.mgmt.storage import StorageManagementClient
        return StorageManagementClient(self._credential, self.subscription_id)

    def _resource_client(self):
        from azure.mgmt.resource import ResourceManagementClient
        return ResourceManagementClient(self._credential, self.subscription_id)

    def list_vms(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        compute = self._compute_client()
        vms = []
        try:
            all_vms = compute.virtual_machines.list_all()
            for vm in all_vms:
                location = vm.location
                if region and location != region:
                    continue
                power_state = "unknown"
                resource_group = vm.id.split("/")[4] if vm.id else "unknown"
                try:
                    iv = compute.virtual_machines.instance_view(resource_group, vm.name)
                    for s in iv.statuses or []:
                        if s.code and s.code.startswith("PowerState/"):
                            power_state = s.code.replace("PowerState/", "")
                            break
                except Exception:
                    pass
                hw_profile = vm.hardware_profile
                vms.append(
                    {
                        "id": vm.id,
                        "name": vm.name,
                        "status": power_state,
                        "region": location,
                        "resource_group": resource_group,
                        "specs": {
                            "vm_size": hw_profile.vm_size if hw_profile else None,
                            "os_type": (
                                vm.storage_profile.os_disk.os_type.value
                                if vm.storage_profile and vm.storage_profile.os_disk
                                else None
                            ),
                            "location": location,
                            "provisioning_state": vm.provisioning_state,
                            "tags": dict(vm.tags) if vm.tags else {},
                        },
                    }
                )
        except Exception as e:
            logger.error("azure_list_vms_error", error=str(e))
            raise RuntimeError(f"Azure list_vms failed: {e}") from e
        return vms

    def list_storage(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        storage = self._storage_client()
        storages = []
        try:
            for account in storage.storage_accounts.list():
                location = account.location
                if region and location != region:
                    continue
                storages.append(
                    {
                        "id": account.id,
                        "name": account.name,
                        "size_gb": None,
                        "region": location,
                        "type": "StorageAccount",
                        "specs": {
                            "kind": account.kind,
                            "sku": account.sku.name if account.sku else None,
                            "provisioning_state": account.provisioning_state,
                            "primary_location": account.primary_location,
                            "tags": dict(account.tags) if account.tags else {},
                        },
                    }
                )
        except Exception as e:
            logger.error("azure_list_storage_error", error=str(e))
            raise RuntimeError(f"Azure list_storage failed: {e}") from e
        return storages

    def list_networks(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        network = self._network_client()
        networks = []
        try:
            for vnet in network.virtual_networks.list_all():
                location = vnet.location
                if region and location != region:
                    continue
                address_space = None
                if vnet.address_space and vnet.address_space.address_prefixes:
                    address_space = vnet.address_space.address_prefixes[0]
                networks.append(
                    {
                        "id": vnet.id,
                        "name": vnet.name,
                        "cidr": address_space,
                        "region": location,
                        "type": "VNet",
                        "specs": {
                            "address_prefixes": (
                                vnet.address_space.address_prefixes
                                if vnet.address_space
                                else []
                            ),
                            "provisioning_state": vnet.provisioning_state,
                            "subnets": [s.name for s in (vnet.subnets or [])],
                            "tags": dict(vnet.tags) if vnet.tags else {},
                        },
                    }
                )
        except Exception as e:
            logger.error("azure_list_networks_error", error=str(e))
            raise RuntimeError(f"Azure list_networks failed: {e}") from e
        return networks

    def get_vm(self, vm_id: str, region: Optional[str] = None) -> Dict[str, Any]:
        compute = self._compute_client()
        try:
            if vm_id.startswith("/subscriptions/"):
                parts = vm_id.split("/")
                resource_group = parts[4]
                vm_name = parts[-1]
            elif "/" in vm_id:
                resource_group, vm_name = vm_id.split("/", 1)
            else:
                raise ValueError(
                    "vm_id must be a full Azure resource ID or 'resource_group/vm_name'"
                )
            vm = compute.virtual_machines.get(resource_group, vm_name)
            power_state = "unknown"
            try:
                iv = compute.virtual_machines.instance_view(resource_group, vm_name)
                for s in iv.statuses or []:
                    if s.code and s.code.startswith("PowerState/"):
                        power_state = s.code.replace("PowerState/", "")
                        break
            except Exception:
                pass
            hw_profile = vm.hardware_profile
            return {
                "id": vm.id,
                "name": vm.name,
                "status": power_state,
                "region": vm.location,
                "resource_group": resource_group,
                "specs": {
                    "vm_size": hw_profile.vm_size if hw_profile else None,
                    "location": vm.location,
                },
            }
        except Exception as e:
            logger.error("azure_get_vm_error", vm_id=vm_id, error=str(e))
            raise RuntimeError(f"Azure get_vm failed: {e}") from e

    def start_vm(self, vm_id: str, region: Optional[str] = None) -> Dict[str, Any]:
        compute = self._compute_client()
        try:
            if vm_id.startswith("/subscriptions/"):
                parts = vm_id.split("/")
                resource_group = parts[4]
                vm_name = parts[-1]
            elif "/" in vm_id:
                resource_group, vm_name = vm_id.split("/", 1)
            else:
                raise ValueError(
                    "vm_id must be a full Azure resource ID or 'resource_group/vm_name'"
                )
            poller = compute.virtual_machines.begin_start(resource_group, vm_name)
            poller.result()
            return self.get_vm(vm_id, region)
        except Exception as e:
            logger.error("azure_start_vm_error", vm_id=vm_id, error=str(e))
            raise RuntimeError(f"Azure start_vm failed: {e}") from e

    def stop_vm(self, vm_id: str, region: Optional[str] = None) -> Dict[str, Any]:
        compute = self._compute_client()
        try:
            if vm_id.startswith("/subscriptions/"):
                parts = vm_id.split("/")
                resource_group = parts[4]
                vm_name = parts[-1]
            elif "/" in vm_id:
                resource_group, vm_name = vm_id.split("/", 1)
            else:
                raise ValueError(
                    "vm_id must be a full Azure resource ID or 'resource_group/vm_name'"
                )
            poller = compute.virtual_machines.begin_deallocate(resource_group, vm_name)
            poller.result()
            return self.get_vm(vm_id, region)
        except Exception as e:
            logger.error("azure_stop_vm_error", vm_id=vm_id, error=str(e))
            raise RuntimeError(f"Azure stop_vm failed: {e}") from e

    def list_regions(self) -> List[Dict[str, Any]]:
        resource_client = self._resource_client()
        regions = []
        try:
            for location in resource_client.subscriptions.list_locations(self.subscription_id):
                regions.append(
                    {
                        "id": location.name,
                        "name": location.display_name,
                        "region": location.name,
                    }
                )
        except Exception as e:
            logger.error("azure_list_regions_error", error=str(e))
            raise RuntimeError(f"Azure list_regions failed: {e}") from e
        return regions
