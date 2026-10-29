from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, model_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "production"
    bot_token: SecretStr
    database_url: str
    bootstrap_admin_id: int = 0
    bootstrap_admin_name: str = "Начальник"
    bootstrap_manager_id: int = 0
    bootstrap_manager_name: str = "Менеджер"
    openai_api_key: SecretStr = SecretStr("")
    openai_text_model: str = ""
    openai_transcribe_model: str = ""
    storage_backend: str = "s3"
    local_storage_path: str = "private/objects"
    s3_endpoint_url: str | None = None
    s3_bucket: str = ""
    aws_default_region: str = "auto"
    soffice_path: str = "soffice"
    ffmpeg_path: str = "ffmpeg"
    max_voice_seconds: int = 180
    max_file_bytes: int = 10 * 1024 * 1024
    timezone: str = "Europe/Moscow"

    @model_validator(mode="after")
    def validate_runtime(self):
        if self.database_url.startswith("postgres://"):
            self.database_url = self.database_url.replace("postgres://", "postgresql+psycopg://", 1)
        elif self.database_url.startswith("postgresql://"):
            self.database_url = self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        if self.storage_backend not in {"s3", "local"}:
            raise ValueError("STORAGE_BACKEND: s3 or local")
        if self.app_env == "production":
            if not self.database_url.startswith("postgresql+psycopg://"):
                raise ValueError("Production requires PostgreSQL")
            if self.storage_backend != "s3" or not self.s3_bucket:
                raise ValueError("Production requires a private S3 bucket")
        return self
