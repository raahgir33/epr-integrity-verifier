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

    # Per-purpose HTTP timeouts for agent calls (app/llm.py's
    # generate_structured/run_tool_loop) — milliseconds. Split per purpose
    # 2026-10-08 from the full acceptance run's own llm_calls (201 calls,
    # both runs combined; docs/PROGRESS.md):
    #
    #   purpose             n    p50 (ms)  p95 (ms)  max (ms)
    #   agent_hypothesis    22   25,098    57,483    60,027
    #   agent_critic_tools  158  1,371     8,746     58,286
    #   agent_critic_final  20   4,841     8,655     10,092
    #   agent_revision      1    4,770     4,770     4,770
    #
    # agent_hypothesis has by far the widest spread (p95 57.5s, close to
    # the old shared 60s timeout) — given generous headroom so a genuine
    # slow-but-fine call doesn't get cut off. The other three purposes are
    # tightly clustered well under 10s even at p95 — given a tighter 30s
    # floor instead, so a genuine stall (the ~118s-class backend stall
    # diagnosed on agent_critic_tools in the fifth canary, before this
    # split existed) is cut short faster, not slower. Each value is a
    # multiple of that purpose's own observed p95, not one shared number.
    # Still fail-fast-and-retry (app/llm.py's _AGENT_MAX_ATTEMPTS=3) within
    # the unchanged 300s run deadline (app/checks/params.py's
    # AGENT_TIMEOUT_S). Env-overridable; tighten further once more history
    # exists (same llm_calls query as before, in docs/PROGRESS.md).
    agent_hypothesis_timeout_ms: int = 120_000  # ~2.1x observed p95 (57.5s)
    agent_critic_tools_timeout_ms: int = 30_000  # ~3.4x observed p95 (8.7s)
    agent_critic_final_timeout_ms: int = 30_000  # ~3.5x observed p95 (8.7s)
    agent_revision_timeout_ms: int = 30_000  # only 1 sample (4.8s); same floor

    # Per-request HTTP timeout for extract() (app/ingest/extract.py) —
    # milliseconds. No local extraction-latency history was available
    # when this was set (2026-10-08, before the full ~714-document
    # extraction run) — the agent never runs live GCP calls, so this was
    # not measured directly. Set to the explicit floor requested (120_000)
    # rather than guessed; raise to 2x the observed max extraction
    # latency from llm_calls, whichever is larger, once that data exists.
    extract_request_timeout_ms: int = 120_000


settings = Settings()
