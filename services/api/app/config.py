from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="BUSINEX_",
        extra="ignore",
    )

    environment: str = "development"
    auth_mode: str = "demo"
    database_url: str = "postgresql+asyncpg://businex_app:businex_app@localhost:5432/businex"
    migration_database_url: str = (
        "postgresql+asyncpg://businex_owner:businex_owner@localhost:5432/businex"
    )
    seed_database_url: str = (
        "postgresql+asyncpg://postgres:postgres-dev-only@localhost:5432/businex"
    )
    oidc_issuer: AnyHttpUrl = "http://localhost:8080/realms/businex"  # type: ignore[assignment]
    oidc_audience: str = "businex-api"
    oidc_jwks_url: AnyHttpUrl = (
        "http://localhost:8080/realms/businex/protocol/openid-connect/certs"  # type: ignore[assignment]
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:8443", "http://localhost:5173"]
    )
    demo_jwt_secret: str = "businex-demo-dev-only-change-me-please-32b"
    demo_password: str = "Demo@2025"
    redis_url: str = "redis://localhost:6379/0"
    ai_provider: str = "mock"
    openai_api_key: str = ""
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    gemini_api_key: str = ""
    gemini_backend: str = "api"
    gemini_project: str = ""
    gemini_location: str = "asia-south1"
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = "2024-10-21"
    gemini_model: str = "gemini-3.8-flash"
    ai_timeout_seconds: float = 30.0
    ai_max_retries: int = 2
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin-dev-only"
    public_app_url: str = "http://localhost:8443"
    public_api_url: str = "http://localhost:8000"
    payment_mode: str = "disabled"
    default_country: str = "IN"
    default_currency: str = "INR"
    trial_days_default: int = 14
    billing_grace_days: int = 7
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_webhook_id: str = ""
    paypal_sandbox: bool = True
    adyen_api_key: str = ""
    adyen_merchant_account: str = ""
    adyen_hmac_key: str = ""
    adyen_client_key: str = ""
    ip_country_lookup_url: str = ""
    tax_service_url: str = ""
    tax_service_key: str = ""
    invoice_prefix: str = "INV"


@lru_cache
def get_settings() -> Settings:
    return Settings()
