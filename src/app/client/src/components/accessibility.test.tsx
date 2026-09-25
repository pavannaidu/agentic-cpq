import { TooltipProvider } from "@databricks/appkit-ui/react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { DraftOrder } from "../types";
import { QuotePanel } from "./QuotePanel";
import { WorkspaceHeader } from "./WorkspaceHeader";

const APPROVAL_DRAFT: DraftOrder = {
  draft_order_id: "draft-1",
  account_id: "account-1",
  status: "draft",
  line_items: [{
    sku: "EQUIP-1",
    title: "Equipment",
    category: "Equipment",
    quantity: 1,
    unit_price: 1_000,
    approval_required: true,
  }],
  subtotal: 1_000,
  grand_total: 1_000,
};

describe("workspace accessibility", () => {
  it("keeps the icon-only mobile history control named and disables context changes while busy", () => {
    render(
      <TooltipProvider>
        <WorkspaceHeader
          accounts={[{ account_id: "account-1", name: "River Dental" }]}
          accountId="account-1"
          user={{ username: "Seller" }}
          role="seller"
          allowedRoles={["seller", "manager"]}
          dark={false}
          busy
          onAccountChange={vi.fn()}
          onRoleChange={vi.fn()}
          onOpenAdmin={vi.fn()}
          onNewQuote={vi.fn()}
          onHistory={vi.fn()}
          onToggleTheme={vi.fn()}
        />
      </TooltipProvider>,
    );

    expect(screen.getByRole("button", { name: "Open quote history" })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Select quote account" })).toBeDisabled();
    expect(screen.queryByRole("combobox", { name: "Select quote view" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "User menu for Seller, Seller role" })).toBeEnabled();
  });

  it("keeps the user and role menu reachable by an accessible button", () => {
    render(
      <TooltipProvider>
        <WorkspaceHeader
          accounts={[{ account_id: "account-1", name: "River Dental" }]}
          accountId="account-1"
          user={{ username: "Manager" }}
          role="seller"
          allowedRoles={["seller", "manager"]}
          dark={false}
          onAccountChange={vi.fn()}
          onRoleChange={vi.fn()}
          onOpenAdmin={vi.fn()}
          onNewQuote={vi.fn()}
          onHistory={vi.fn()}
          onToggleTheme={vi.fn()}
        />
      </TooltipProvider>,
    );

    expect(screen.queryByRole("combobox", { name: "Select quote view" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "User menu for Manager, Seller role" })).toBeEnabled();
  });

  it("exposes the reason an approval-blocked handoff is unavailable to keyboard users", () => {
    render(
      <TooltipProvider>
        <QuotePanel
          account={{ account_id: "account-1", name: "River Dental" }}
          draft={APPROVAL_DRAFT}
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

    expect(screen.getByRole("button", { name: "Generate PDF" })).toBeDisabled();
    expect(screen.getByLabelText("Generate quote PDF unavailable: clear quote approvals first.")).toHaveAttribute("tabindex", "0");
  });
});
