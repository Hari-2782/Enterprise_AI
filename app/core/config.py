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
    model_provider: str = "ollama"
    model_name: str = "qwen2.5:3b"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
