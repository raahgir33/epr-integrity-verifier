"""Smoke test: Gemini on Vertex AI — inline-bytes structured extraction, and tool use.

Confirms the model and region work from this machine before any feature work starts.
Run: uv run python scripts/smoke/smoke_gemini.py
"""

import sys

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.config import settings


class SmokeInvoiceFacts(BaseModel):
    invoice_no: str
    quantity: str


def build_minimal_pdf(lines: list[str]) -> bytes:
    """Hand-build a tiny one-page PDF with the given text lines, no library needed."""

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


def lookup_capacity(processor_id: str) -> str:
    """Look up the consented processing capacity for a plastic waste processor, in tonnes per year.

    Args:
        processor_id: The processor identifier, e.g. "PWP-01".
    """
    return "4200 t/yr"


def check_structured_extraction(client: genai.Client) -> bool:
    print("--- smoke_gemini: structured extraction from inline PDF bytes ---")
    pdf_bytes = build_minimal_pdf(
        [
            "SYNTHETIC - DEMO DATA",
            "Invoice No: SMOKE-TEST-001",
            "Quantity: 10.50 t",
        ]
    )
    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                "Extract the invoice number and quantity exactly as printed.",
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SmokeInvoiceFacts,
                temperature=0,
            ),
        )
        facts = SmokeInvoiceFacts.model_validate_json(response.text)
        print(f"extracted: {facts!r}")
        if facts.invoice_no != "SMOKE-TEST-001":
            print(f"FAIL: expected invoice_no 'SMOKE-TEST-001', got {facts.invoice_no!r}")
            return False
        print("PASS: structured extraction")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: structured extraction raised {exc!r}")
        return False


def check_function_calling(client: genai.Client) -> bool:
    """Manual two-step tool-call round trip: generate_content's automatic function
    calling is not reliable (the SDK itself warns against it), and the agent design
    needs the tool-call step separate from the final answer anyway."""
    print("--- smoke_gemini: function calling with a trivial tool ---")
    try:
        question = "What is the consented capacity for processor PWP-01?"
        config = types.GenerateContentConfig(
            tools=[lookup_capacity],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="ANY")
            ),
            temperature=0.2,
        )
        response = client.models.generate_content(
            model=settings.gemini_model, contents=question, config=config
        )

        model_turn = response.candidates[0].content
        function_call = next(
            (part.function_call for part in (model_turn.parts or []) if part.function_call),
            None,
        )
        print(f"tool called: {function_call is not None}")
        if function_call is None:
            print("FAIL: model did not call the tool")
            return False
        print(f"call: {function_call.name}({dict(function_call.args)})")

        result = lookup_capacity(**function_call.args)
        follow_up = client.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Content(role="user", parts=[types.Part.from_text(text=question)]),
                model_turn,
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_function_response(
                            name=function_call.name, response={"result": result}
                        )
                    ],
                ),
            ],
            config=types.GenerateContentConfig(temperature=0.2),
        )
        print(f"final answer: {follow_up.text!r}")
        if not follow_up.text:
            print("FAIL: no final answer after returning the function result")
            return False
        print("PASS: function calling")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: function calling raised {exc!r}")
        return False


def main() -> int:
    client = genai.Client(
        vertexai=True, project=settings.gcp_project, location=settings.vertex_location
    )
    results = [check_structured_extraction(client), check_function_calling(client)]
    if all(results):
        print("smoke_gemini: ALL PASS")
        return 0
    print("smoke_gemini: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
