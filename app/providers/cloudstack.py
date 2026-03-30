import base64
import hashlib
import hmac
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests
import structlog

from app.providers.base import BaseProvider

logger = structlog.get_logger(__name__)


class CloudStackProvider(BaseProvider):
    """Apache CloudStack / Opus cloud provider.

    Authentication uses HMAC-SHA1 signed requests as per the CloudStack API spec:
      1. Build the parameter dict including 'apiKey' and 'command'.
      2. Sort parameters by key (case-insensitive).
      3. URL-encode the query string, then lowercase the entire string for signing.
      4. Sign with HMAC-SHA1 using the secret key.
      5. Base64-encode the digest and append as 'signature'.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        secret_key: str,
        zone_id: Optional[str] = None,
        timeout: int = 60,
        verify_ssl: bool = True,
    ):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.secret_key = secret_key
        self.default_zone_id = zone_id
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        if not verify_ssl:
            logger.warning("cloudstack_ssl_verification_disabled", api_url=self.api_url)

    def _sign(self, params: Dict[str, str]) -> str:
        """Return HMAC-SHA1 signature for the given sorted parameter dict."""
        sorted_params = sorted(params.items(), key=lambda kv: kv[0].lower())
        # Build URL-encoded query string
        query_string = "&".join(
            f"{quote(str(k), safe='')}={quote(str(v), safe='')}"
            for k, v in sorted_params
        )
        # Lowercase the entire string before signing
        string_to_sign = query_string.lower()
        digest = hmac.new(
            self.secret_key.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha1,
        ).digest()
        return base64.b64encode(digest).decode("utf-8")

    def _make_request(self, command: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a signed CloudStack API command.

        Args:
            command: CloudStack API command name (e.g. 'listVirtualMachines').
            params: Additional parameters for the command.

        Returns:
            Parsed JSON response dict.

        Raises:
            RuntimeError: On HTTP or API-level errors.
        """
        all_params: Dict[str, str] = {
            "command": command,
            "apiKey": self.api_key,
            "response": "json",
        }
        if params:
            for k, v in params.items():
                all_params[str(k)] = str(v)

        signature = self._sign(all_params)
        all_params["signature"] = signature

        try:
            response = requests.get(
                self.api_url,
                params=all_params,
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            logger.error("cloudstack_request_error", command=command, error=str(e))
            raise RuntimeError(f"CloudStack request '{command}' failed: {e}") from e

        # Detect API-level errors embedded in response
        error_response_key = f"{command.lower()}response"
        resp_data = data.get(error_response_key, data)
        if isinstance(resp_data, dict) and "errorcode" in resp_data:
            msg = resp_data.get("errortext", "Unknown CloudStack API error")
            raise RuntimeError(f"CloudStack API error ({resp_data['errorcode']}): {msg}")

        return data

    # --- BaseProvider interface ---

    def list_vms(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"listall": "true"}
        if region:
            params["zoneid"] = region
        result = self._make_request("listVirtualMachines", params)
        vms_data = result.get("listvirtualmachinesresponse", {}).get("virtualmachine", [])
        vms = []
        for vm in vms_data:
            vms.append({
                "id": vm["id"],
                "name": vm.get("displayname", vm.get("name")),
                "status": (vm.get("state") or "").lower(),
                "region": vm.get("zonename", ""),
                "specs": {
                    "service_offering": vm.get("serviceofferingname"),
                    "cpunumber": vm.get("cpunumber"),
                    "memory_mb": vm.get("memory"),
                    "template": vm.get("templatename"),
                    "hypervisor": vm.get("hypervisor"),
                    "ips": [nic.get("ipaddress") for nic in vm.get("nic", [])],
                },
            })
        return vms

    def list_storage(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"listall": "true"}
        if region:
            params["zoneid"] = region
        result = self._make_request("listVolumes", params)
        vols_data = result.get("listvolumesresponse", {}).get("volume", [])
        volumes = []
        for vol in vols_data:
            volumes.append({
                "id": vol["id"],
                "name": vol.get("name"),
                "size_gb": vol.get("size", 0) // (1024 ** 3),
                "region": vol.get("zonename", ""),
                "type": vol.get("type", ""),
                "specs": {
                    "state": vol.get("state"),
                    "vm_name": vol.get("vmname"),
                    "storage_type": vol.get("storagetype"),
                },
            })
        return volumes

    def list_networks(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"listall": "true"}
        if region:
            params["zoneid"] = region
        result = self._make_request("listNetworks", params)
        nets_data = result.get("listnetworksresponse", {}).get("network", [])
        networks = []
        for net in nets_data:
            networks.append({
                "id": net["id"],
                "name": net.get("name"),
                "cidr": net.get("cidr"),
                "region": net.get("zonename", ""),
                "type": net.get("type", ""),
                "specs": {
                    "gateway": net.get("gateway"),
                    "state": net.get("state"),
                    "network_offering": net.get("networkofferingname"),
                },
            })
        return networks

    def get_vm(self, vm_id: str, region: Optional[str] = None) -> Dict[str, Any]:
        result = self._make_request("listVirtualMachines", {"id": vm_id})
        vms = result.get("listvirtualmachinesresponse", {}).get("virtualmachine", [])
        if not vms:
            raise ValueError(f"VM {vm_id} not found in CloudStack")
        vm = vms[0]
        return {
            "id": vm["id"],
            "name": vm.get("displayname", vm.get("name")),
            "status": (vm.get("state") or "").lower(),
            "region": vm.get("zonename", ""),
            "specs": {
                "service_offering": vm.get("serviceofferingname"),
                "cpunumber": vm.get("cpunumber"),
                "memory_mb": vm.get("memory"),
            },
        }

    def start_vm(self, vm_id: str, region: Optional[str] = None) -> Dict[str, Any]:
        try:
            self._make_request("startVirtualMachine", {"id": vm_id})
            return self.get_vm(vm_id, region)
        except Exception as e:
            logger.error("cloudstack_start_vm_error", vm_id=vm_id, error=str(e))
            raise RuntimeError(f"CloudStack start_vm failed: {e}") from e

    def get_account_info(self) -> Dict[str, Any]:
        """Return account and domain info associated with the current API key.

        Uses listUsers with listall=false to retrieve only the user that owns
        the API key, then returns account/domain metadata.
        """
        try:
            result = self._make_request("listUsers", {"listall": "false"})
            users = result.get("listusersresponse", {}).get("user", [])
            if users:
                user = users[0]
                return {
                    "username": user.get("username"),
                    "account": user.get("account"),
                    "domain": user.get("domain"),
                    "domain_id": user.get("domainid"),
                    "account_type": user.get("accounttype"),
                    "email": user.get("email", ""),
                    "state": user.get("state"),
                }
        except Exception as e:
            logger.warning("cloudstack_get_account_info_failed", error=str(e))
        return {}

    def stop_vm(self, vm_id: str, region: Optional[str] = None) -> Dict[str, Any]:
        try:
            self._make_request("stopVirtualMachine", {"id": vm_id})
            return self.get_vm(vm_id, region)
        except Exception as e:
            logger.error("cloudstack_stop_vm_error", vm_id=vm_id, error=str(e))
            raise RuntimeError(f"CloudStack stop_vm failed: {e}") from e

    def list_regions(self) -> List[Dict[str, Any]]:
        result = self._make_request("listZones")
        zones_data = result.get("listzonesresponse", {}).get("zone", [])
        zones = []
        for zone in zones_data:
            zones.append({
                "id": zone["id"],
                "name": zone.get("name"),
            })
        return zones

    def list_public_ips(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        """List allocated public IP addresses."""
        params: Dict[str, Any] = {"listall": "true", "allocatedonly": "true"}
        if region:
            params["zoneid"] = region
        try:
            result = self._make_request("listPublicIpAddresses", params)
            ips_data = result.get("listpublicipaddressesresponse", {}).get("publicipaddress", [])
            return [
                {
                    "id": ip["id"],
                    "ip_address": ip.get("ipaddress"),
                    "region": ip.get("zonename", ""),
                    "state": ip.get("state"),
                    "allocated": ip.get("allocated"),
                    "associated_network": ip.get("associatednetworkname"),
                    "is_source_nat": ip.get("issourcenat", False),
                    "is_static_nat": ip.get("isstaticnat", False),
                    "vm_name": ip.get("virtualmachinename"),
                }
                for ip in ips_data
            ]
        except Exception as e:
            logger.warning("cloudstack_list_public_ips_failed", error=str(e))
            return []

    def list_service_offerings(self) -> List[Dict[str, Any]]:
        """List available service offerings (compute plans)."""
        try:
            result = self._make_request("listServiceOfferings", {"listall": "true"})
            offerings = result.get("listserviceofferingsresponse", {}).get("serviceoffering", [])
            return [
                {
                    "id": o["id"],
                    "name": o.get("name"),
                    "display_text": o.get("displaytext"),
                    "cpunumber": o.get("cpunumber"),
                    "cpuspeed": o.get("cpuspeed"),
                    "memory_mb": o.get("memory"),
                    "storage_type": o.get("storagetype"),
                }
                for o in offerings
            ]
        except Exception as e:
            logger.warning("cloudstack_list_service_offerings_failed", error=str(e))
            return []

    def list_templates(self, template_filter: str = "self") -> List[Dict[str, Any]]:
        """List available templates.

        Args:
            template_filter: 'self' (own templates), 'featured', 'community', 'all'
        """
        try:
            result = self._make_request("listTemplates", {"templatefilter": template_filter, "listall": "true"})
            templates = result.get("listtemplatesresponse", {}).get("template", [])
            return [
                {
                    "id": t["id"],
                    "name": t.get("name"),
                    "display_text": t.get("displaytext"),
                    "os_type": t.get("ostypename"),
                    "region": t.get("zonename", ""),
                    "size_gb": (t.get("size", 0) or 0) // (1024 ** 3),
                    "status": t.get("status"),
                    "is_public": t.get("ispublic", False),
                    "hypervisor": t.get("hypervisor"),
                    "created": t.get("created"),
                }
                for t in templates
            ]
        except Exception as e:
            logger.warning("cloudstack_list_templates_failed", error=str(e))
            return []

    def test_connection(self) -> bool:
        """Test connection to CloudStack API."""
        try:
            logger.info("cloudstack_test_connection", api_url=self.api_url)
            result = self._make_request("listZones")
            success = "listzonesresponse" in result
            if success:
                logger.info("cloudstack_connection_ok", zones_count=len(result.get("listzonesresponse", {}).get("zone", [])))
            return success
        except Exception as e:
            logger.error("cloudstack_connection_failed", error=str(e))
            return False

    # --- CloudStack-specific methods for migration ---

    def list_disk_offerings(self) -> List[Dict[str, Any]]:
        result = self._make_request("listDiskOfferings")
        offerings = result.get("listdiskofferingsresponse", {}).get("diskoffering", [])
        return [
            {
                "id": o["id"],
                "name": o["name"],
                "disk_size_gb": o.get("disksize"),
                "description": o.get("displaytext"),
            }
            for o in offerings
        ]

    def deploy_virtual_machine(
        self,
        service_offering_id: str,
        template_id: str,
        zone_id: str,
        name: str,
        network_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        params = {
            "serviceofferingid": service_offering_id,
            "templateid": template_id,
            "zoneid": zone_id,
            "displayname": name,
            "name": name,
        }
        if network_id:
            params["networkids"] = network_id
        result = self._make_request("deployVirtualMachine", params)
        resp = result.get("deployvirtualmachineresponse", {})
        logger.info("cloudstack_deploy_vm", name=name, job_id=resp.get("jobid"))
        return {"vm_id": resp.get("id"), "job_id": resp.get("jobid"), "status": "deploying"}

    def register_template(
        self,
        name: str,
        display_text: str,
        url: str,
        zone_id: str,
        os_type_id: str,
        hypervisor: str = "KVM",
        format_type: str = "QCOW2",
    ) -> Dict[str, Any]:
        result = self._make_request(
            "registerTemplate",
            {
                "name": name,
                "displaytext": display_text,
                "url": url,
                "zoneid": zone_id,
                "ostypeid": os_type_id,
                "hypervisor": hypervisor,
                "format": format_type,
            },
        )
        templates = result.get("registertemplateresponse", {}).get("template", [])
        if templates:
            logger.info("cloudstack_register_template", name=name, id=templates[0]["id"])
            return templates[0]
        return {}
