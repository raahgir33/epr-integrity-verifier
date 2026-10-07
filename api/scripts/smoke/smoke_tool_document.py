"""Smoke test: can a document's bytes be attached to a Critic tool-loop
turn, and does the model actually read them?

docs/PROGRESS.md's T10 plan: before writing app/agents/tools.py's
read_document body, confirm whether a document Part can live in the same
turn as its function_response (one Content, two Parts) — if the model
correctly answers a question only the embedded document's printed text
would reveal, that's confirmed. Either way, app/llm.py's run_tool_loop
already uses the safer fallback (the document as a SEPARATE user-role
Content immediately after the function_response) regardless of this
test's result — see run_tool_loop's docstring. This script only answers
the open question; it does not gate anything already built.

Run by the developer — never by the agent (hits real Vertex AI).
Run: uv run python scripts/smoke/smoke_tool_document.py
"""

import sys

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.config import settings

_SECRET_INVOICE_NO = "SMOKE-DOC-TOOL-001"


class _Answer(BaseModel):
    invoice_no: str


def _build_minimal_pdf(lines: list[str]) -> bytes:
    """Same hand-built single-page PDF approach as smoke_gemini.py — no
    PDF library dependency needed for a smoke test."""

    def esc(s: str) -> str:
        return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    content_lines = ["BT", "/F1 12 Tf", "72 720 Td"]
    for i, line in enumerate(lines):
        if i > 0:
            content_lines.append("0 -18 Td")
        content_lines.append(f"({esc(line)}) Tj")
    content_lines.append("ET")
    content_stream = "\n".join(content_lines).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length "
        + str(len(content_stream)).encode()
        + b" >>\nstream\n"
        + content_stream
        + b"\nendstream",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode()
        out += body
        out += b"\nendobj\n"

    xref_offset = len(out)
    n = len(objects) + 1
    out += f"xref\n0 {n}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode()
    return bytes(out)


def _fetch_document_path(doc_id: str) -> str:
    """Trivial tool: returns a gs:// path for a document. This smoke test
    never actually calls GCS — it hands the model the real bytes locally
    once this tool is "called", standing in for the GCS fetch that
    app/agents/tools.py's real read_document does.

    Args:
        doc_id: The document identifier to fetch, e.g. "DOC-1".
    """
    return f"gs://smoke-test-bucket/{doc_id}.pdf"


def run_smoke_test() -> bool:
    client = genai.Client(
        vertexai=True, project=settings.gcp_project, location=settings.vertex_location
    )
    pdf_bytes = _build_minimal_pdf(["SYNTHETIC - DEMO DATA", f"Invoice No: {_SECRET_INVOICE_NO}"])
    question = (
        "Call the tool to fetch the document's path for doc_id 'DOC-1', then read the "
        "document content you are given and report the exact invoice number printed on it."
    )
    config = types.GenerateContentConfig(
        tools=[_fetch_document_path],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(mode="AUTO")
        ),
        temperature=0.2,
    )

    print("--- smoke_tool_document: forcing the tool call ---")
    response = client.models.generate_content(
        model=settings.gemini_model, contents=question, config=config
    )
    model_turn = response.candidates[0].content
    function_call = next(
        (part.function_call for part in (model_turn.parts or []) if part.function_call), None
    )
    if function_call is None:
        print("FAIL: model did not call the tool")
        return False
    print(f"call: {function_call.name}({dict(function_call.args)})")
    gcs_path = _fetch_document_path(**function_call.args)

    print(
        "--- smoke_tool_document: attaching the document bytes in the SAME turn as the "
        "function_response (one Content, two Parts) ---"
    )
    follow_up = client.models.generate_content(
        model=settings.gemini_model,
        contents=[
            types.Content(role="user", parts=[types.Part.from_text(text=question)]),
            model_turn,
            types.Content(
                role="user",
                parts=[
                    types.Part.from_function_response(
                        name=function_call.name, response={"result": gcs_path}
                    ),
                    types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                ],
            ),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=_Answer, temperature=0.2
        ),
    )
    try:
        answer = _Answer.model_validate_json(follow_up.text)
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: could not parse a structured answer: {exc!r}")
        print(f"raw response: {follow_up.text!r}")
        return False

    print(f"model's reported invoice_no: {answer.invoice_no!r}")
    if answer.invoice_no != _SECRET_INVOICE_NO:
        print(
            f"FAIL: model did not read the attached document correctly "
            f"(expected {_SECRET_INVOICE_NO!r})"
        )
        return False

    print("PASS: a document Part in the same turn as its function_response is read correctly.")
    print(
        "This confirms the combined-turn approach works; app/llm.py's run_tool_loop already "
        "uses the safer two-separate-Content fallback regardless — this result does not require "
        "a code change, it only answers the open question from docs/PROGRESS.md's T10 plan."
    )
    return True


def main() -> int:
    try:
        passed = run_smoke_test()
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: smoke test raised {exc!r}")
        passed = False
    print("smoke_tool_document: ALL PASS" if passed else "smoke_tool_document: FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
