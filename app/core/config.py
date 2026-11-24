from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_env: str = "development"

    DATABASE_URL: str
    upload_dir: str = "data/uploads"
    max_upload_bytes: int = 25 * 1024 * 1024

    azure_search_endpoint: str | None = None
    azure_search_api_key: SecretStr | None = None
    azure_search_index_name: str = "enterprise-knowledge"

    model_provider: str = "openrouter"
    model_name: str = "baidu/ernie-5.5-flash-preview:free"

    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "baidu/ernie-5.5-flash-preview:free"
    openrouter_fallback_model: str | None = "nvidia/nemotron-3-ultra-550b-a55b:free"
    openrouter_timeout: float = 30.0
    openrouter_max_retries: int = 2
    openrouter_max_tokens: int = 2048

    auth_secret_key: SecretStr = SecretStr("dev-only-insecure-secret-change-in-prod")
    auth_token_ttl_minutes: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
