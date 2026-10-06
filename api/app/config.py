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

    # Gemini pricing, USD per million tokens — developer-provided rate,
    # 2026-10-07, for scripts/cost_report.py. Not a regulatory threshold;
    # update if Vertex AI pricing changes. Thinking tokens are billed as
    # output tokens.
    gemini_input_price_per_million: float = 1.50
    gemini_output_price_per_million: float = 9.00


settings = Settings()
