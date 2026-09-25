import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { DraftLineItem, DraftOrder } from "../types";
import { QuoteLifecycle } from "./QuoteLifecycle";

const LINE: DraftLineItem = {
  sku: "EQUIP-1",
  title: "Equipment",
  category: "Equipment",
  quantity: 1,
  unit_price: 1_000,
};

function makeDraft(overrides: Partial<DraftOrder> = {}): DraftOrder {
  return {
    draft_order_id: "draft-12345678-abcd",
    account_id: "account-1",
    status: "draft",
    line_items: [],
    subtotal: 0,
    grand_total: 0,
    ...overrides,
  };
}

function step(label: string): HTMLElement {
  return screen.getByRole("listitem", { name: new RegExp(`^${label} —`) });
}

describe("QuoteLifecycle", () => {
  it("starts at Configure when the draft has no lines", () => {
    render(<QuoteLifecycle draft={makeDraft()} />);

    const lifecycle = screen.getByRole("navigation", { name: "Quote lifecycle" });
    expect(lifecycle).toBeInTheDocument();
    expect(step("Configure")).toHaveAttribute("data-state", "current");
    expect(step("Configure")).toHaveAttribute("aria-current", "step");
    expect(step("Price")).toHaveAttribute("data-state", "upcoming");
    expect(within(lifecycle).queryByText(/Revision 1|Draft abcd/)).not.toBeInTheDocument();
  });

  it("moves to Price while a line requires approval", () => {
    render(
      <QuoteLifecycle
        draft={makeDraft({ line_items: [{ ...LINE, approval_required: true }] })}
      />,
    );

    expect(step("Configure")).toHaveAttribute("data-state", "complete");
    expect(step("Price")).toHaveAttribute("data-state", "current");
    expect(step("Price")).toHaveAttribute("aria-current", "step");
    expect(step("Review")).toHaveAttribute("data-state", "upcoming");
  });

  it("moves to Review when populated lines have no approval hold", () => {
    render(<QuoteLifecycle draft={makeDraft({ line_items: [LINE] })} />);

    expect(step("Configure")).toHaveAttribute("data-state", "complete");
    expect(step("Price")).toHaveAttribute("data-state", "complete");
    expect(step("Review")).toHaveAttribute("data-state", "current");
    expect(step("Generate")).toHaveAttribute("data-state", "upcoming");
  });

  it("holds at Price when the quote total crosses the regional approval threshold", () => {
    render(
      <QuoteLifecycle
        draft={makeDraft({ line_items: [LINE], grand_total: 50_001 })}
        approvalThreshold={50_000}
      />,
    );

    expect(step("Configure")).toHaveAttribute("data-state", "complete");
    expect(step("Price")).toHaveAttribute("data-state", "current");
    expect(step("Review")).toHaveAttribute("data-state", "upcoming");
  });

  it("marks the full lifecycle complete after the quote is created", () => {
    render(
      <QuoteLifecycle
        draft={makeDraft({ status: "quote-created", quote_id: "quote-1", line_items: [LINE] })}
      />,
    );

    for (const label of ["Configure", "Price", "Review", "Generate"]) {
      expect(step(label)).toHaveAttribute("data-state", "complete");
    }
    expect(step("Generate")).toHaveAttribute("aria-current", "step");
  });
});
