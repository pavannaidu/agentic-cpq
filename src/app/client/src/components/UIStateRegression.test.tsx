import { TooltipProvider } from "@databricks/appkit-ui/react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import type { DraftLineItem, DraftOrder, Evidence, Recommendation } from "../types";
import { CopilotPanel } from "./CopilotPanel";
import { QuotePanel } from "./QuotePanel";
import { RecommendationCard } from "./RecommendationCard";

const LINE: DraftLineItem = {
  sku: "EQUIP-1",
  title: "Imaging system",
  category: "Imaging",
  quantity: 2,
  unit_price: 1_000,
  list_price: 1_200,
};

const EVIDENCE: Evidence = {
  citations: [],
  sql: "",
  columns: [],
  rows: [],
  checks: [],
  freshness: [],
  tools: [],
  truncated: false,
};

function draft(overrides: Partial<DraftOrder> = {}): DraftOrder {
  return {
    draft_order_id: "draft-1",
    account_id: "account-1",
    status: "draft",
    line_items: [LINE],
    subtotal: 2_000,
    grand_total: 2_000,
    version: 4,
    ...overrides,
  };
}

const originalScrollIntoView = Object.getOwnPropertyDescriptor(Element.prototype, "scrollIntoView");

beforeAll(() => {
  Object.defineProperty(Element.prototype, "scrollIntoView", {
    configurable: true,
    value: vi.fn(),
  });
});

afterAll(() => {
  if (originalScrollIntoView) {
    Object.defineProperty(Element.prototype, "scrollIntoView", originalScrollIntoView);
  } else {
    delete (Element.prototype as Partial<Element>).scrollIntoView;
  }
});

describe("QuotePanel mutation guards", () => {
  it("uses the workspace approval threshold and seller price permission", () => {
    render(
      <TooltipProvider>
        <QuotePanel
          account={{ account_id: "account-1", name: "River Dental" }}
          draft={draft({ grand_total: 2_000 })}
          freshness={[]}
          role="seller"
          approvalThreshold={1_500}
          canEditNetPrice={false}
          onOpenProducts={vi.fn()}
          onQuantity={vi.fn(async () => undefined)}
          onSetPrice={vi.fn(async () => undefined)}
          onRemove={vi.fn(async () => undefined)}
          onSave={vi.fn(async () => undefined)}
          onSend={vi.fn(async () => undefined)}
          onCreateRevision={vi.fn(async () => undefined)}
        />
      </TooltipProvider>,
    );

    expect(screen.getByText("Quote total above $1,500")).toBeInTheDocument();
    const price = screen.getByRole("textbox", { name: "Net unit price for Imaging system" });
    expect(price).toBeDisabled();
    expect(price).toHaveAttribute("title", "Net price editing is limited to managers.");
    expect(screen.getByRole("button", { name: "Generate PDF" })).toBeDisabled();
  });

  it("keeps the empty quote focused on one busy-safe catalog action", async () => {
    const user = userEvent.setup();
    const onOpenProducts = vi.fn();
    const emptyDraft = draft({ line_items: [], subtotal: 0, grand_total: 0 });
    const quotePanel = (busy: boolean) => (
      <TooltipProvider>
        <QuotePanel
          account={{ account_id: "account-1", name: "River Dental" }}
          draft={emptyDraft}
          freshness={[]}
          role="seller"
          busy={busy}
          onOpenProducts={onOpenProducts}
          onQuantity={vi.fn(async () => undefined)}
          onSetPrice={vi.fn(async () => undefined)}
          onRemove={vi.fn(async () => undefined)}
          onSave={vi.fn(async () => undefined)}
          onSend={vi.fn(async () => undefined)}
          onCreateRevision={vi.fn(async () => undefined)}
        />
      </TooltipProvider>
    );
    const { rerender } = render(quotePanel(true));

    expect(screen.getByText("Start this quote")).toBeInTheDocument();
    expect(screen.getByText("Add products manually, or ask Genie to build it from your goal.")).toBeInTheDocument();
    expect(screen.queryByText(/guided assistant workflow/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Add products to continue")).not.toBeInTheDocument();
    expect(screen.queryByText("Draft ready")).not.toBeInTheDocument();
    expect(screen.queryByText(/Review the quote, then generate/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Add product" })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Add product" })).toBeDisabled();

    rerender(quotePanel(false));
    await user.click(screen.getByRole("button", { name: "Add product" }));
    expect(onOpenProducts).toHaveBeenCalledOnce();
  });

  it("filters a dense quote by product name or SKU without changing the draft", async () => {
    const user = userEvent.setup();
    const sterilizer: DraftLineItem = {
      ...LINE,
      sku: "STERI-2",
      title: "Sterilization suite",
      category: "Sterilization",
    };
    render(
      <TooltipProvider>
        <QuotePanel
          account={{ account_id: "account-1", name: "River Dental" }}
          draft={draft({ line_items: [LINE, sterilizer], grand_total: 4_000 })}
          freshness={[]}
          role="seller"
          onOpenProducts={vi.fn()}
          onQuantity={vi.fn(async () => undefined)}
          onSetPrice={vi.fn(async () => undefined)}
          onRemove={vi.fn(async () => undefined)}
          onSave={vi.fn(async () => undefined)}
          onSend={vi.fn(async () => undefined)}
          onCreateRevision={vi.fn(async () => undefined)}
        />
      </TooltipProvider>,
    );

    await user.type(screen.getByRole("textbox", { name: "Filter quote lines" }), "STERI-2");

    expect(screen.getByRole("heading", { name: "Sterilization suite" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Imaging system" })).not.toBeInTheDocument();
    expect(screen.getByText("1 of 2")).toBeInTheDocument();
  });

  it("paginates quotes with hundreds of products while filtering across the full draft", async () => {
    const user = userEvent.setup();
    const lines = Array.from({ length: 125 }, (_, index): DraftLineItem => ({
      ...LINE,
      sku: `SKU-${String(index + 1).padStart(3, "0")}`,
      title: `Catalog product ${index + 1}`,
      category: "Consumables",
      quantity: 1,
    }));
    render(
      <TooltipProvider>
        <QuotePanel
          account={{ account_id: "account-1", name: "River Dental" }}
          draft={draft({ line_items: lines, grand_total: 125_000 })}
          freshness={[]}
          role="seller"
          onOpenProducts={vi.fn()}
          onQuantity={vi.fn(async () => undefined)}
          onSetPrice={vi.fn(async () => undefined)}
          onRemove={vi.fn(async () => undefined)}
          onSave={vi.fn(async () => undefined)}
          onSend={vi.fn(async () => undefined)}
          onCreateRevision={vi.fn(async () => undefined)}
        />
      </TooltipProvider>,
    );

    expect(screen.getByText("1–50 of 125 products")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Catalog product 50" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Catalog product 51" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Next quote line page" }));

    expect(screen.getByText("51–100 of 125 products")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Catalog product 51" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Catalog product 1" })).not.toBeInTheDocument();

    await user.type(screen.getByRole("textbox", { name: "Filter quote lines" }), "SKU-125");

    expect(screen.getByRole("heading", { name: "Catalog product 125" })).toBeInTheDocument();
    expect(screen.getByText("1 of 125")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Quote line pagination" })).not.toBeInTheDocument();
  });

  it("locks sent quote mutations and offers compact document actions", async () => {
    const user = userEvent.setup();
    const onCreateRevision = vi.fn(async () => undefined);
    render(
      <TooltipProvider>
        <QuotePanel
          account={{ account_id: "account-1", name: "River Dental" }}
          draft={draft({ status: "quote-created", quote_id: "quote-1" })}
          freshness={[]}
          role="seller"
          dirty
          onOpenProducts={vi.fn()}
          onQuantity={vi.fn(async () => undefined)}
          onSetPrice={vi.fn(async () => undefined)}
          onRemove={vi.fn(async () => undefined)}
          onSave={vi.fn(async () => undefined)}
          onSend={vi.fn(async () => undefined)}
          onCreateRevision={onCreateRevision}
        />
      </TooltipProvider>,
    );

    expect(screen.getByRole("button", { name: "Add product" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Decrease Imaging system quantity" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Increase Imaging system quantity" })).toBeDisabled();
    expect(screen.getByRole("textbox", { name: "Net unit price for Imaging system" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Remove Imaging system" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save draft" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generate quote PDF" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View PDF" })).toHaveAttribute(
      "href",
      "/api/draft-orders/draft-1/quote.pdf?view_role=seller",
    );
    expect(screen.getByRole("link", { name: "View PDF" })).toHaveAttribute("target", "_blank");
    expect(screen.getByRole("link", { name: "Download PDF" })).toHaveAttribute(
      "href",
      "/api/draft-orders/draft-1/quote.pdf?view_role=seller&download=true",
    );
    expect(screen.getByRole("link", { name: "Download PDF" })).toHaveAttribute("download");
    expect(screen.getByRole("button", { name: "Create new version" })).toBeEnabled();
    expect(screen.queryByText("Locked document")).not.toBeInTheDocument();
    expect(screen.queryByText("Customer PDF generated")).not.toBeInTheDocument();
    expect(screen.queryByText("Generated quote locked")).not.toBeInTheDocument();
    expect(screen.queryByText(/Create a revision to propose changes/)).not.toBeInTheDocument();
    expect(screen.getByText("List value")).toBeInTheDocument();
    expect(screen.getByText("$2,400")).toBeInTheDocument();
    expect(screen.getByText("Savings")).toBeInTheDocument();
    expect(screen.getByText("$400")).toBeInTheDocument();
    expect(screen.getByText("16.7% from list")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Create new version" }));
    expect(onCreateRevision).toHaveBeenCalledOnce();
  });

  it("restores the authoritative price and exposes invalid state when a price update is rejected", async () => {
    const user = userEvent.setup();
    const onSetPrice = vi.fn(async () => {
      throw new Error("Pricing service rejected the update");
    });
    render(
      <TooltipProvider>
        <QuotePanel
          account={{ account_id: "account-1", name: "River Dental" }}
          draft={draft()}
          freshness={[]}
          role="seller"
          onOpenProducts={vi.fn()}
          onQuantity={vi.fn(async () => undefined)}
          onSetPrice={onSetPrice}
          onRemove={vi.fn(async () => undefined)}
          onSave={vi.fn(async () => undefined)}
          onSend={vi.fn(async () => undefined)}
          onCreateRevision={vi.fn(async () => undefined)}
        />
      </TooltipProvider>,
    );

    const price = screen.getByRole("textbox", { name: "Net unit price for Imaging system" });
    await user.clear(price);
    await user.type(price, "875.50");
    await user.tab();

    expect(onSetPrice).toHaveBeenCalledWith(LINE, 875.5);
    await waitFor(() => {
      expect(price).toHaveValue("1000");
      expect(price).toHaveAttribute("aria-invalid", "true");
    });
  });
});

describe("assistant mutation guards", () => {
  it("disables an outdated recommendation when the live draft version has changed", () => {
    const recommendation: Recommendation = {
      summary: "Add an imaging system",
      recommendation_id: "recommendation-1",
      revision: 1,
      draft_version: 3,
      items: [LINE],
    };
    const onApply = vi.fn(async () => undefined);
    const onRefresh = vi.fn(async () => undefined);

    render(
      <RecommendationCard
        recommendation={recommendation}
        currentLines={[]}
        currentDraftVersion={4}
        role="seller"
        onApply={onApply}
        onRefresh={onRefresh}
        onEvidence={vi.fn()}
        evidence={EVIDENCE}
      />,
    );

    expect(screen.queryByText("Outdated")).not.toBeInTheDocument();
    expect(screen.getByText("The quote changed. Update this proposal before applying.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Update proposal" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Update proposal" }));
    expect(onRefresh).toHaveBeenCalledOnce();
    expect(onApply).not.toHaveBeenCalled();
  });

  it("disables the composer until Copilot is ready", () => {
    const onSubmit = vi.fn(async () => undefined);

    render(
      <CopilotPanel
        messages={[]}
        stages={[]}
        currentLines={[]}
        currentDraftVersion={4}
        role="seller"
        ready={false}
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        onApply={vi.fn(async () => undefined)}
        onEvidence={vi.fn()}
      />,
    );

    expect(screen.getByRole("textbox", { name: "Message Genie" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
    expect(screen.getByText("Ask about this quote or request changes.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Suggested" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Suggested workflow/i)).not.toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
