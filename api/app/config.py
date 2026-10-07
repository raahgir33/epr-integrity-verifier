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

    # Per-request HTTP timeout for agent calls (app/llm.py's
    # generate_structured/run_tool_loop) — milliseconds. Derived
    # 2026-10-08 from the fifth-canary acceptance run's own llm_calls:
    # PWP-08 hit two consecutive agent_critic_tools failures at ~118.4s
    # each (HTTP 504), confirmed via google-genai's _api_client.py
    # (populate_server_timeout_header) to be the SERVER enforcing OUR OWN
    # configured timeout, forwarded as the X-Server-Timeout header — not
    # a client-side stall. Every call that actually completed in that run
    # finished well under 25s (max 36.8s, agent_hypothesis; next-slowest
    # purpose maxed at 24.4s) — so a ~118s stall is an outlier, not a
    # request that genuinely needs more time. Decided to fail fast and
    # retry instead of waiting longer: 60_000 (~2.4x the observed normal
    # max of ~25s) cuts a stall short quickly, and app/llm.py's
    # _AGENT_MAX_ATTEMPTS (3 total attempts, retrying this fast) lets a
    # fresh attempt (observed: succeeds in ~4s) run again well within
    # AGENT_TIMEOUT_S (app/checks/params.py, raised to 300s alongside this).
    # Env-overridable; tighten with a real llm_calls query (exact SQL in
    # docs/PROGRESS.md) once more history exists.
    agent_request_timeout_ms: int = 60_000

    # Per-request HTTP timeout for extract() (app/ingest/extract.py) —
    # milliseconds. No local extraction-latency history was available
    # when this was set (2026-10-08, before the full ~714-document
    # extraction run) — the agent never runs live GCP calls, so this was
    # not measured directly. Set to the explicit floor requested (120_000)
    # rather than guessed; raise to 2x the observed max extraction
    # latency from llm_calls, whichever is larger, once that data exists.
    extract_request_timeout_ms: int = 120_000


settings = Settings()
