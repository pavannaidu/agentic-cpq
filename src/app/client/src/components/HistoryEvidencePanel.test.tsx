import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import type { DraftLineItem, DraftOrder, Evidence, HistoryItem } from "../types";
import { EvidencePanel } from "./EvidencePanel";
import { HistoryPanel } from "./HistoryPanel";

const LINE: DraftLineItem = {
  sku: "IMAG-CBCT-210",
  title: "Vatech CBCT Imaging Starter",
  category: "Imaging",
  quantity: 1,
  unit_price: 17_575,
  list_price: 18_500,
};

const originalResizeObserver = globalThis.ResizeObserver;

beforeAll(() => {
  globalThis.ResizeObserver = class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
});

afterAll(() => {
  if (originalResizeObserver) globalThis.ResizeObserver = originalResizeObserver;
  else delete (globalThis as Partial<typeof globalThis>).ResizeObserver;
});

function draft(overrides: Partial<DraftOrder> = {}): DraftOrder {
  return {
    draft_order_id: "draft-current",
    account_id: "account-1",
    status: "saved",
    line_items: [LINE],
    subtotal: 17_575,
    grand_total: 17_575,
    version: 4,
    revision_number: 2,
    ...overrides,
  };
}

afterEach(() => vi.restoreAllMocks());

describe("HistoryPanel", () => {
  it("expands a generated quote inside its row with direct PDF actions", async () => {
    const user = userEvent.setup();
    const generated = draft({
      draft_order_id: "draft-generated",
      status: "quote-created",
      quote_id: "quote-8462B4EFDA",
      grand_total: 19_684,
    });
    const item: HistoryItem = {
      draft_order_id: generated.draft_order_id,
      status: generated.status,
      quote_id: generated.quote_id,
      grand_total: generated.grand_total,
      line_count: generated.line_items.length,
      revision_number: 2,
      updated_at: "2026-09-10T16:02:00Z",
    };
    vi.spyOn(api, "history").mockResolvedValue({ items: [item] });
    vi.spyOn(api, "getDraft").mockResolvedValue(generated);

    render(
      <HistoryPanel
        open
        compact={false}
        account={{ account_id: "account-1", name: "River Dental" }}
        currentDraft={draft({ grand_total: 121_285.8 })}
        role="seller"
        onOpenChange={vi.fn()}
        onLoadDraft={vi.fn(async () => undefined)}
      />,
    );

    const trigger = await screen.findByRole("button", { name: "Quote · Rev 2" });
    await user.click(trigger);

    const preview = await screen.findByRole("region", { name: "Selected quote comparison" });
    await waitFor(() => expect(trigger).toHaveAttribute("aria-expanded", "true"));
    expect(trigger.closest('[data-slot="item"]')).toContainElement(preview);
    expect(within(preview).queryByText(/Revision 2/)).not.toBeInTheDocument();
    expect(within(preview).queryByText("8462B4EFDA")).not.toBeInTheDocument();
    expect(within(preview).getByRole("link", { name: "View PDF" })).toHaveAttribute(
      "href",
      "/api/draft-orders/draft-generated/quote.pdf?view_role=seller",
    );
    expect(within(preview).getByRole("link", { name: "View PDF" })).toHaveAttribute("target", "_blank");
    expect(within(preview).getByRole("link", { name: "Download PDF" })).toHaveAttribute(
      "href",
      "/api/draft-orders/draft-generated/quote.pdf?view_role=seller&download=true",
    );
    expect(within(preview).getByRole("link", { name: "Download PDF" })).toHaveAttribute("download");
    expect(within(preview).getByRole("button", { name: "Open quote" })).toBeEnabled();
    expect(screen.queryByText("8462B4EFDA")).not.toBeInTheDocument();
  });

  it("provides an explicit close action in the compact drawer", async () => {
    const onOpenChange = vi.fn();
    vi.spyOn(api, "history").mockResolvedValue({ items: [] });

    render(
      <HistoryPanel
        open
        compact
        account={{ account_id: "account-1", name: "River Dental" }}
        currentDraft={draft()}
        role="seller"
        onOpenChange={onOpenChange}
        onLoadDraft={vi.fn(async () => undefined)}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Close history" }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});

describe("EvidencePanel", () => {
  it("presents clean source labels and hides raw citation fragments", async () => {
    const user = userEvent.setup();
    const evidence: Evidence = {
      citations: [{
        source: "genie_volume",
        title: "financing-and-approval-guide.docx",
        detail: "[2",
        url: "https://example.com/guidance.docx",
      }],
      sql: "SELECT sku FROM products",
      columns: ["sku"],
      rows: [["IMAG-CBCT-210"]],
      checks: [],
      freshness: [],
      tools: ["genie"],
      truncated: false,
      executionIdentity: "databricks-app:agentic-cpq-test",
    };

    render(
      <EvidencePanel
        open
        compact={false}
        evidence={evidence}
        onOpenChange={vi.fn()}
      />,
    );

    expect(screen.getByText("Uses approved app access.")).toBeInTheDocument();
    expect(screen.queryByText(/Runs as the app service principal/i)).not.toBeInTheDocument();
    expect(screen.getByText("financing-and-approval-guide.docx")).toBeInTheDocument();
    expect(screen.getByText("Guidance")).toBeInTheDocument();
    expect(screen.queryByText("genie_volume")).not.toBeInTheDocument();
    expect(screen.queryByText("[2")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open" })).toHaveAttribute("target", "_blank");
    expect(screen.queryByRole("heading", { name: "Query" })).not.toBeInTheDocument();
    expect(screen.queryByText("SELECT sku FROM products")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "View query details" }));
    expect(screen.getByText("SELECT sku FROM products")).toBeInTheDocument();
    expect(screen.getByRole("generic", { name: "Returned data" })).toBeInTheDocument();
  });

  it("uses neutral trust copy when the execution identity is unknown", () => {
    const evidence: Evidence = {
      citations: [],
      sql: "",
      columns: [],
      rows: [],
      checks: [],
      freshness: [],
      tools: [],
      truncated: false,
      executionIdentity: "unknown-runtime",
    };

    render(
      <EvidencePanel
        open
        compact={false}
        evidence={evidence}
        onOpenChange={vi.fn()}
      />,
    );

    expect(screen.getByText("Supporting details for a selected response.")).toBeInTheDocument();
    expect(screen.queryByText("Uses approved app access.")).not.toBeInTheDocument();
    expect(screen.queryByText("Uses your workspace access.")).not.toBeInTheDocument();
  });

  it("renders humanized data status when freshness is the only supporting detail", () => {
    const evidence: Evidence = {
      citations: [],
      sql: "",
      columns: [],
      rows: [],
      checks: [],
      freshness: [{
        source: "system.ai.web_search",
        status: "live",
        detail: "Retrieved for this request.",
      }, {
        source: "genie_conversation_api",
        status: "fresh",
        detail: "Returned by Genie for this request.",
      }],
      tools: ["web_search"],
      truncated: false,
    };

    render(
      <EvidencePanel
        open
        compact={false}
        evidence={evidence}
        onOpenChange={vi.fn()}
      />,
    );

    expect(screen.getByRole("heading", { name: "Data status" })).toBeInTheDocument();
    expect(screen.getByText("Supporting details for a selected response.")).toBeInTheDocument();
    expect(screen.getByText("External reference")).toBeInTheDocument();
    expect(screen.getByText("Workspace data")).toBeInTheDocument();
    expect(screen.getAllByText("Current")).toHaveLength(2);
    expect(screen.getByText("Retrieved for this request.")).toBeInTheDocument();
    expect(screen.queryByText("system.ai.web_search")).not.toBeInTheDocument();
    expect(screen.queryByText("web_search")).not.toBeInTheDocument();
    expect(screen.queryByText("genie_conversation_api")).not.toBeInTheDocument();
    expect(screen.queryByText("No supporting details were returned.")).not.toBeInTheDocument();
  });

  it("provides an explicit close action in the compact drawer", async () => {
    const onOpenChange = vi.fn();

    render(
      <EvidencePanel
        open
        compact
        evidence={null}
        onOpenChange={onOpenChange}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Close details" }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
