import { describe, expect, it } from "vitest";
import { resolveEvidence } from "@/lib/evidence";

const PID = "PWP-03";
const DEMO_DOCS = [
  `${PID}-DEMO-INBOUND_INVOICE-001`,
  `${PID}-DEMO-EWAY_BILL-001`,
  `${PID}-DEMO-WEIGHBRIDGE_SLIP-001`,
];
const DEMO_SHIPMENT_ID = `${PID}-DEMO-SHP-001`;

describe("resolveEvidence", () => {
  it("links a document it knows", () => {
    const resolved = resolveEvidence(`${PID}-INBOUND_INVOICE-003`, new Set([`${PID}-INBOUND_INVOICE-003`]));
    expect(resolved).toEqual({
      kind: "document",
      href: `/files/${PID}-INBOUND_INVOICE-003`,
      label: `${PID}-INBOUND_INVOICE-003`,
    });
  });

  it("sends a site thumbnail path to the Site evidence tab", () => {
    expect(resolveEvidence("seed-42/site/PWP-05.png", new Set())).toEqual({
      kind: "site",
      href: "?tab=site",
      label: "Site imagery",
    });
  });

  it("falls back to plain text for anything it cannot resolve", () => {
    expect(resolveEvidence("EPR-CERT/617488/202504", new Set())).toEqual({
      kind: "plain",
      label: "EPR-CERT/617488/202504",
    });
  });

  // T17. The demo-extra documents are the planted-remark finding's own
  // evidence, and the shipment id it cites has a new "-DEMO-SHP-" shape.
  // Nothing here pattern-matches an id — a document is a document because
  // it is in knownDocIds — so these must resolve like any other. The
  // assertions exist because that is invisible from reading the function.
  describe("the demo-extra evidence", () => {
    it("links each demo document once the processor lists it", () => {
      const known = new Set(DEMO_DOCS);
      for (const docId of DEMO_DOCS) {
        const resolved = resolveEvidence(docId, known);
        expect(resolved.kind).toBe("document");
        expect(resolved).toMatchObject({ href: `/files/${docId}`, label: docId });
      }
    });

    it("does not mistake a demo document for a site thumbnail", () => {
      // "-DEMO-" and the "_SLIP" suffix must not trip the storage-path
      // pattern, which keys off gs://, /site/ and image extensions.
      for (const docId of DEMO_DOCS) {
        expect(resolveEvidence(docId, new Set()).kind).toBe("plain");
      }
    });

    it("renders a cited shipment id as plain text, never as a link", () => {
      // A shipment id is not a document; FindingCard prints it verbatim.
      expect(resolveEvidence(DEMO_SHIPMENT_ID, new Set(DEMO_DOCS))).toEqual({
        kind: "plain",
        label: DEMO_SHIPMENT_ID,
      });
    });
  });
});
