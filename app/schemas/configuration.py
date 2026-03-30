from typing import Optional, Any, Dict, List
from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


def _parse_oci_config_input(config_input: Optional[str]) -> Dict[str, str]:
    parsed: Dict[str, str] = {}
    if not config_input:
        return parsed

    field_map = {
        "user": "user_ocid",
        "fingerprint": "fingerprint",
        "tenancy": "tenancy_ocid",
        "region": "region",
    }

    for raw_line in config_input.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("[") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        mapped_key = field_map.get(key.strip().lower())
        if not mapped_key:
            continue

        parsed[mapped_key] = value.split("#", 1)[0].strip()

    return parsed


# ============================================================================
# CloudStack Schemas
# ============================================================================

class CloudStackConfig(BaseModel):
    """CloudStack configuration for testing connectivity."""
    
    api_url: HttpUrl = Field(..., description="CloudStack API URL (e.g., https://cloudstack.example.com/client/api)")
    api_key: str = Field(..., min_length=1, description="CloudStack API Key")
    secret_key: str = Field(..., min_length=1, description="CloudStack Secret Key")
    zone_id: Optional[str] = Field(None, description="Default zone ID (optional)")
    verify_ssl: bool = Field(True, description="Verify SSL certificate")

    @field_validator("api_url", mode="before")
    @classmethod
    def validate_api_url(cls, v):
        if isinstance(v, str):
            v = v.rstrip("/")
        return v


class CloudStackAccountInfo(BaseModel):
    """Account and domain information from CloudStack."""
    username: Optional[str] = Field(None, description="Username")
    account: Optional[str] = Field(None, description="Account name")
    domain: Optional[str] = Field(None, description="Domain name")
    domain_id: Optional[str] = Field(None, description="Domain ID")
    account_type: Optional[int] = Field(None, description="Account type (0=user, 1=admin, 2=domain-admin)")
    email: Optional[str] = Field(None, description="User email")
    state: Optional[str] = Field(None, description="Account state")


class CloudStackTestResult(BaseModel):
    """Result of CloudStack connectivity test."""
    
    connected: bool = Field(..., description="Whether connection was successful")
    api_url: str = Field(..., description="API URL tested")
    zones_found: Optional[int] = Field(None, description="Number of zones found")
    account_info: Optional[CloudStackAccountInfo] = Field(None, description="Account and domain details")
    error_message: Optional[str] = Field(None, description="Error message if connection failed")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")


class CloudStackSaveRequest(BaseModel):
    """Request to save CloudStack credentials securely."""
    api_url: HttpUrl = Field(..., description="CloudStack API URL")
    api_key: str = Field(..., min_length=1, description="CloudStack API Key")
    secret_key: str = Field(..., min_length=1, description="CloudStack Secret Key")
    name: Optional[str] = Field(None, description="Friendly name (auto-generated from domain/account if omitted)")
    zone_id: Optional[str] = Field(None, description="Default zone ID (optional)")
    verify_ssl: bool = Field(True, description="Verify SSL certificate")

    @field_validator("api_url", mode="before")
    @classmethod
    def validate_api_url(cls, v):
        if isinstance(v, str):
            v = v.rstrip("/")
        return v


class CloudStackSavedProvider(BaseModel):
    """Saved CloudStack provider (credentials are masked)."""
    id: int
    name: str
    api_url: str
    account: Optional[str] = None
    domain: Optional[str] = None
    is_active: bool
    created_at: str


class CloudStackZone(BaseModel):
    """CloudStack zone information."""
    
    id: str = Field(..., description="Zone ID")
    name: str = Field(..., description="Zone name")
    network_type: Optional[str] = Field(None, description="Network type")
    dns1: Optional[str] = Field(None, description="Primary DNS")
    dns2: Optional[str] = Field(None, description="Secondary DNS")


class CloudStackZonesList(BaseModel):
    """List of CloudStack zones."""
    
    total: int = Field(..., description="Total zones found")
    zones: list[CloudStackZone] = Field(..., description="List of zones")


# ============================================================================
# AWS Schemas (for future use)
# ============================================================================

class AWSConfig(BaseModel):
    """AWS configuration for testing connectivity."""
    
    access_key_id: str = Field(..., min_length=1, description="AWS Access Key ID")
    secret_access_key: str = Field(..., min_length=1, description="AWS Secret Access Key")
    region: str = Field(default="us-east-1", description="AWS Region")
    session_token: Optional[str] = Field(None, description="AWS Session Token (optional)")


class AWSAccountInfo(BaseModel):
    account_id: Optional[str] = Field(None, description="AWS account ID")
    arn: Optional[str] = Field(None, description="Caller ARN")
    user_id: Optional[str] = Field(None, description="Caller user ID")
    default_region: Optional[str] = Field(None, description="Default AWS region")


class AWSSaveRequest(AWSConfig):
    name: Optional[str] = Field(None, description="Friendly name for the AWS provider")


class AWSTestResult(BaseModel):
    """Result of AWS connectivity test."""
    
    connected: bool = Field(..., description="Whether connection was successful")
    region: Optional[str] = Field(None, description="Default region used in the test")
    account_id: Optional[str] = Field(None, description="AWS Account ID")
    account_info: Optional[AWSAccountInfo] = Field(None, description="AWS caller identity details")
    regions_found: Optional[int] = Field(None, description="Number of regions available")
    error_message: Optional[str] = Field(None, description="Error message if connection failed")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")


class AWSSavedProvider(BaseModel):
    id: int
    name: str
    region: str
    account_id: Optional[str] = None
    arn: Optional[str] = None
    is_active: bool
    created_at: str


# ============================================================================
# GCP Schemas (for future use)
# ============================================================================

class GCPConfig(BaseModel):
    """GCP configuration for testing connectivity."""
    
    project_id: str = Field(..., min_length=1, description="GCP Project ID")
    service_account_key_json: str = Field(..., description="GCP Service Account Key (JSON string)")
    default_region: Optional[str] = Field("us-central1", description="Default GCP region")


class GCPProjectInfo(BaseModel):
    project_id: Optional[str] = Field(None, description="GCP Project ID")
    project_name: Optional[str] = Field(None, description="GCP Project Name")
    project_number: Optional[str] = Field(None, description="GCP Project Number")
    default_region: Optional[str] = Field(None, description="Default region")


class GCPTestResult(BaseModel):
    """Result of GCP connectivity test."""
    
    connected: bool = Field(..., description="Whether connection was successful")
    project_id: Optional[str] = Field(None, description="Project ID verified")
    project_info: Optional[GCPProjectInfo] = Field(None, description="GCP project details")
    regions_found: Optional[int] = Field(None, description="Number of regions available")
    error_message: Optional[str] = Field(None, description="Error message if connection failed")


class GCPSaveRequest(GCPConfig):
    name: Optional[str] = Field(None, description="Friendly name for the GCP provider")


class GCPSavedProvider(BaseModel):
    id: int
    name: str
    project_id: str
    default_region: Optional[str] = None
    is_active: bool
    created_at: str


# ============================================================================
# Azure Schemas (for future use)
# ============================================================================

class AzureConfig(BaseModel):
    """Azure configuration for testing connectivity."""
    
    subscription_id: str = Field(..., min_length=1, description="Azure Subscription ID")
    tenant_id: str = Field(..., min_length=1, description="Azure Tenant ID")
    client_id: str = Field(..., min_length=1, description="Azure Client ID (Application ID)")
    client_secret: str = Field(..., min_length=1, description="Azure Client Secret")
    default_location: Optional[str] = Field("eastus", description="Default Azure location")


class AzureAccountInfo(BaseModel):
    subscription_id: Optional[str] = Field(None, description="Subscription ID")
    tenant_id: Optional[str] = Field(None, description="Tenant ID")
    subscription_name: Optional[str] = Field(None, description="Subscription display name")
    default_location: Optional[str] = Field(None, description="Default location")
    state: Optional[str] = Field(None, description="Subscription state")


class AzureTestResult(BaseModel):
    """Result of Azure connectivity test."""
    
    connected: bool = Field(..., description="Whether connection was successful")
    subscription_id: Optional[str] = Field(None, description="Subscription ID verified")
    account_info: Optional[AzureAccountInfo] = Field(None, description="Azure account details")
    regions_found: Optional[int] = Field(None, description="Number of regions available")
    error_message: Optional[str] = Field(None, description="Error message if connection failed")


class AzureSaveRequest(AzureConfig):
    name: Optional[str] = Field(None, description="Friendly name for the Azure provider")


class AzureSavedProvider(BaseModel):
    id: int
    name: str
    subscription_id: str
    tenant_id: Optional[str] = None
    default_location: Optional[str] = None
    is_active: bool
    created_at: str


# ============================================================================
# OCI Schemas (for future use)
# ============================================================================

class OCIConfig(BaseModel):
    """OCI configuration for testing connectivity."""

    config_input: Optional[str] = Field(None, description="OCI config block copied from the console")
    user_ocid: Optional[str] = Field(None, min_length=1, description="OCI User OCID")
    fingerprint: Optional[str] = Field(None, min_length=1, description="OCI API Key Fingerprint")
    tenancy_ocid: Optional[str] = Field(None, min_length=1, description="OCI Tenancy OCID")
    region: Optional[str] = Field(default=None, description="OCI Region")
    private_key_content: str = Field(..., description="OCI Private Key Content (PEM format)")
    compartment_id: Optional[str] = Field(None, description="OCI Compartment ID (defaults to tenancy)")

    @model_validator(mode="after")
    def populate_from_config_input(self):
        parsed = _parse_oci_config_input(self.config_input)

        self.user_ocid = self.user_ocid or parsed.get("user_ocid")
        self.fingerprint = self.fingerprint or parsed.get("fingerprint")
        self.tenancy_ocid = self.tenancy_ocid or parsed.get("tenancy_ocid")
        self.region = self.region or parsed.get("region") or "us-ashburn-1"

        missing = []
        if not self.user_ocid:
            missing.append("user")
        if not self.fingerprint:
            missing.append("fingerprint")
        if not self.tenancy_ocid:
            missing.append("tenancy")
        if not self.private_key_content:
            missing.append("private_key")

        if missing:
            raise ValueError("Missing OCI fields: " + ", ".join(missing))

        return self


class OCITenancyInfo(BaseModel):
    tenancy_ocid: Optional[str] = Field(None, description="Tenancy OCID")
    tenancy_name: Optional[str] = Field(None, description="Tenancy name")
    user_ocid: Optional[str] = Field(None, description="User OCID")
    region: Optional[str] = Field(None, description="Home region")
    home_region: Optional[str] = Field(None, description="Tenancy home region key")


class OCITestResult(BaseModel):
    """Result of OCI connectivity test."""
    
    connected: bool = Field(..., description="Whether connection was successful")
    tenancy_ocid: Optional[str] = Field(None, description="Tenancy OCID verified")
    account_info: Optional[OCITenancyInfo] = Field(None, description="OCI tenancy details")
    regions_found: Optional[int] = Field(None, description="Number of regions available")
    error_message: Optional[str] = Field(None, description="Error message if connection failed")


class OCISaveRequest(OCIConfig):
    name: Optional[str] = Field(None, description="Friendly name for the OCI provider")


class OCISavedProvider(BaseModel):
    id: int
    name: str
    tenancy_ocid: str
    region: Optional[str] = None
    is_active: bool
    created_at: str


# ============================================================================
# Generic Configuration Test Request/Response
# ============================================================================

class ProviderConfigTest(BaseModel):
    """Generic provider configuration test request."""
    
    provider_type: str = Field(..., description="Provider type (CLOUDSTACK, AWS, GCP, AZURE, OCI)")
    config: Dict[str, Any] = Field(..., description="Provider configuration")


class ProviderTestResult(BaseModel):
    """Generic provider test result."""
    
    provider_type: str = Field(..., description="Provider type tested")
    connected: bool = Field(..., description="Whether connection was successful")
    timestamp: str = Field(..., description="Timestamp of test")
    message: str = Field(..., description="Status message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")
