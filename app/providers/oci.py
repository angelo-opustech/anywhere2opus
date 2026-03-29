from typing import Any, Dict, List, Optional
import structlog

from app.providers.base import BaseProvider

logger = structlog.get_logger(__name__)


class OCIProvider(BaseProvider):
    """OCI cloud provider using the oci library."""

    def __init__(
        self,
        user_ocid: str,
        fingerprint: str,
        tenancy_ocid: str,
        region: str = "us-ashburn-1",
        private_key_file: Optional[str] = None,
        private_key_content: Optional[str] = None,
        compartment_id: Optional[str] = None,
    ):
        self.user_ocid = user_ocid
        self.fingerprint = fingerprint
        self.tenancy_ocid = tenancy_ocid
        self.region = region
        self.private_key_file = private_key_file
        self.private_key_content = private_key_content
        self.compartment_id = compartment_id or tenancy_ocid
        self._config = self._build_config()

    def _build_config(self) -> Dict[str, Any]:
        import oci

        config = {
            "user": self.user_ocid,
            "fingerprint": self.fingerprint,
            "tenancy": self.tenancy_ocid,
            "region": self.region,
        }
        if self.private_key_content:
            config["key_content"] = self.private_key_content
        elif self.private_key_file:
            config["key_file"] = self.private_key_file
        else:
            config["key_file"] = "~/.oci/oci_api_key.pem"

        try:
            oci.config.validate_config(config)
        except Exception as e:
            logger.error("oci_config_error", error=str(e))
            raise RuntimeError(f"OCI config validation failed: {e}") from e
        return config

    def _compute_client(self):
        import oci
        return oci.core.ComputeClient(self._config)

    def _network_client(self):
        import oci
        return oci.core.VirtualNetworkClient(self._config)

    def _block_storage_client(self):
        import oci
        return oci.core.BlockstorageClient(self._config)

    def _identity_client(self):
        import oci
        return oci.identity.IdentityClient(self._config)

    def list_vms(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        client = self._compute_client()
        vms = []
        try:
            response = client.list_instances(compartment_id=self.compartment_id)
            for inst in response.data:
                shape_config = inst.shape_config
                vms.append(
                    {
                        "id": inst.id,
                        "name": inst.display_name,
                        "status": inst.lifecycle_state.lower() if inst.lifecycle_state else "unknown",
                        "region": inst.region,
                        "specs": {
                            "shape": inst.shape,
                            "ocpus": shape_config.ocpus if shape_config else None,
                            "memory_in_gbs": shape_config.memory_in_gbs if shape_config else None,
                            "availability_domain": inst.availability_domain,
                            "fault_domain": inst.fault_domain,
                            "time_created": (
                                inst.time_created.isoformat() if inst.time_created else None
                            ),
                            "freeform_tags": inst.freeform_tags or {},
                        },
                    }
                )
        except Exception as e:
            logger.error("oci_list_vms_error", error=str(e))
            raise RuntimeError(f"OCI list_vms failed: {e}") from e
        return vms

    def list_storage(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        client = self._block_storage_client()
        storages = []
        try:
            response = client.list_volumes(compartment_id=self.compartment_id)
            for vol in response.data:
                storages.append(
                    {
                        "id": vol.id,
                        "name": vol.display_name,
                        "size_gb": vol.size_in_gbs,
                        "region": self.region,
                        "type": "BlockVolume",
                        "specs": {
                            "vpus_per_gb": vol.vpus_per_gb,
                            "lifecycle_state": vol.lifecycle_state,
                            "availability_domain": vol.availability_domain,
                            "time_created": (
                                vol.time_created.isoformat() if vol.time_created else None
                            ),
                            "freeform_tags": vol.freeform_tags or {},
                        },
                    }
                )
        except Exception as e:
            logger.error("oci_list_storage_error", error=str(e))
            raise RuntimeError(f"OCI list_storage failed: {e}") from e
        return storages

    def list_networks(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        client = self._network_client()
        networks = []
        try:
            response = client.list_vcns(compartment_id=self.compartment_id)
            for vcn in response.data:
                cidr = None
                if vcn.cidr_blocks:
                    cidr = vcn.cidr_blocks[0]
                networks.append(
                    {
                        "id": vcn.id,
                        "name": vcn.display_name,
                        "cidr": cidr,
                        "region": self.region,
                        "type": "VCN",
                        "specs": {
                            "cidr_blocks": vcn.cidr_blocks,
                            "dns_label": vcn.dns_label,
                            "lifecycle_state": vcn.lifecycle_state,
                            "freeform_tags": vcn.freeform_tags or {},
                        },
                    }
                )
        except Exception as e:
            logger.error("oci_list_networks_error", error=str(e))
            raise RuntimeError(f"OCI list_networks failed: {e}") from e
        return networks

    def get_vm(self, vm_id: str, region: Optional[str] = None) -> Dict[str, Any]:
        client = self._compute_client()
        try:
            response = client.get_instance(instance_id=vm_id)
            inst = response.data
            shape_config = inst.shape_config
            return {
                "id": inst.id,
                "name": inst.display_name,
                "status": inst.lifecycle_state.lower() if inst.lifecycle_state else "unknown",
                "region": inst.region,
                "specs": {
                    "shape": inst.shape,
                    "ocpus": shape_config.ocpus if shape_config else None,
                    "memory_in_gbs": shape_config.memory_in_gbs if shape_config else None,
                    "availability_domain": inst.availability_domain,
                },
            }
        except Exception as e:
            logger.error("oci_get_vm_error", vm_id=vm_id, error=str(e))
            raise RuntimeError(f"OCI get_vm failed: {e}") from e

    def start_vm(self, vm_id: str, region: Optional[str] = None) -> Dict[str, Any]:
        client = self._compute_client()
        try:
            client.instance_action(instance_id=vm_id, action="START")
            import oci
            oci.wait_until(
                client,
                client.get_instance(instance_id=vm_id),
                "lifecycle_state",
                "RUNNING",
                max_wait_seconds=300,
            )
            return self.get_vm(vm_id, region)
        except Exception as e:
            logger.error("oci_start_vm_error", vm_id=vm_id, error=str(e))
            raise RuntimeError(f"OCI start_vm failed: {e}") from e

    def stop_vm(self, vm_id: str, region: Optional[str] = None) -> Dict[str, Any]:
        client = self._compute_client()
        try:
            client.instance_action(instance_id=vm_id, action="STOP")
            import oci
            oci.wait_until(
                client,
                client.get_instance(instance_id=vm_id),
                "lifecycle_state",
                "STOPPED",
                max_wait_seconds=300,
            )
            return self.get_vm(vm_id, region)
        except Exception as e:
            logger.error("oci_stop_vm_error", vm_id=vm_id, error=str(e))
            raise RuntimeError(f"OCI stop_vm failed: {e}") from e

    def list_regions(self) -> List[Dict[str, Any]]:
        client = self._identity_client()
        regions = []
        try:
            response = client.list_regions()
            for region in response.data:
                regions.append(
                    {
                        "id": region.name,
                        "name": region.name,
                        "key": region.key,
                    }
                )
        except Exception as e:
            logger.error("oci_list_regions_error", error=str(e))
            raise RuntimeError(f"OCI list_regions failed: {e}") from e
        return regions
