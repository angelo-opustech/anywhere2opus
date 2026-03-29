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

    def _s3(self):
        return self._session.client("s3", region_name=self.default_region)

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
        s3 = self._s3()
        storages = []
        try:
            response = s3.list_buckets()
            for bucket in response.get("Buckets", []):
                bucket_region = self.default_region
                try:
                    loc = s3.get_bucket_location(Bucket=bucket["Name"])
                    bucket_region = loc.get("LocationConstraint") or "us-east-1"
                except ClientError:
                    pass
                storages.append(
                    {
                        "id": bucket["Name"],
                        "name": bucket["Name"],
                        "size_gb": None,
                        "region": bucket_region,
                        "type": "S3",
                        "specs": {
                            "creation_date": (
                                bucket["CreationDate"].isoformat()
                                if bucket.get("CreationDate")
                                else None
                            ),
                        },
                    }
                )
        except (ClientError, BotoCoreError) as e:
            logger.error("aws_list_storage_error", error=str(e))
            raise RuntimeError(f"AWS list_storage failed: {e}") from e
        return storages

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
                        },
                    }
                )
        except (ClientError, BotoCoreError) as e:
            logger.error("aws_list_networks_error", error=str(e))
            raise RuntimeError(f"AWS list_networks failed: {e}") from e
        return networks

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
