from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "anywhere2opus"
    app_env: str = "development"
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Database
    database_url: str = "postgresql+psycopg2://anywhere2opus:anywhere2opus@localhost:5432/anywhere2opus"
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "anywhere2opus"
    db_user: str = "anywhere2opus"
    db_password: str = "anywhere2opus"

    # Security
    secret_key: str = "change-me-in-production-at-least-32-characters-long"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # AWS
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_default_region: str = "us-east-1"
    aws_session_token: Optional[str] = None

    # GCP
    gcp_project_id: Optional[str] = None
    gcp_service_account_key_file: Optional[str] = None
    gcp_service_account_key_json: Optional[str] = None

    # Azure
    azure_subscription_id: Optional[str] = None
    azure_tenant_id: Optional[str] = None
    azure_client_id: Optional[str] = None
    azure_client_secret: Optional[str] = None

    # OCI
    oci_user_ocid: Optional[str] = None
    oci_fingerprint: Optional[str] = None
    oci_tenancy_ocid: Optional[str] = None
    oci_region: str = "us-ashburn-1"
    oci_private_key_file: Optional[str] = None
    oci_private_key_content: Optional[str] = None

    # Opus
    opus_url: Optional[str] = None
    opus_api_key: Optional[str] = None
    opus_secret_key: Optional[str] = None
    opus_zone_id: Optional[str] = None


settings = Settings()
