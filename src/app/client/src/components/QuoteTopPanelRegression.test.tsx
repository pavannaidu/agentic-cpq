import { TooltipProvider } from "@databricks/appkit-ui/react";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { DraftLineItem, DraftOrder, SourceFreshness } from "../types";
import { QuotePanel } from "./QuotePanel";

const LINE: DraftLineItem = {
  sku: "EQUIP-1",
  title: "Imaging system",
  category: "Imaging",
  quantity: 1,
  unit_price: 1_000,
  list_price: 1_200,
};

const CARE_LINE: DraftLineItem = {
  sku: "SUPPORT-CARE-IMG",
  title: "Equipment Care · Imaging Care",
  category: "Care",
  quantity: 1,
  unit_price: 120,
  list_price: 120,
  is_addon: true,
  covers_sku: LINE.sku,
};

const SAVED_REVISION: DraftOrder = {
  draft_order_id: "draft-revision-abcdefgh",
  account_id: "account-1",
  status: "saved",
  revision_number: 2,
  parent_draft_order_id: "draft-original-12345678",
  source_quote_id: "quote-original-87654321",
  line_items: [LINE],
  subtotal: 1_000,
  grand_total: 1_000,
};

function TopPanels({
  dirty = false,
  draft = SAVED_REVISION,
  freshness = [],
}: {
  dirty?: boolean;
  draft?: DraftOrder;
  freshness?: SourceFreshness[];
}) {
  return (
    <TooltipProvider>
      <QuotePanel
        account={{ account_id: "account-1", name: "River Dental" }}
        draft={draft}
        freshness={freshness}
        role="seller"
        dirty={dirty}
        onOpenProducts={vi.fn()}
        onQuantity={vi.fn(async () => undefined)}
        onSetPrice={vi.fn(async () => undefined)}
        onRemove={vi.fn(async () => undefined)}
        onSave={vi.fn(async () => undefined)}
        onSend={vi.fn(async () => undefined)}
        onCreateRevision={vi.fn(async () => undefined)}
      />
    </TooltipProvider>
  );
}

describe("quote top-panel identity", () => {
  it("presents one coherent revision and status identity without lifecycle duplication", () => {
    render(<TopPanels />);

    expect(screen.queryByRole("navigation", { name: "Quote lifecycle" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Revision 2/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Draft abcdefgh/)).not.toBeInTheDocument();
    expect(screen.getAllByText("Saved", { exact: true })).toHaveLength(1);

    const quoteHeader = screen.getByRole("heading", { name: "River Dental" }).closest("header");
    expect(quoteHeader).not.toBeNull();
    expect(within(quoteHeader as HTMLElement).getByText("Quote", { exact: true })).toBeInTheDocument();
    expect(within(quoteHeader as HTMLElement).getByText("Saved", { exact: true })).toBeInTheDocument();

    const lineage = screen.getByText(/Based on quote .*87654321/i);
    expect(lineage).not.toHaveTextContent("Revision 2");
    expect(lineage).not.toHaveTextContent("Original unchanged");
  });

  it("keeps the save action label stable for clean and dirty saved revisions", () => {
    const { rerender } = render(<TopPanels />);

    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Saved" })).not.toBeInTheDocument();

    rerender(<TopPanels dirty />);

    expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Saved" })).not.toBeInTheDocument();
  });

});

describe("quote line layout", () => {
  it("aligns net pricing as financial data and exposes the full freshness copy", () => {
    const detail = "Catalog pricing refreshed from the governed workspace source at 9:45 AM";
    render(<TopPanels freshness={[{ source: "catalog", status: "fresh", detail }]} />);

    expect(screen.getByRole("columnheader", { name: "Net unit" })).toHaveClass("table-number");
    const source = screen.getByText(`Pricing source · ${detail}`);
    expect(source.closest(".source-note")).not.toHaveAttribute("title");
  });

  it("keeps attached-care copy inside a table cell with explicit wrap targets", () => {
    render(<TopPanels draft={{ ...SAVED_REVISION, line_items: [LINE, CARE_LINE] }} />);

    const title = screen.getByText(CARE_LINE.title);
    const productCell = title.closest('[data-slot="table-cell"]');
    const metadata = within(productCell as HTMLElement).getByText("SUPPORT-CARE-IMG · Covers EQUIP-1");
    const mobileTotal = within(productCell as HTMLElement).getByText(/^\$120(?:\.00)? total$/);

    expect(productCell?.tagName).toBe("TD");
    expect(productCell).toHaveClass("care-plan-product");
    expect(productCell?.firstElementChild).toHaveClass("care-plan-product-content");
    expect(metadata).toHaveClass("care-plan-meta");
    expect(mobileTotal).toHaveClass("mobile-line-total");
    expect(mobileTotal).not.toBe(metadata);
  });
});
