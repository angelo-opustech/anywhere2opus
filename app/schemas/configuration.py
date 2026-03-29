from typing import Optional, Any, Dict
from pydantic import BaseModel, Field, HttpUrl, field_validator


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


class AWSTestResult(BaseModel):
    """Result of AWS connectivity test."""
    
    connected: bool = Field(..., description="Whether connection was successful")
    account_id: Optional[str] = Field(None, description="AWS Account ID")
    regions_found: Optional[int] = Field(None, description="Number of regions available")
    error_message: Optional[str] = Field(None, description="Error message if connection failed")


# ============================================================================
# GCP Schemas (for future use)
# ============================================================================

class GCPConfig(BaseModel):
    """GCP configuration for testing connectivity."""
    
    project_id: str = Field(..., min_length=1, description="GCP Project ID")
    service_account_key_json: str = Field(..., description="GCP Service Account Key (JSON string)")


class GCPTestResult(BaseModel):
    """Result of GCP connectivity test."""
    
    connected: bool = Field(..., description="Whether connection was successful")
    project_id: Optional[str] = Field(None, description="Project ID verified")
    error_message: Optional[str] = Field(None, description="Error message if connection failed")


# ============================================================================
# Azure Schemas (for future use)
# ============================================================================

class AzureConfig(BaseModel):
    """Azure configuration for testing connectivity."""
    
    subscription_id: str = Field(..., min_length=1, description="Azure Subscription ID")
    tenant_id: str = Field(..., min_length=1, description="Azure Tenant ID")
    client_id: str = Field(..., min_length=1, description="Azure Client ID")
    client_secret: str = Field(..., min_length=1, description="Azure Client Secret")


class AzureTestResult(BaseModel):
    """Result of Azure connectivity test."""
    
    connected: bool = Field(..., description="Whether connection was successful")
    subscription_id: Optional[str] = Field(None, description="Subscription ID verified")
    error_message: Optional[str] = Field(None, description="Error message if connection failed")


# ============================================================================
# OCI Schemas (for future use)
# ============================================================================

class OCIConfig(BaseModel):
    """OCI configuration for testing connectivity."""
    
    user_ocid: str = Field(..., min_length=1, description="OCI User OCID")
    fingerprint: str = Field(..., min_length=1, description="OCI API Key Fingerprint")
    tenancy_ocid: str = Field(..., min_length=1, description="OCI Tenancy OCID")
    region: str = Field(..., min_length=1, description="OCI Region")
    private_key_content: str = Field(..., description="OCI Private Key Content")


class OCITestResult(BaseModel):
    """Result of OCI connectivity test."""
    
    connected: bool = Field(..., description="Whether connection was successful")
    tenancy_ocid: Optional[str] = Field(None, description="Tenancy OCID verified")
    error_message: Optional[str] = Field(None, description="Error message if connection failed")


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

