"""Configuration and connection testing endpoints for cloud providers."""

from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status
import structlog

from app.models.provider import ProviderType
from app.providers.factory import get_provider
from app.schemas.configuration import (
    CloudStackConfig,
    CloudStackTestResult,
    CloudStackZonesList,
    CloudStackZone,
    ProviderConfigTest,
    ProviderTestResult,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/configuration", tags=["Configuration & Testing"])


# ============================================================================
# CloudStack Configuration & Testing
# ============================================================================

@router.post(
    "/cloudstack/test",
    response_model=CloudStackTestResult,
    summary="Test CloudStack API connection",
    description="Test connectivity to a CloudStack API without saving configuration"
)
def test_cloudstack_connection(config: CloudStackConfig):
    """
    Test connection to CloudStack API.
    
    This endpoint allows testing CloudStack connectivity before saving the provider configuration.
    
    Args:
        config: CloudStack configuration including API URL, keys, and optional zone ID
        
    Returns:
        CloudStackTestResult with connection status and zone information
    """
    try:
        logger.info(
            "cloudstack_test_start",
            api_url=str(config.api_url),
            verify_ssl=config.verify_ssl,
        )
        
        # Create provider instance
        provider = get_provider(
            ProviderType.CLOUDSTACK,
            credentials={
                "api_url": str(config.api_url),
                "api_key": config.api_key,
                "secret_key": config.secret_key,
                "zone_id": config.zone_id,
            },
        )
        
        # Test connection
        connected = provider.test_connection()
        
        if not connected:
            logger.warning("cloudstack_test_failed_no_response")
            return CloudStackTestResult(
                connected=False,
                api_url=str(config.api_url),
                error_message="Failed to connect - no response from API",
            )
        
        # Get zones if connection successful
        try:
            zones_data = provider.list_regions()
            zones_count = len(zones_data)
            
            logger.info(
                "cloudstack_test_success",
                api_url=str(config.api_url),
                zones_count=zones_count,
            )
            
            return CloudStackTestResult(
                connected=True,
                api_url=str(config.api_url),
                zones_found=zones_count,
                details={"zones": zones_data},
            )
        except Exception as e:
            logger.error("cloudstack_list_zones_failed", error=str(e))
            return CloudStackTestResult(
                connected=True,
                api_url=str(config.api_url),
                zones_found=0,
                error_message=f"Connection OK but failed to list zones: {str(e)}",
            )
            
    except Exception as e:
        error_msg = str(e)
        logger.error("cloudstack_test_error", error=error_msg)
        return CloudStackTestResult(
            connected=False,
            api_url=str(config.api_url),
            error_message=error_msg,
        )


@router.post(
    "/cloudstack/zones",
    response_model=CloudStackZonesList,
    summary="List CloudStack zones",
    description="List available zones from a CloudStack API"
)
def list_cloudstack_zones(config: CloudStackConfig):
    """
    List available zones from CloudStack.
    
    Args:
        config: CloudStack configuration
        
    Returns:
        List of available zones
    """
    try:
        logger.info("cloudstack_zones_list_start", api_url=str(config.api_url))
        
        provider = get_provider(
            ProviderType.CLOUDSTACK,
            credentials={
                "api_url": str(config.api_url),
                "api_key": config.api_key,
                "secret_key": config.secret_key,
            },
        )
        
        zones_data = provider.list_regions()
        zones = [CloudStackZone(id=z["id"], name=z["name"]) for z in zones_data]
        
        logger.info("cloudstack_zones_list_success", count=len(zones))
        
        return CloudStackZonesList(total=len(zones), zones=zones)
        
    except Exception as e:
        logger.error("cloudstack_zones_list_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to list CloudStack zones: {str(e)}",
        )


# ============================================================================
# Generic Provider Configuration Testing
# ============================================================================

@router.post(
    "/test",
    response_model=ProviderTestResult,
    summary="Test any cloud provider configuration",
    description="Test connectivity to any supported cloud provider"
)
def test_provider_config(config: ProviderConfigTest):
    """
    Test connection to any cloud provider.
    
    Generic endpoint for testing any provider configuration.
    
    Args:
        config: Provider type and configuration dictionary
        
    Returns:
        ProviderTestResult with connection status
    """
    try:
        provider_type_str = config.provider_type.upper()
        
        # Map string to ProviderType enum
        provider_type_map = {
            "CLOUDSTACK": ProviderType.CLOUDSTACK,
            "AWS": ProviderType.AWS,
            "GCP": ProviderType.GCP,
            "AZURE": ProviderType.AZURE,
            "OCI": ProviderType.OCI,
        }
        
        if provider_type_str not in provider_type_map:
            raise ValueError(f"Unsupported provider type: {provider_type_str}")
        
        provider_type = provider_type_map[provider_type_str]
        
        logger.info(
            "provider_test_start",
            provider_type=provider_type_str,
        )
        
        # Create provider instance
        provider = get_provider(provider_type, credentials=config.config)
        
        # Test connection
        connected = provider.test_connection()
        
        timestamp = datetime.utcnow().isoformat() + "Z"
        message = "Connection successful" if connected else "Connection failed"
        
        logger.info(
            "provider_test_result",
            provider_type=provider_type_str,
            connected=connected,
        )
        
        return ProviderTestResult(
            provider_type=provider_type_str,
            connected=connected,
            timestamp=timestamp,
            message=message,
        )
        
    except Exception as e:
        error_msg = str(e)
        logger.error("provider_test_error", error=error_msg)
        
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        return ProviderTestResult(
            provider_type=config.provider_type.upper(),
            connected=False,
            timestamp=timestamp,
            message=f"Configuration test failed",
            details={"error": error_msg},
        )
