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

    # T13.8 hardening: comma-separated list of origins the browser is
    # allowed to make cross-origin requests from (app/main.py's
    # CORSMiddleware). No wildcard — an explicit allow-list only. Default
    # covers local web dev; deploy_api.sh sets the real production origin.
    cors_allowed_origins: str = "http://localhost:3000"

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    # T17: the demo batches POST /demo/certificate-batch will actually
    # run, comma-separated. Not a threshold, so not in
    # app/checks/params.py — a deployment-time demo setting, which is
    # what this file is for, and env-overridable so the enabled batch can
    # change without a code change.
    #
    # Only BATCH-PWP-01-001 and BATCH-PWP-03-001 are safe to run at all:
    # the other eight have period_month 2026-04, which starts a new
    # financial year, so certified_t_fy_to_date counts the new
    # certificate and nothing else and the processor's certified tonnes
    # collapse to the batch quantity (PWP-02: 136.05 t -> 1.92 t, band
    # Medium -> Low) while its chart still shows the full history. They
    # also carry no extra_document_ids, so there is nothing to extract.
    # BATCH-PWP-03-001 is the one with the planted handwritten Hindi
    # remark, so it is the only one enabled by default.
    demo_enabled_batch_ids: str = "BATCH-PWP-03-001"

    @property
    def demo_enabled_batch_ids_list(self) -> list[str]:
        return [b.strip() for b in self.demo_enabled_batch_ids.split(",") if b.strip()]

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

    # T11 (API): the API serves exactly one (seed, facts_source) — never
    # mixed in a response (docs/BUILD_PLAN.md). facts_source switches to
    # "extracted" once the full 496-document extraction run has happened.
    default_seed: int = 42
    default_facts_source: str = "truth"
    # Not actually used by any key app/store/cache.py's preload() fills —
    # those all pass ttl=cache.NO_EXPIRY (A2, docs/PROGRESS.md), since a
    # short wall-clock TTL was undermining "preload once, stay warm" (any
    # read made more than this many seconds after startup re-triggered a
    # live BigQuery query). Left as the get_or_load() default for any
    # future lazy (non-preloaded) key — none exist today — and reserved
    # for T13, which may want real TTL-based staleness once live writes
    # exist; invalidate() is the correct trigger for everything preloaded.
    cache_ttl_seconds: int = 60


settings = Settings()
