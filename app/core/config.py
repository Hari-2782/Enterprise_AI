from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_env: str = "development"

    database_url: str

    azure_search_endpoint: str | None = None
    azure_search_api_key: SecretStr | None = None
    azure_search_index_name: str = "enterprise-knowledge"

    model_provider: str = "ollama"
    model_name: str = "qwen2.5:3b"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

settings = Settings()
