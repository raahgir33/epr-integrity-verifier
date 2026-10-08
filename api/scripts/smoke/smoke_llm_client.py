"""Smoke test: one real call through app/llm.py's GeminiClient (not a raw
genai.Client, unlike scripts/smoke/smoke_gemini.py), to confirm the AFC
deprecation warning is actually gone from OUR code path.

T2's smoke_gemini.py showed the warning on a structured-extraction call
("Direct use of automatic function calling (AFC) in Models.generate_content
is not recommended...") — but it talks to the SDK directly, so it never
exercised GeminiClient.extract()'s own config, which previously omitted
automatic_function_calling entirely (the actual cause, confirmed by
reading google-genai's source: should_disable_afc() defaults to enabling
the legacy AFC loop whenever that field isn't set at all, tools or not).
This script calls the real GeminiClient.extract() once and prints a PASS/
FAIL based on whether that specific warning text appears in the log
output — not just "did the call succeed."

Run by the developer — never by the agent (hits real Vertex AI).
Run: uv run python scripts/smoke/smoke_llm_client.py
"""

import io
import logging
import sys

from pydantic import BaseModel

from app.llm import GeminiClient
from scripts.smoke.smoke_gemini import build_minimal_pdf

_AFC_WARNING_TEXT = "Direct use of automatic function calling"


class SmokeInvoiceFacts(BaseModel):
    invoice_no: str
    quantity: str


def main() -> int:
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.WARNING)

    pdf_bytes = build_minimal_pdf(["Invoice No: SMOKE-LLM-CLIENT-001", "Quantity: 1.00 t"])
    client = GeminiClient()
    try:
        facts = client.extract(
            pdf_bytes,
            "application/pdf",
            "Extract the invoice number and quantity exactly as printed.",
            SmokeInvoiceFacts,
            purpose="smoke_llm_client",
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: GeminiClient.extract() raised {exc!r}")
        return 1
    finally:
        logging.getLogger().removeHandler(handler)

    print(f"extracted: {facts!r}")

    captured = log_capture.getvalue()
    if _AFC_WARNING_TEXT in captured:
        print("FAIL: AFC deprecation warning still present:")
        print(captured)
        return 1

    print("PASS: no AFC deprecation warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
