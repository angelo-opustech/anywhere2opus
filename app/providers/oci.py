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

    def _normalize_key(self, key_content: str) -> str:
        """Normalize key content received from UI or stored credentials."""
        if not key_content:
            return key_content

        normalized = key_content.replace('\\n', '\n')
        normalized = normalized.strip()
        return normalized

    def _build_config(self) -> Dict[str, Any]:
        import oci

        config = {
            "user": self.user_ocid,
            "fingerprint": self.fingerprint,
            "tenancy": self.tenancy_ocid,
            "region": self.region,
        }
        if self.private_key_content:
            config["key_content"] = self._normalize_key(self.private_key_content)
        elif self.private_key_file:
            config["key_file"] = self.private_key_file
        else:
            config["key_file"] = "~/.oci/oci_api_key.pem"

        try:
            oci.config.validate_config(config)
        except Exception as e:
            logger.error("oci_config_error", error=str(e), config_keys=list(config.keys()))
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

    def get_tenancy_info(self) -> Dict[str, Any]:
        client = self._identity_client()
        try:
            tenancy = client.get_tenancy(tenancy_id=self.tenancy_ocid)
            return {
                "tenancy_ocid": self.tenancy_ocid,
                "tenancy_name": tenancy.data.name,
                "user_ocid": self.user_ocid,
                "region": self.region,
                "home_region": tenancy.data.home_region_key,
            }
        except Exception as e:
            logger.error("oci_get_tenancy_info_error", error=str(e))
            raise RuntimeError(f"OCI get_tenancy_info failed: {e}") from e

    def test_connection(self) -> bool:
        try:
            self.get_tenancy_info()
            self.list_regions()
            return True
        except Exception:
            return False

    def list_vms(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        import oci

        compute = self._compute_client()
        network_client = self._network_client()
        block_storage = self._block_storage_client()
        vms = []
        try:
            instances = oci.pagination.list_call_get_all_results(
                compute.list_instances,
                compartment_id=self.compartment_id,
            ).data

            # Bulk fetch: VNIC attachments grouped by instance_id
            vnic_attachments = oci.pagination.list_call_get_all_results(
                compute.list_vnic_attachments,
                compartment_id=self.compartment_id,
            ).data
            vnic_map: Dict[str, List] = {}
            for va in vnic_attachments:
                if va.lifecycle_state == "ATTACHED":
                    vnic_map.setdefault(va.instance_id, []).append(va)

            # Bulk fetch: block volume attachments grouped by instance_id
            vol_attachments = oci.pagination.list_call_get_all_results(
                compute.list_volume_attachments,
                compartment_id=self.compartment_id,
            ).data
            vol_attachment_map: Dict[str, List] = {}
            for va in vol_attachments:
                if va.lifecycle_state == "ATTACHED":
                    vol_attachment_map.setdefault(va.instance_id, []).append(va)

            # Bulk fetch: all block volumes indexed by volume_id
            all_volumes = oci.pagination.list_call_get_all_results(
                block_storage.list_volumes,
                compartment_id=self.compartment_id,
            ).data
            volumes_by_id: Dict[str, Any] = {v.id: v for v in all_volumes}

            for inst in instances:
                sc = inst.shape_config

                # ── Network: VNICs ──────────────────────────────────────────
                vnics = []
                for va in vnic_map.get(inst.id, []):
                    try:
                        vnic = network_client.get_vnic(vnic_id=va.vnic_id).data
                        vnics.append(
                            {
                                "vnic_id": vnic.id,
                                "display_name": vnic.display_name,
                                "private_ip": vnic.private_ip,
                                "public_ip": vnic.public_ip,
                                "subnet_id": vnic.subnet_id,
                                "hostname_label": vnic.hostname_label,
                                "is_primary": vnic.is_primary,
                                "mac_address": vnic.mac_address,
                                "nsg_ids": vnic.nsg_ids or [],
                                "skip_source_dest_check": vnic.skip_source_dest_check,
                            }
                        )
                    except Exception as vnic_err:
                        logger.warning(
                            "oci_get_vnic_error",
                            vnic_id=va.vnic_id,
                            error=str(vnic_err),
                        )

                # ── Disks: local NVMe (flash) ────────────────────────────────
                # Available on DenseIO and HPC shapes; shape_config exposes count
                # and total size directly.
                flash_disks: List[Dict] = []
                if sc and sc.local_disks:
                    flash_disks.append(
                        {
                            "source": "local_nvme",
                            "count": sc.local_disks,
                            "total_size_gb": sc.local_disk_total_size_in_gbs,
                            "description": getattr(sc, "local_disks_description", None),
                            "disk_class": "flash",
                        }
                    )

                # ── Disks: attached block volumes (flash >= 20 VPUs, else SAS) ─
                # OCI vpus_per_gb: 0=LowerCost(SAS), 10=Balanced(SAS),
                #                  20=HigherPerf(flash), 120=UltraHighPerf(flash)
                sas_disks: List[Dict] = []
                for vol_att in vol_attachment_map.get(inst.id, []):
                    vol = volumes_by_id.get(vol_att.volume_id)
                    if vol is None:
                        continue
                    vpus = vol.vpus_per_gb or 0
                    disk_class = "flash" if vpus >= 20 else "sas"
                    record = {
                        "source": "block_volume",
                        "volume_id": vol.id,
                        "name": vol.display_name,
                        "size_gb": vol.size_in_gbs,
                        "vpus_per_gb": vpus,
                        "disk_class": disk_class,
                        "is_boot": False,
                    }
                    if disk_class == "flash":
                        flash_disks.append(record)
                    else:
                        sas_disks.append(record)

                vms.append(
                    {
                        "id": inst.id,
                        "name": inst.display_name,
                        "status": (
                            inst.lifecycle_state.lower()
                            if inst.lifecycle_state
                            else "unknown"
                        ),
                        "region": inst.region,
                        "specs": {
                            "shape": inst.shape,
                            # 1 OCPU = 2 vCPUs (HT) on x86 Intel/AMD shapes;
                            # on Ampere A1 shapes ocpus == vcpus directly.
                            "ocpus": sc.ocpus if sc else None,
                            "memory_gb": sc.memory_in_gbs if sc else None,
                            "processor": sc.processor_description if sc else None,
                            "networking_gbps": (
                                sc.networking_bandwidth_in_gbps if sc else None
                            ),
                            "flash_disks": flash_disks,
                            "sas_disks": sas_disks,
                            "network": {"vnics": vnics},
                            "availability_domain": inst.availability_domain,
                            "fault_domain": inst.fault_domain,
                            "time_created": (
                                inst.time_created.isoformat()
                                if inst.time_created
                                else None
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
        import oci

        block_storage = self._block_storage_client()
        identity = self._identity_client()
        storages: List[Dict[str, Any]] = []
        try:
            # ── Block Volumes ────────────────────────────────────────────────
            # vpus_per_gb: 0=LowerCost(SAS), 10=Balanced(SAS),
            #              20=HigherPerf(flash), 120=UltraHighPerf(flash)
            volumes = oci.pagination.list_call_get_all_results(
                block_storage.list_volumes,
                compartment_id=self.compartment_id,
            ).data
            for vol in volumes:
                vpus = vol.vpus_per_gb or 0
                storages.append(
                    {
                        "id": vol.id,
                        "name": vol.display_name,
                        "size_gb": vol.size_in_gbs,
                        "region": self.region,
                        "type": "BlockVolume",
                        "specs": {
                            "vpus_per_gb": vpus,
                            "disk_class": "flash" if vpus >= 20 else "sas",
                            "lifecycle_state": vol.lifecycle_state,
                            "availability_domain": vol.availability_domain,
                            "time_created": (
                                vol.time_created.isoformat() if vol.time_created else None
                            ),
                            "freeform_tags": vol.freeform_tags or {},
                        },
                    }
                )

            # ── Boot Volumes (one call per Availability Domain) ──────────────
            ads = oci.pagination.list_call_get_all_results(
                identity.list_availability_domains,
                compartment_id=self.compartment_id,
            ).data
            for ad in ads:
                boot_vols = oci.pagination.list_call_get_all_results(
                    block_storage.list_boot_volumes,
                    availability_domain=ad.name,
                    compartment_id=self.compartment_id,
                ).data
                for bvol in boot_vols:
                    vpus = bvol.vpus_per_gb or 10  # default boot = Balanced (10)
                    storages.append(
                        {
                            "id": bvol.id,
                            "name": bvol.display_name,
                            "size_gb": bvol.size_in_gbs,
                            "region": self.region,
                            "type": "BootVolume",
                            "specs": {
                                "vpus_per_gb": vpus,
                                "disk_class": "flash" if vpus >= 20 else "sas",
                                "lifecycle_state": bvol.lifecycle_state,
                                "availability_domain": bvol.availability_domain,
                                "time_created": (
                                    bvol.time_created.isoformat()
                                    if bvol.time_created
                                    else None
                                ),
                                "freeform_tags": bvol.freeform_tags or {},
                            },
                        }
                    )

            # ── Object Storage Buckets ───────────────────────────────────────
            try:
                storages.extend(self.list_buckets())
            except Exception as bucket_err:
                logger.warning("oci_list_buckets_in_storage_warning", error=str(bucket_err))

        except Exception as e:
            logger.error("oci_list_storage_error", error=str(e))
            raise RuntimeError(f"OCI list_storage failed: {e}") from e
        return storages

    def list_networks(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        import oci

        client = self._network_client()
        networks: List[Dict[str, Any]] = []
        try:
            vcns = oci.pagination.list_call_get_all_results(
                client.list_vcns,
                compartment_id=self.compartment_id,
            ).data

            for vcn in vcns:
                # Subnets
                subnets = oci.pagination.list_call_get_all_results(
                    client.list_subnets,
                    compartment_id=self.compartment_id,
                    vcn_id=vcn.id,
                ).data
                subnet_list = [
                    {
                        "id": s.id,
                        "name": s.display_name,
                        "cidr": s.cidr_block,
                        "availability_domain": s.availability_domain,
                        "dns_label": s.dns_label,
                        "is_public": not getattr(s, "prohibit_internet_ingress", True),
                        "security_list_ids": s.security_list_ids or [],
                        "route_table_id": s.route_table_id,
                        "lifecycle_state": s.lifecycle_state,
                    }
                    for s in subnets
                ]

                # Internet Gateways
                igws = oci.pagination.list_call_get_all_results(
                    client.list_internet_gateways,
                    compartment_id=self.compartment_id,
                    vcn_id=vcn.id,
                ).data

                # NAT Gateways
                nats = oci.pagination.list_call_get_all_results(
                    client.list_nat_gateways,
                    compartment_id=self.compartment_id,
                    vcn_id=vcn.id,
                ).data

                # Service Gateways (OCI Services, e.g. Object Storage)
                sgws = oci.pagination.list_call_get_all_results(
                    client.list_service_gateways,
                    compartment_id=self.compartment_id,
                    vcn_id=vcn.id,
                ).data

                cidr = vcn.cidr_blocks[0] if vcn.cidr_blocks else None
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
                            "subnets": subnet_list,
                            "internet_gateways": [
                                {
                                    "id": gw.id,
                                    "name": gw.display_name,
                                    "is_enabled": gw.is_enabled,
                                }
                                for gw in igws
                            ],
                            "nat_gateways": [
                                {
                                    "id": nat.id,
                                    "name": nat.display_name,
                                    "nat_ip": nat.nat_ip,
                                    "block_traffic": nat.block_traffic,
                                }
                                for nat in nats
                            ],
                            "service_gateways": [
                                {
                                    "id": sgw.id,
                                    "name": sgw.display_name,
                                    "block_traffic": sgw.block_traffic,
                                }
                                for sgw in sgws
                            ],
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

    def list_load_balancers(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        import oci
        from oci.load_balancer import LoadBalancerClient

        client = LoadBalancerClient(self._config)
        lbs: List[Dict[str, Any]] = []
        try:
            load_balancers = oci.pagination.list_call_get_all_results(
                client.list_load_balancers,
                compartment_id=self.compartment_id,
            ).data
            for lb in load_balancers:
                listeners = {
                    name: {
                        "port": lst.port,
                        "protocol": lst.protocol,
                        "default_backend_set": lst.default_backend_set_name,
                        "ssl_enabled": lst.ssl_configuration is not None,
                    }
                    for name, lst in (lb.listeners or {}).items()
                }
                backend_sets = {
                    name: {
                        "policy": bs.policy,
                        "health_checker": (
                            {
                                "protocol": bs.health_checker.protocol,
                                "port": bs.health_checker.port,
                                "url_path": bs.health_checker.url_path,
                            }
                            if bs.health_checker
                            else None
                        ),
                        "backends": [
                            {
                                "ip": b.ip_address,
                                "port": b.port,
                                "weight": b.weight,
                                "is_backup": b.is_backup,
                                "is_drain": b.is_drain,
                                "is_offline": b.is_offline,
                            }
                            for b in (bs.backends or [])
                        ],
                    }
                    for name, bs in (lb.backend_sets or {}).items()
                }
                lbs.append(
                    {
                        "id": lb.id,
                        "name": lb.display_name,
                        "status": (
                            lb.lifecycle_state.lower()
                            if lb.lifecycle_state
                            else "unknown"
                        ),
                        "region": self.region,
                        "specs": {
                            "shape_name": lb.shape_name,
                            "ip_addresses": [
                                ip.ip_address for ip in (lb.ip_addresses or [])
                            ],
                            "is_private": lb.is_private,
                            "subnet_ids": lb.subnet_ids or [],
                            "listeners": listeners,
                            "backend_sets": backend_sets,
                            "freeform_tags": lb.freeform_tags or {},
                        },
                    }
                )
        except Exception as e:
            logger.error("oci_list_load_balancers_error", error=str(e))
            raise RuntimeError(f"OCI list_load_balancers failed: {e}") from e
        return lbs

    def list_databases(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        import oci
        from oci.database import DatabaseClient

        client = DatabaseClient(self._config)
        databases: List[Dict[str, Any]] = []
        try:
            # ── VM/BM/Exadata DB Systems ─────────────────────────────────────
            db_systems = oci.pagination.list_call_get_all_results(
                client.list_db_systems,
                compartment_id=self.compartment_id,
            ).data
            for dbs in db_systems:
                databases.append(
                    {
                        "id": dbs.id,
                        "name": dbs.display_name,
                        "status": (
                            dbs.lifecycle_state.lower()
                            if dbs.lifecycle_state
                            else "unknown"
                        ),
                        "region": self.region,
                        "specs": {
                            "db_type": "DBSystem",
                            "shape": dbs.shape,
                            "cpu_core_count": dbs.cpu_core_count,
                            "db_edition": dbs.database_edition,
                            "hostname": dbs.hostname,
                            "disk_redundancy": dbs.disk_redundancy,
                            "data_storage_size_gb": dbs.data_storage_size_in_gbs,
                            "node_count": dbs.node_count,
                            "subnet_id": dbs.subnet_id,
                            "license_model": dbs.license_model,
                            "freeform_tags": dbs.freeform_tags or {},
                        },
                    }
                )

            # ── Autonomous Databases ─────────────────────────────────────────
            adbs = oci.pagination.list_call_get_all_results(
                client.list_autonomous_databases,
                compartment_id=self.compartment_id,
            ).data
            for adb in adbs:
                databases.append(
                    {
                        "id": adb.id,
                        "name": adb.display_name,
                        "status": (
                            adb.lifecycle_state.lower()
                            if adb.lifecycle_state
                            else "unknown"
                        ),
                        "region": self.region,
                        "specs": {
                            "db_type": "AutonomousDatabase",
                            "workload_type": adb.db_workload,
                            "cpu_core_count": adb.cpu_core_count,
                            "data_storage_size_gb": adb.data_storage_size_in_gbs,
                            "db_version": adb.db_version,
                            "is_free_tier": adb.is_free_tier,
                            "is_dedicated": adb.is_dedicated,
                            "subnet_id": getattr(adb, "subnet_id", None),
                            "freeform_tags": adb.freeform_tags or {},
                        },
                    }
                )
        except Exception as e:
            logger.error("oci_list_databases_error", error=str(e))
            raise RuntimeError(f"OCI list_databases failed: {e}") from e
        return databases

    def list_buckets(self) -> List[Dict[str, Any]]:
        from oci.object_storage import ObjectStorageClient
        buckets = []
        try:
            client = ObjectStorageClient(self._config)
            namespace_response = client.get_namespace()
            namespace = namespace_response.data
            response = client.list_buckets(namespace_name=namespace, compartment_id=self.compartment_id)
            for bucket in response.data:
                buckets.append({
                    "id": bucket.name,
                    "name": bucket.name,
                    "region": self.region,
                    "type": "OSS",
                    "specs": {
                        "storage_tier": bucket.storage_tier,
                        "time_created": bucket.time_created.isoformat() if bucket.time_created else None,
                        "freeform_tags": bucket.freeform_tags or {},
                    },
                })
        except Exception as e:
            logger.error("oci_list_buckets_error", error=str(e))
            raise RuntimeError(f"OCI list_buckets failed: {e}") from e
        return buckets
