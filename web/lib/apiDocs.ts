import rawSchema from "@/lib/openapi.json";

/** The published API reference, built at render time from the committed
 * OpenAPI schema — the same file `npm run gen:types` generates the client
 * types from, so the page cannot drift from the service.
 *
 * The schema lives in web/ rather than being imported from ../api/
 * because web/Dockerfile builds with `COPY . .` from web/ alone: a
 * cross-package import compiles locally and fails the Cloud Run build.
 * api/scripts/export_openapi.py writes both copies and a pytest fails if
 * they differ.
 *
 * Nothing here filters endpoints. The two operator-only endpoints are
 * absent because the service no longer publishes them
 * (include_in_schema=False), so this page documents exactly what the API
 * actually exposes. */

type Json = Record<string, unknown>;

const schema = rawSchema as unknown as {
  paths: Record<string, Record<string, Json>>;
  components?: { schemas?: Record<string, Json> };
};

const SCHEMAS: Record<string, Json> = schema.components?.schemas ?? {};

/** How deep a nested object is expanded before the reader is pointed at
 * the schema name instead. Two levels covers every response this API
 * returns without turning a 40-schema document into a wall. */
const MAX_DEPTH = 2;

export type FieldRow = {
  name: string;
  type: string;
  required: boolean;
  description?: string;
  depth: number;
};

export type Param = {
  name: string;
  location: string;
  type: string;
  required: boolean;
  description?: string;
};

export type Endpoint = {
  id: string;
  method: string;
  path: string;
  summary: string;
  description: string;
  params: Param[];
  requestSchemaName: string | null;
  requestFields: FieldRow[];
  responseStatus: string;
  responseSchemaName: string | null;
  responseFields: FieldRow[];
  /** True when the success response is not JSON — a streamed file. */
  streamsBytes: boolean;
  curl: string;
};

function refName(node: Json): string | null {
  const ref = node["$ref"];
  return typeof ref === "string" ? ref.replace("#/components/schemas/", "") : null;
}

function deref(node: Json): Json {
  const name = refName(node);
  return name && SCHEMAS[name] ? SCHEMAS[name] : node;
}

/** The non-null branch of an Optional, plus whether null was allowed.
 * FastAPI emits `anyOf: [X, {type: "null"}]` for every `| None` field. */
function unwrapNullable(node: Json): { node: Json; nullable: boolean } {
  const anyOf = node["anyOf"];
  if (!Array.isArray(anyOf)) return { node, nullable: false };
  const branches = anyOf as Json[];
  const nonNull = branches.filter((b) => b["type"] !== "null");
  const nullable = branches.length !== nonNull.length;
  if (nonNull.length === 1) return { node: nonNull[0], nullable };
  return { node, nullable };
}

export function typeLabel(input: Json): string {
  const { node, nullable } = unwrapNullable(input);
  const suffix = nullable ? " or null" : "";

  const name = refName(node);
  if (name) return name + suffix;

  const anyOf = node["anyOf"];
  if (Array.isArray(anyOf)) {
    return (anyOf as Json[]).map((b) => typeLabel(b)).join(" or ") + suffix;
  }

  const enumValues = node["enum"];
  if (Array.isArray(enumValues)) {
    return `one of ${enumValues.map((v) => JSON.stringify(v)).join(", ")}` + suffix;
  }

  const type = node["type"];
  if (type === "array") {
    const items = (node["items"] as Json) ?? {};
    return `${typeLabel(items)}[]` + suffix;
  }
  if (typeof type === "string") return type + suffix;
  return "object" + suffix;
}

/** Flattens a schema into readable rows, following $refs and expanding
 * nested objects to MAX_DEPTH. Self-referencing schemas terminate at the
 * repeated name rather than recursing. */
export function flattenSchema(input: Json, depth = 0, seen: string[] = []): FieldRow[] {
  const { node } = unwrapNullable(input);
  const name = refName(node);
  if (name && seen.includes(name)) return [];
  const resolved = deref(node);

  const properties = resolved["properties"] as Record<string, Json> | undefined;
  if (!properties) return [];
  const required = new Set((resolved["required"] as string[] | undefined) ?? []);
  const nextSeen = name ? [...seen, name] : seen;

  const rows: FieldRow[] = [];
  for (const [field, rawValue] of Object.entries(properties)) {
    const value = rawValue;
    rows.push({
      name: field,
      type: typeLabel(value),
      required: required.has(field),
      description: typeof value["description"] === "string" ? value["description"] : undefined,
      depth,
    });

    if (depth >= MAX_DEPTH - 1) continue;

    // Expand one level into a nested object, or into an array's items.
    const { node: inner } = unwrapNullable(value);
    const arrayItems = inner["type"] === "array" ? ((inner["items"] as Json) ?? {}) : null;
    const target = arrayItems ?? inner;
    if (refName(target) || target["properties"]) {
      rows.push(...flattenSchema(target, depth + 1, nextSeen));
    }
  }
  return rows;
}

/** Realistic path values, so an example can be pasted and run. Taken from
 * the served synthetic dataset; a parameter with no known sample keeps an
 * angle-bracket placeholder rather than an invented value. */
const SAMPLE_PATH_VALUES: Record<string, string> = {
  processor_id: "PWP-01",
  brand_id: "BRAND-01",
  doc_id: "PWP-01-DEMO-INBOUND_INVOICE-001",
};

function samplePath(path: string): string {
  return path.replace(/\{(\w+)\}/g, (_, name: string) => SAMPLE_PATH_VALUES[name] ?? `<${name}>`);
}

function sampleBody(fields: FieldRow[]): string | null {
  if (fields.length === 0) return null;
  const body: Record<string, string> = {};
  for (const field of fields.filter((f) => f.depth === 0)) {
    // The demo endpoint takes the one allow-listed batch; anything else
    // is rejected by the server, so no other value would be a useful
    // example.
    body[field.name] = field.name === "batch_id" ? "BATCH-PWP-03-001" : `<${field.name}>`;
  }
  return JSON.stringify(body);
}

export function buildCurl(
  method: string,
  path: string,
  requestFields: FieldRow[],
  baseUrl: string
): string {
  const url = `${baseUrl}${samplePath(path)}`;
  if (method === "get") return `curl -s "${url}"`;
  const body = sampleBody(requestFields);
  if (!body) return `curl -s -X ${method.toUpperCase()} "${url}"`;
  return `curl -s -X ${method.toUpperCase()} "${url}" \\\n  -H "Content-Type: application/json" \\\n  -d '${body}'`;
}

function jsonSchemaOf(container: Json | undefined): Json | null {
  const content = container?.["content"] as Record<string, Json> | undefined;
  const entry = content?.["application/json"];
  const inner = entry?.["schema"] as Json | undefined;
  if (!inner || Object.keys(inner).length === 0) return null;
  return inner;
}

export function listEndpoints(baseUrl: string): Endpoint[] {
  const endpoints: Endpoint[] = [];

  for (const [path, operations] of Object.entries(schema.paths)) {
    for (const [method, rawOperation] of Object.entries(operations)) {
      if (!["get", "post", "put", "patch", "delete"].includes(method)) continue;
      const operation = rawOperation;

      const params: Param[] = ((operation["parameters"] as Json[] | undefined) ?? []).map((p) => ({
        name: String(p["name"]),
        location: String(p["in"]),
        type: typeLabel((p["schema"] as Json) ?? {}),
        required: p["required"] === true,
        description: typeof p["description"] === "string" ? p["description"] : undefined,
      }));

      const requestSchema = jsonSchemaOf(operation["requestBody"] as Json | undefined);
      const requestFields = requestSchema ? flattenSchema(requestSchema) : [];

      const responses = (operation["responses"] as Record<string, Json> | undefined) ?? {};
      const responseStatus =
        Object.keys(responses).find((code) => code.startsWith("2")) ?? "200";
      const responseContainer = responses[responseStatus];
      const responseSchema = jsonSchemaOf(responseContainer);

      endpoints.push({
        id: `${method}-${path}`.replace(/[^a-zA-Z0-9]+/g, "-").replace(/-+$/, ""),
        method,
        path,
        summary: String(operation["summary"] ?? ""),
        description: String(operation["description"] ?? ""),
        params,
        requestSchemaName: requestSchema ? refName(requestSchema) : null,
        requestFields,
        responseStatus,
        responseSchemaName: responseSchema ? refName(responseSchema) : null,
        responseFields: responseSchema ? flattenSchema(responseSchema) : [],
        streamsBytes: responseSchema === null,
        curl: buildCurl(method, path, requestFields, baseUrl),
      });
    }
  }

  // Grouped by resource, so the reference reads in the order someone
  // would actually call it rather than alphabetically by path.
  const order = [
    "/health",
    "/stats",
    "/processors",
    "/processors/{processor_id}",
    "/processors/{processor_id}/documents",
    "/processors/{processor_id}/reasoning",
    "/processors/{processor_id}/memo",
    "/processors/{processor_id}/site",
    "/documents/{doc_id}/facts",
    "/documents/{doc_id}/file",
    "/site-images/{processor_id}",
    "/brands",
    "/portfolio/{brand_id}",
    "/evaluation",
    "/alerts",
    "/demo-batches",
    "/demo/certificate-batch",
    "/runs/{run_id}",
  ];
  return endpoints.sort((a, b) => {
    const ia = order.indexOf(a.path);
    const ib = order.indexOf(b.path);
    return (ia === -1 ? order.length : ia) - (ib === -1 ? order.length : ib);
  });
}
