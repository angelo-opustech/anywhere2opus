from typing import Any, Dict, List, Optional
import structlog

import boto3
from botocore.exceptions import ClientError, BotoCoreError

from app.providers.base import BaseProvider

logger = structlog.get_logger(__name__)


class AWSProvider(BaseProvider):
    """AWS cloud provider using boto3."""

    def __init__(
        self,
        access_key_id: str,
        secret_access_key: str,
        region: str = "us-east-1",
        session_token: Optional[str] = None,
    ):
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.default_region = region
        self.session_token = session_token
        self._session = self._create_session()

    def _create_session(self) -> boto3.Session:
        kwargs = dict(
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            region_name=self.default_region,
        )
        if self.session_token:
            kwargs["aws_session_token"] = self.session_token
        return boto3.Session(**kwargs)

    def _ec2(self, region: Optional[str] = None):
        return self._session.client("ec2", region_name=region or self.default_region)

    def _s3(self, region: Optional[str] = None):
        return self._session.client("s3", region_name=region or self.default_region)

    def _sts(self):
        return self._session.client("sts", region_name=self.default_region)

    def get_account_info(self) -> Dict[str, Any]:
        sts = self._sts()
        try:
            response = sts.get_caller_identity()
            return {
                "account_id": response.get("Account"),
                "arn": response.get("Arn"),
                "user_id": response.get("UserId"),
                "default_region": self.default_region,
            }
        except (ClientError, BotoCoreError) as e:
            logger.error("aws_get_account_info_error", error=str(e))
            raise RuntimeError(f"AWS get_account_info failed: {e}") from e

    def test_connection(self) -> bool:
        try:
            self.get_account_info()
            self.list_regions()
            return True
        except Exception:
            return False

    def list_vms(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        ec2 = self._ec2(region)
        vms = []
        try:
            paginator = ec2.get_paginator("describe_instances")
            for page in paginator.paginate():
                for reservation in page.get("Reservations", []):
                    for instance in reservation.get("Instances", []):
                        name = ""
                        for tag in instance.get("Tags", []):
                            if tag["Key"] == "Name":
                                name = tag["Value"]
                                break
                        vms.append(
                            {
                                "id": instance["InstanceId"],
                                "name": name or instance["InstanceId"],
                                "status": instance["State"]["Name"],
                                "region": region or self.default_region,
                                "type": instance.get("InstanceType", ""),
                                "specs": {
                                    "instance_type": instance.get("InstanceType"),
                                    "platform": instance.get("Platform", "linux"),
                                    "architecture": instance.get("Architecture"),
                                    "private_ip": instance.get("PrivateIpAddress"),
                                    "public_ip": instance.get("PublicIpAddress"),
                                    "vpc_id": instance.get("VpcId"),
                                    "subnet_id": instance.get("SubnetId"),
                                    "image_id": instance.get("ImageId"),
                                    "key_name": instance.get("KeyName"),
                                    "availability_zone": instance.get("Placement", {}).get("AvailabilityZone"),
                                    "monitoring": instance.get("Monitoring", {}).get("State"),
                                    "security_groups": [group.get("GroupName") for group in instance.get("SecurityGroups", [])],
                                    "launch_time": (
                                        instance["LaunchTime"].isoformat()
                                        if instance.get("LaunchTime")
                                        else None
                                    ),
                                },
                            }
                        )
        except (ClientError, BotoCoreError) as e:
            logger.error("aws_list_vms_error", error=str(e))
            raise RuntimeError(f"AWS list_vms failed: {e}") from e
        return vms

    def list_storage(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        ec2 = self._ec2(region)
        storages = []
        try:
            paginator = ec2.get_paginator("describe_volumes")
            for page in paginator.paginate():
                for volume in page.get("Volumes", []):
                    attachment = volume.get("Attachments", [{}])[0] if volume.get("Attachments") else {}
                    name = volume.get("VolumeId")
                    for tag in volume.get("Tags", []):
                        if tag.get("Key") == "Name":
                            name = tag.get("Value")
                            break
                    storages.append(
                        {
                            "id": volume["VolumeId"],
                            "name": name,
                            "size_gb": volume.get("Size"),
                            "region": region or self.default_region,
                            "type": volume.get("VolumeType", "EBS"),
                            "specs": {
                                "state": volume.get("State"),
                                "availability_zone": volume.get("AvailabilityZone"),
                                "iops": volume.get("Iops"),
                                "throughput": volume.get("Throughput"),
                                "encrypted": volume.get("Encrypted"),
                                "snapshot_id": volume.get("SnapshotId"),
                                "attached_instance_id": attachment.get("InstanceId"),
                                "device": attachment.get("Device"),
                            },
                        }
                    )
        except (ClientError, BotoCoreError) as e:
            logger.error("aws_list_storage_error", error=str(e))
            raise RuntimeError(f"AWS list_storage failed: {e}") from e
        return storages

    def list_buckets(self) -> List[Dict[str, Any]]:
        s3 = self._s3()
        buckets = []
        try:
            response = s3.list_buckets()
            owner = response.get("Owner", {})
            for bucket in response.get("Buckets", []):
                bucket_region = self.default_region
                try:
                    loc = s3.get_bucket_location(Bucket=bucket["Name"])
                    bucket_region = loc.get("LocationConstraint") or "us-east-1"
                except ClientError:
                    pass
                buckets.append(
                    {
                        "id": bucket["Name"],
                        "name": bucket["Name"],
                        "region": bucket_region,
                        "type": "S3",
                        "specs": {
                            "creation_date": (
                                bucket["CreationDate"].isoformat()
                                if bucket.get("CreationDate")
                                else None
                            ),
                            "owner_id": owner.get("ID"),
                            "owner_display_name": owner.get("DisplayName"),
                        },
                    }
                )
        except (ClientError, BotoCoreError) as e:
            logger.error("aws_list_buckets_error", error=str(e))
            raise RuntimeError(f"AWS list_buckets failed: {e}") from e
        return buckets

    def list_networks(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        ec2 = self._ec2(region)
        networks = []
        try:
            response = ec2.describe_vpcs()
            for vpc in response.get("Vpcs", []):
                name = ""
                for tag in vpc.get("Tags", []):
                    if tag["Key"] == "Name":
                        name = tag["Value"]
                        break
                networks.append(
                    {
                        "id": vpc["VpcId"],
                        "name": name or vpc["VpcId"],
                        "cidr": vpc.get("CidrBlock"),
                        "region": region or self.default_region,
                        "type": "VPC",
                        "specs": {
                            "state": vpc.get("State"),
                            "is_default": vpc.get("IsDefault", False),
                            "dhcp_options_id": vpc.get("DhcpOptionsId"),
                            "owner_id": vpc.get("OwnerId"),
                            "instance_tenancy": vpc.get("InstanceTenancy"),
                            "ipv6_cidrs": [cidr.get("Ipv6CidrBlock") for cidr in vpc.get("Ipv6CidrBlockAssociationSet", [])],
                        },
                    }
                )
        except (ClientError, BotoCoreError) as e:
            logger.error("aws_list_networks_error", error=str(e))
            raise RuntimeError(f"AWS list_networks failed: {e}") from e
        return networks

    def list_elastic_ips(self, region: Optional[str] = None) -> List[Dict[str, Any]]:
        ec2 = self._ec2(region)
        addresses = []
        try:
            response = ec2.describe_addresses()
            for address in response.get("Addresses", []):
                addresses.append(
                    {
                        "id": address.get("AllocationId") or address.get("PublicIp"),
                        "public_ip": address.get("PublicIp"),
                        "region": region or self.default_region,
                        "domain": address.get("Domain"),
                        "instance_id": address.get("InstanceId"),
                        "private_ip": address.get("PrivateIpAddress"),
                        "network_interface_id": address.get("NetworkInterfaceId"),
                        "network_border_group": address.get("NetworkBorderGroup"),
                        "service_managed": address.get("ServiceManaged"),
                    }
                )
        except (ClientError, BotoCoreError) as e:
            logger.error("aws_list_elastic_ips_error", error=str(e))
            raise RuntimeError(f"AWS list_elastic_ips failed: {e}") from e
        return addresses

    def list_instance_types(self, region: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        ec2 = self._ec2(region)
        instance_types = []
        next_token = None
        try:
            while len(instance_types) < limit:
                kwargs: Dict[str, Any] = {"MaxResults": min(100, limit - len(instance_types))}
                if next_token:
                    kwargs["NextToken"] = next_token
                response = ec2.describe_instance_types(**kwargs)
                for item in response.get("InstanceTypes", []):
                    instance_types.append(
                        {
                            "id": item.get("InstanceType"),
                            "name": item.get("InstanceType"),
                            "vcpu": item.get("VCpuInfo", {}).get("DefaultVCpus"),
                            "memory_mb": item.get("MemoryInfo", {}).get("SizeInMiB"),
                            "network_performance": item.get("NetworkInfo", {}).get("NetworkPerformance"),
                            "current_generation": item.get("CurrentGeneration"),
                            "free_tier_eligible": item.get("FreeTierEligible"),
                            "architecture": item.get("ProcessorInfo", {}).get("SupportedArchitectures", []),
                            "hypervisor": item.get("Hypervisor"),
                        }
                    )
                next_token = response.get("NextToken")
                if not next_token:
                    break
        except (ClientError, BotoCoreError) as e:
            logger.error("aws_list_instance_types_error", error=str(e))
            raise RuntimeError(f"AWS list_instance_types failed: {e}") from e
        return instance_types

    def list_images(self, region: Optional[str] = None, limit: int = 60) -> List[Dict[str, Any]]:
        ec2 = self._ec2(region)
        images: List[Dict[str, Any]] = []

        def _collect(owners: List[str], remaining: int) -> None:
            next_token = None
            while remaining > 0:
                kwargs: Dict[str, Any] = {
                    "Owners": owners,
                    "MaxResults": min(100, remaining),
                    "Filters": [{"Name": "state", "Values": ["available"]}],
                }
                if next_token:
                    kwargs["NextToken"] = next_token
                response = ec2.describe_images(**kwargs)
                for image in response.get("Images", []):
                    images.append(
                        {
                            "id": image.get("ImageId"),
                            "name": image.get("Name") or image.get("ImageId"),
                            "description": image.get("Description"),
                            "architecture": image.get("Architecture"),
                            "platform": image.get("PlatformDetails") or image.get("Platform") or "Linux/UNIX",
                            "image_type": image.get("ImageType"),
                            "owner_id": image.get("OwnerId"),
                            "is_public": image.get("Public"),
                            "state": image.get("State"),
                            "creation_date": image.get("CreationDate"),
                            "root_device_type": image.get("RootDeviceType"),
                        }
                    )
                    remaining -= 1
                    if remaining == 0:
                        break
                next_token = response.get("NextToken")
                if not next_token or remaining == 0:
                    break

        try:
            _collect(["self"], limit)
            if len(images) < limit:
                _collect(["amazon"], limit - len(images))
        except (ClientError, BotoCoreError) as e:
            logger.error("aws_list_images_error", error=str(e))
            raise RuntimeError(f"AWS list_images failed: {e}") from e

        return images

    def get_vm(self, vm_id: str, region: Optional[str] = None) -> Dict[str, Any]:
        ec2 = self._ec2(region)
        try:
            response = ec2.describe_instances(InstanceIds=[vm_id])
            reservations = response.get("Reservations", [])
            if not reservations:
                raise ValueError(f"VM {vm_id} not found")
            instance = reservations[0]["Instances"][0]
            name = ""
            for tag in instance.get("Tags", []):
                if tag["Key"] == "Name":
                    name = tag["Value"]
                    break
            return {
                "id": instance["InstanceId"],
                "name": name or instance["InstanceId"],
                "status": instance["State"]["Name"],
                "region": region or self.default_region,
                "specs": {
                    "instance_type": instance.get("InstanceType"),
                    "private_ip": instance.get("PrivateIpAddress"),
                    "public_ip": instance.get("PublicIpAddress"),
                    "vpc_id": instance.get("VpcId"),
                    "image_id": instance.get("ImageId"),
                },
            }
        except ClientError as e:
            logger.error("aws_get_vm_error", vm_id=vm_id, error=str(e))
            raise RuntimeError(f"AWS get_vm failed: {e}") from e

    def start_vm(self, vm_id: str, region: Optional[str] = None) -> Dict[str, Any]:
        ec2 = self._ec2(region)
        try:
            ec2.start_instances(InstanceIds=[vm_id])
            ec2.get_waiter("instance_running").wait(InstanceIds=[vm_id])
            return self.get_vm(vm_id, region)
        except (ClientError, BotoCoreError) as e:
            logger.error("aws_start_vm_error", vm_id=vm_id, error=str(e))
            raise RuntimeError(f"AWS start_vm failed: {e}") from e

    def stop_vm(self, vm_id: str, region: Optional[str] = None) -> Dict[str, Any]:
        ec2 = self._ec2(region)
        try:
            ec2.stop_instances(InstanceIds=[vm_id])
            ec2.get_waiter("instance_stopped").wait(InstanceIds=[vm_id])
            return self.get_vm(vm_id, region)
        except (ClientError, BotoCoreError) as e:
            logger.error("aws_stop_vm_error", vm_id=vm_id, error=str(e))
            raise RuntimeError(f"AWS stop_vm failed: {e}") from e

    def list_regions(self) -> List[Dict[str, Any]]:
        ec2 = self._ec2()
        try:
            response = ec2.describe_regions(AllRegions=False)
            return [
                {
                    "id": r["RegionName"],
                    "name": r["RegionName"],
                    "endpoint": r.get("Endpoint", ""),
                    "opt_in_status": r.get("OptInStatus", ""),
                }
                for r in response.get("Regions", [])
            ]
        except (ClientError, BotoCoreError) as e:
            logger.error("aws_list_regions_error", error=str(e))
            raise RuntimeError(f"AWS list_regions failed: {e}") from e
