import { TooltipProvider } from "@databricks/appkit-ui/react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { DraftLineItem, DraftOrder } from "../types";
import { QuotePanel } from "./QuotePanel";

const EMPTY_DRAFT: DraftOrder = {
  draft_order_id: "draft-empty-1",
  account_id: "account-1",
  status: "draft",
  line_items: [],
  subtotal: 0,
  grand_total: 0,
};

const MANY_APPROVAL_LINES: DraftLineItem[] = Array.from({ length: 51 }, (_, index) => ({
  sku: `EQUIP-${index + 1}`,
  title: `Equipment ${index + 1}`,
  category: "Equipment",
  quantity: 1,
  unit_price: 1_000,
  list_price: 1_000,
  approval_required: true,
}));

function TestQuotePanel({ draft }: { draft: DraftOrder }) {
  return (
    <TooltipProvider>
      <QuotePanel
        account={{ account_id: "account-1", name: "River Dental" }}
        draft={draft}
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
    </TooltipProvider>
  );
}

describe("QuotePanel empty state", () => {
  it("offers one clear way to add products alongside the Genie guidance", async () => {
    const user = userEvent.setup();
    const onOpenProducts = vi.fn();

    render(
      <TooltipProvider>
        <QuotePanel
          account={{ account_id: "account-1", name: "River Dental" }}
          draft={EMPTY_DRAFT}
          freshness={[]}
          role="seller"
          onOpenProducts={onOpenProducts}
          onQuantity={vi.fn(async () => undefined)}
          onSetPrice={vi.fn(async () => undefined)}
          onRemove={vi.fn(async () => undefined)}
          onSave={vi.fn(async () => undefined)}
          onSend={vi.fn(async () => undefined)}
          onCreateRevision={vi.fn(async () => undefined)}
        />
      </TooltipProvider>,
    );

    expect(screen.getByText("Start this quote")).toHaveAttribute("data-slot", "empty-title");
    expect(
      screen.getByText("Add products manually, or ask Genie to build it from your goal."),
    ).toBeInTheDocument();

    const addProductActions = screen.getAllByRole("button", { name: "Add product" });
    expect(addProductActions).toHaveLength(1);

    await user.click(addProductActions[0]);
    expect(onOpenProducts).toHaveBeenCalledOnce();
  });

  it("clears quote-line controls and pagination when the active draft changes", async () => {
    const user = userEvent.setup();
    const populatedDraft: DraftOrder = {
      ...EMPTY_DRAFT,
      draft_order_id: "draft-populated-1",
      line_items: MANY_APPROVAL_LINES,
      subtotal: 51_000,
      grand_total: 51_000,
    };
    const { rerender } = render(<TestQuotePanel draft={populatedDraft} />);

    const filter = screen.getByRole("textbox", { name: "Filter quote lines" });
    await user.type(filter, "Equipment");
    await user.click(screen.getByRole("button", { name: "Approvals 51" }));
    await user.click(screen.getByRole("button", { name: "Next quote line page" }));

    expect(filter).toHaveValue("Equipment");
    expect(screen.getByRole("button", { name: "Approvals 51" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();

    rerender(
      <TestQuotePanel
        draft={{ ...populatedDraft, draft_order_id: "draft-populated-2" }}
      />,
    );

    expect(screen.getByRole("textbox", { name: "Filter quote lines" })).toHaveValue("");
    expect(screen.getByRole("button", { name: "Approvals 51" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
  });
});
