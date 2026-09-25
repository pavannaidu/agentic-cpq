import { describe, expect, it } from "vitest";
import {
  blendedMargin,
  computeQuoteDiff,
  evidenceFromGenie,
  evidenceFromRecommendation,
  groupQuoteLines,
  historyDiff,
  lineKey,
  quoteSnapshot,
  safeExternalUrl,
  sanitizeDraftForRole,
  sanitizeRecommendationForRole,
} from "./domain";
import type { DraftLineItem, DraftOrder, Recommendation } from "./types";

function line(overrides: Partial<DraftLineItem> = {}): DraftLineItem {
  return {
    sku: "EQUIP-1",
    title: "Equipment",
    category: "Equipment",
    quantity: 1,
    unit_price: 1_000,
    ...overrides,
  };
}

describe("quote line grouping", () => {
  it("nests add-ons beneath the equipment they cover and preserves orphans", () => {
    const equipment = line();
    const attached = line({ sku: "CARE", title: "Equipment Care", is_addon: true, covers_sku: "EQUIP-1", unit_price: 120 });
    const orphan = line({ sku: "ORPHAN", title: "Unattached care", is_addon: true, covers_sku: "MISSING", unit_price: 50 });

    expect(groupQuoteLines([attached, equipment, orphan])).toEqual([
      { parent: equipment, children: [attached] },
      { parent: orphan, children: [] },
    ]);
    expect(lineKey(attached)).toBe("CARE::EQUIP-1");
  });
});

describe("quote diffs", () => {
  it("merges changed lines and adds new lines without removing untouched lines", () => {
    const current = [
      line({ quantity: 1, unit_price: 1_000 }),
      line({ sku: "KEEP", title: "Keep", unit_price: 400, approval_required: true }),
    ];
    const proposed = [
      line({ quantity: 2, unit_price: 900 }),
      line({ sku: "CARE", title: "Equipment Care", is_addon: true, covers_sku: "EQUIP-1", unit_price: 100 }),
    ];

    const diff = computeQuoteDiff(current, proposed, "add");

    expect(diff.added.map(lineKey)).toEqual(["CARE::EQUIP-1"]);
    expect(diff.removed).toEqual([]);
    expect(diff.changed).toHaveLength(1);
    expect(diff.resultLines.map(lineKey)).toEqual(["EQUIP-1", "KEEP", "CARE::EQUIP-1"]);
    expect(diff.currentTotal).toBe(1_400);
    expect(diff.proposedTotal).toBe(2_300);
    expect(diff.delta).toBe(900);
    expect(diff.proposedApproval).toBe(true);
    expect(diff.protectionTotal).toBe(100);
  });

  it("computes a replacement snapshot including removals and approval changes", () => {
    const current = [line({ approval_required: true }), line({ sku: "OLD", title: "Old", unit_price: 250 })];
    const proposed = [line({ unit_price: 800, approval_required: false })];

    const diff = historyDiff(current, proposed);

    expect(diff.removed.map((item) => item.sku)).toEqual(["OLD"]);
    expect(diff.changed).toHaveLength(1);
    expect(diff.currentApproval).toBe(true);
    expect(diff.proposedApproval).toBe(false);
    expect(diff.proposedTotal).toBe(800);
  });
});

describe("role sanitization", () => {
  const sensitiveLine = line({
    supplier_cost: 500,
    gross_margin_pct: 50,
    overpay_amount: 40,
    legacy_supplier_cost: 540,
    correct_supplier_cost: 500,
  });

  it("removes manager-only line fields for sellers without mutating the source", () => {
    const draft: DraftOrder = {
      draft_order_id: "draft-1",
      account_id: "account-1",
      status: "draft",
      line_items: [sensitiveLine],
      subtotal: 1_000,
      grand_total: 1_000,
    };

    const sanitized = sanitizeDraftForRole(draft, "seller");

    expect(sanitized).not.toBe(draft);
    expect(sanitized.line_items[0]).not.toHaveProperty("supplier_cost");
    expect(sanitized.line_items[0]).not.toHaveProperty("gross_margin_pct");
    expect(draft.line_items[0].supplier_cost).toBe(500);
    expect(sanitizeDraftForRole(draft, "manager")).toBe(draft);
  });

  it("removes manager aggregates and sensitive item fields from recommendations", () => {
    const recommendation: Recommendation = {
      summary: "Recommended",
      items: [sensitiveLine],
      manager_insights: [{ label: "Margin", status: "good" }],
      overpay_prevented_total: 40,
    };

    const sanitized = sanitizeRecommendationForRole(recommendation, "seller");

    expect(sanitized.items[0]).not.toHaveProperty("supplier_cost");
    expect(sanitized.manager_insights).toBeUndefined();
    expect(sanitized.overpay_prevented_total).toBeUndefined();
    expect(recommendation.items[0].supplier_cost).toBe(500);
  });
});

describe("evidence normalization", () => {
  it("normalizes Genie citations and prefers SQL attachment result metadata", () => {
    const evidence = evidenceFromGenie({
      source: "genie_space",
      execution_identity: "on_behalf_of",
      citations: [{ citation_id: "1", title: "Eligibility policy", uri: "https://example.test/policy", snippet: "Covered." }],
      sql: "select fallback",
      columns: ["fallback"],
      rows: [[0]],
      sql_attachments: [{ sql: "select governed", columns: ["eligible"], rows: [[true]], truncated: true }],
      checks: [{ label: "Row policy", status: "passed" }],
    });

    expect(evidence.citations[0]).toEqual({
      source: "Genie",
      title: "Eligibility policy",
      detail: "Covered.",
      url: "https://example.test/policy",
    });
    expect(evidence.sql).toBe("select governed");
    expect(evidence.rows).toEqual([[true]]);
    expect(evidence.truncated).toBe(true);
    expect(evidence.executionIdentity).toBe("on_behalf_of");
    expect(evidence.partial).toBe(false);
  });

  it("deduplicates recommendation citations and combines governed checks", () => {
    const citation = { source: "Catalog", title: "SKU", detail: "Active" };
    const recommendation: Recommendation = {
      summary: "Recommended",
      items: [line({ citations: [citation], insights: [citation] })],
      citations: [citation],
      pricing_controls: [{ label: "Floor", status: "passed" }],
      quote_readiness: [{ label: "Account", status: "passed" }],
      metadata: { tools_used: ["catalog_lookup", 42] },
    };

    const evidence = evidenceFromRecommendation(recommendation, "service_principal");

    expect(evidence.citations).toEqual([citation]);
    expect(evidence.checks.map((check) => check.label)).toEqual(["Floor", "Account"]);
    expect(evidence.tools).toEqual(["catalog_lookup"]);
    expect(evidence.partial).toBe(false);
  });
});

describe("governed source links", () => {
  it("allows only HTTP(S) citation URLs", () => {
    expect(safeExternalUrl("https://example.test/policy")).toBe("https://example.test/policy");
    expect(safeExternalUrl("http://example.test/source")).toBe("http://example.test/source");
    expect(safeExternalUrl("javascript:alert(1)")).toBeNull();
    expect(safeExternalUrl("not a URL")).toBeNull();
  });
});

describe("quote summary helpers", () => {
  it("creates an order-independent snapshot and a revenue-weighted margin", () => {
    const a = line({ sku: "A", quantity: 2, unit_price: 100, gross_margin_pct: 20 });
    const b = line({ sku: "B", quantity: 1, unit_price: 300, gross_margin_pct: 40 });

    expect(quoteSnapshot([a, b])).toBe(quoteSnapshot([b, a]));
    expect(blendedMargin([a, b])).toBe(32);
    expect(blendedMargin([line({ gross_margin_pct: undefined })])).toBeNull();
  });
});
