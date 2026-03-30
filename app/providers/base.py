from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseProvider(ABC):
    """Abstract base class for all cloud provider integrations."""

    @abstractmethod
    def list_vms(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all virtual machines/compute instances.

        Returns a list of dicts with at minimum:
            - id: str  (provider-specific resource ID)
            - name: str
            - status: str
            - region: str
            - specs: dict  (cpu, memory, disk, etc.)
        """

    @abstractmethod
    def list_storage(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all storage resources (buckets, volumes, disks).

        Returns a list of dicts with at minimum:
            - id: str
            - name: str
            - size_gb: float or None
            - region: str
            - type: str
        """

    @abstractmethod
    def list_networks(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all network resources (VPCs, VNets, subnets).

        Returns a list of dicts with at minimum:
            - id: str
            - name: str
            - cidr: str or None
            - region: str
        """

    @abstractmethod
    def get_vm(self, vm_id: str, region: Optional[str] = None) -> Dict[str, Any]:
        """Get details for a single VM by its provider-side ID."""

    @abstractmethod
    def start_vm(self, vm_id: str, region: Optional[str] = None) -> Dict[str, Any]:
        """Start a stopped VM. Returns updated VM details."""

    @abstractmethod
    def stop_vm(self, vm_id: str, region: Optional[str] = None) -> Dict[str, Any]:
        """Stop a running VM. Returns updated VM details."""

    @abstractmethod
    def list_regions(self) -> List[Dict[str, Any]]:
        """List all available regions/zones for this provider.

        Returns a list of dicts with at minimum:
            - id: str
            - name: str
        """

    def test_connection(self) -> bool:
        """Test that credentials are valid and the API is reachable.
        Override in subclasses for a more specific check.
        """
        try:
            self.list_regions()
            return True
        except Exception:
            return False

    def list_load_balancers(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all load balancers.  Override in providers that support them."""
        return []

    def list_databases(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all managed database services.  Override in providers that support them."""
        return []
