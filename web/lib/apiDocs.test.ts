import { describe, expect, it } from "vitest";
import { buildCurl, flattenSchema, listEndpoints, typeLabel } from "./apiDocs";

const BASE = "https://api.example";
const endpoints = listEndpoints(BASE);

describe("the published surface", () => {
  it("documents exactly the eighteen published endpoints, no more and no fewer", () => {
    // Pinned as an exact list, not just a count: the API defines 20
    // routes and hides 2 (api/tests/test_openapi_schema.py asserts which).
    // If a route is added, removed or un-hidden, this fails rather than
    // the page quietly growing or shrinking.
    expect(endpoints.map((e) => `${e.method.toUpperCase()} ${e.path}`).sort()).toEqual([
      "GET /alerts",
      "GET /brands",
      "GET /demo-batches",
      "GET /documents/{doc_id}/facts",
      "GET /documents/{doc_id}/file",
      "GET /evaluation",
      "GET /health",
      "GET /portfolio/{brand_id}",
      "GET /processors",
      "GET /processors/{processor_id}",
      "GET /processors/{processor_id}/documents",
      "GET /processors/{processor_id}/memo",
      "GET /processors/{processor_id}/reasoning",
      "GET /processors/{processor_id}/site",
      "GET /runs/{run_id}",
      "GET /site-images/{processor_id}",
      "GET /stats",
      "POST /demo/certificate-batch",
    ]);
    expect(endpoints.length).toBe(18);
    for (const endpoint of endpoints) {
      expect(endpoint.summary, endpoint.path).not.toBe("");
      expect(endpoint.description, endpoint.path).not.toBe("");
      expect(endpoint.curl, endpoint.path).toContain(BASE);
    }
  });

  it("never lists the operator-only endpoints", () => {
    const paths = endpoints.map((e) => e.path);
    expect(paths).not.toContain("/admin/reset-demo");
    expect(paths).not.toContain("/events/certificate-batch");
    for (const endpoint of endpoints) {
      expect(endpoint.curl).not.toContain("reset-demo");
      expect(endpoint.curl).not.toContain("events/certificate-batch");
    }
  });

  it("leaks no token, internal note or taxonomy code into a description", () => {
    const CODE = /\b[FH][1-9]\b/;
    for (const endpoint of endpoints) {
      expect(endpoint.description, endpoint.path).not.toMatch(CODE);
      expect(endpoint.summary, endpoint.path).not.toMatch(CODE);
      for (const fragment of ["token", "docs/", "app/", "scripts/", ".py"]) {
        expect(endpoint.description.toLowerCase(), endpoint.path).not.toContain(fragment);
      }
    }
  });
});

describe("examples", () => {
  it("substitutes real path values so an example can be pasted and run", () => {
    const processor = endpoints.find((e) => e.path === "/processors/{processor_id}")!;
    expect(processor.curl).toBe(`curl -s "${BASE}/processors/PWP-01"`);
    expect(processor.curl).not.toContain("{");
  });

  it("uses the one allow-listed batch for the run endpoint, and nothing else", () => {
    const run = endpoints.find((e) => e.path === "/demo/certificate-batch")!;
    expect(run.method).toBe("post");
    expect(run.curl).toContain("-X POST");
    expect(run.curl).toContain('{"batch_id":"BATCH-PWP-03-001"}');
    expect(run.requestFields.map((f) => f.name)).toContain("batch_id");
    expect(run.responseStatus).toBe("202");
  });

  it("states the run endpoint's limits, read from the schema not retyped", () => {
    const run = endpoints.find((e) => e.path === "/demo/certificate-batch")!;
    expect(run.description).toContain("60-second cooldown");
    expect(run.description).toContain("no more than 10 runs");
  });

  it("falls back to a placeholder where no realistic value is known", () => {
    const runStatus = endpoints.find((e) => e.path === "/runs/{run_id}")!;
    expect(runStatus.curl).toContain("<run_id>");
  });

  it("builds a bodyless POST without a -d flag", () => {
    expect(buildCurl("post", "/thing", [], BASE)).toBe(`curl -s -X POST "${BASE}/thing"`);
  });
});

describe("schema rendering", () => {
  it("marks a streamed file as bytes rather than inventing JSON fields", () => {
    const file = endpoints.find((e) => e.path === "/documents/{doc_id}/file")!;
    expect(file.streamsBytes).toBe(true);
    expect(file.responseFields).toEqual([]);
  });

  it("claims a byte response for exactly the two endpoints that stream one", () => {
    // streamsBytes is derived from "no declared JSON schema", which today
    // means precisely the two file endpoints. If a third endpoint ever
    // loses its schema this fails, so nobody ships a page telling a
    // reader that JSON is a file.
    expect(endpoints.filter((e) => e.streamsBytes).map((e) => e.path).sort()).toEqual([
      "/documents/{doc_id}/file",
      "/site-images/{processor_id}",
    ]);
  });

  it("renders no field table for a free-form object rather than a wrong one", () => {
    const health = endpoints.find((e) => e.path === "/health")!;
    expect(health.streamsBytes).toBe(false);
    expect(health.responseFields).toEqual([]);
  });

  it("resolves a $ref to its schema name and expands its fields", () => {
    const evaluation = endpoints.find((e) => e.path === "/evaluation")!;
    expect(evaluation.responseSchemaName).toBe("EvaluationResponse");
    const names = evaluation.responseFields.map((f) => f.name);
    expect(names).toContain("heldout");
    expect(names).toContain("available");
    // One level into the array's items, so a reader sees the row shape.
    expect(names).toContain("numerator");
  });

  it("reads Optional as a nullable type rather than a bare anyOf", () => {
    expect(typeLabel({ anyOf: [{ type: "string" }, { type: "null" }] })).toBe("string or null");
    expect(typeLabel({ type: "array", items: { type: "integer" } })).toBe("integer[]");
    expect(typeLabel({ $ref: "#/components/schemas/Meta" })).toBe("Meta");
  });

  it("terminates instead of recursing forever on a self-referencing schema", () => {
    const rows = flattenSchema({
      properties: { child: { $ref: "#/components/schemas/EvaluationResponse" } },
    });
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.length).toBeLessThan(200);
  });

  it("indents a nested field rather than flattening it ambiguously", () => {
    const evaluation = endpoints.find((e) => e.path === "/evaluation")!;
    expect(evaluation.responseFields.some((f) => f.depth > 0)).toBe(true);
  });
});
