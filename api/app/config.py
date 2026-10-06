from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gcp_project: str | None = None
    vertex_location: str = "asia-south1"
    gemini_model: str = "gemini-3.5-flash"

    bq_dataset: str = "epr"

    dossier_bucket: str | None = None
    artifact_bucket: str | None = None

    pubsub_topic: str = "certificate-batches"
    push_token: str | None = None


settings = Settings()
