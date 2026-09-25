import { TooltipProvider } from "@databricks/appkit-ui/react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import type { ViewRole } from "../types";
import { WorkspaceHeader } from "./WorkspaceHeader";

beforeAll(() => {
  vi.stubGlobal("ResizeObserver", class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  });
});

afterAll(() => {
  vi.unstubAllGlobals();
});

function renderHeader({
  allowedRoles = ["seller", "manager"],
  role = "seller",
  busy = false,
  canManage = true,
  onRoleChange = vi.fn(),
  onOpenAdmin = vi.fn(),
  onNewQuote = vi.fn(),
  newQuoteDisabled = false,
}: {
  allowedRoles?: ViewRole[];
  role?: ViewRole;
  busy?: boolean;
  canManage?: boolean;
  onRoleChange?: (role: ViewRole) => void;
  onOpenAdmin?: () => void;
  onNewQuote?: () => void;
  newQuoteDisabled?: boolean;
} = {}) {
  return render(
    <TooltipProvider>
      <WorkspaceHeader
        accounts={[{ account_id: "account-1", name: "River Dental" }]}
        accountId="account-1"
        user={{ username: "Avery Johnson", email: "avery@example.com", authenticated: true, can_manage: canManage }}
        role={role}
        allowedRoles={allowedRoles}
        dark={false}
        busy={busy}
        onAccountChange={vi.fn()}
        onRoleChange={onRoleChange}
        onOpenAdmin={onOpenAdmin}
        onNewQuote={onNewQuote}
        newQuoteDisabled={newQuoteDisabled}
        onHistory={vi.fn()}
        onToggleTheme={vi.fn()}
      />
    </TooltipProvider>,
  );
}

describe("WorkspaceHeader identity menu", () => {
  it("keeps the product brand primary and orders New quote, History, then User", () => {
    renderHeader();
    const header = screen.getByRole("banner");
    const actions = header.querySelector(".header-actions");
    expect(actions).not.toBeNull();

    const newQuote = within(actions as HTMLElement).getByRole("button", { name: "New quote" });
    const history = within(actions as HTMLElement).getByRole("button", { name: "Open quote history" });
    const userMenu = within(actions as HTMLElement).getByRole("button", { name: "User menu for Avery Johnson, Seller role" });

    expect(within(header).getByRole("heading", { name: "Agentic CPQ" })).toBeInTheDocument();
    expect(within(actions as HTMLElement).getAllByRole("button")).toEqual([newQuote, history, userMenu]);
    expect(within(header).queryByRole("link", { name: "About Agentic CPQ" })).not.toBeInTheDocument();
    expect(within(header).getByRole("combobox", { name: "Select quote account" })).toBeInTheDocument();
    expect(within(header).queryByText("Account", { exact: true })).not.toBeInTheDocument();
    expect(within(header).queryByRole("heading", { name: "Quote Workspace" })).not.toBeInTheDocument();
    expect(within(header).queryByText("Powered by Databricks")).not.toBeInTheDocument();
  });

  it("starts a new quote from the primary header action and explains it with a tooltip", async () => {
    const user = userEvent.setup();
    const onNewQuote = vi.fn();
    renderHeader({ onNewQuote });

    const newQuote = screen.getByRole("button", { name: "New quote" });
    expect(newQuote).toHaveClass("new-quote-button");

    await user.hover(newQuote);
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Start a new quote");
    await user.click(newQuote);

    expect(onNewQuote).toHaveBeenCalledOnce();
  });

  it("disables New quote while the workspace is busy or the current quote is pristine", () => {
    const { unmount } = renderHeader({ busy: true });
    expect(screen.getByRole("button", { name: "New quote" })).toBeDisabled();

    unmount();
    renderHeader({ newQuoteDisabled: true });
    expect(screen.getByRole("button", { name: "New quote" })).toBeDisabled();
  });

  it("moves About Agentic CPQ into the user menu", async () => {
    const user = userEvent.setup();
    renderHeader();

    await user.click(screen.getByRole("button", { name: "User menu for Avery Johnson, Seller role" }));

    const about = screen.getByRole("menuitem", { name: "About Agentic CPQ" });
    expect(about).toHaveAttribute("href", "/info");
    expect(about.tagName).toBe("A");
  });

  it("removes the standalone View selector and switches to an allowed Manager view", async () => {
    const user = userEvent.setup();
    const onRoleChange = vi.fn();
    renderHeader({ onRoleChange });

    expect(screen.queryByRole("combobox", { name: "Select quote view" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "User menu for Avery Johnson, Seller role" }));

    const seller = screen.getByRole("menuitemradio", { name: "Seller" });
    const manager = screen.getByRole("menuitemradio", { name: "Manager" });
    expect(seller).toHaveAttribute("aria-checked", "true");
    expect(manager).toHaveAttribute("aria-checked", "false");

    await user.click(manager);
    expect(onRoleChange).toHaveBeenCalledOnce();
    expect(onRoleChange).toHaveBeenCalledWith("manager");
  });

  it("shows only role options granted to the signed-in user", async () => {
    const user = userEvent.setup();
    renderHeader({ allowedRoles: ["seller"] });

    await user.click(screen.getByRole("button", { name: "User menu for Avery Johnson, Seller role" }));

    expect(screen.getByRole("menuitemradio", { name: "Seller" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitemradio", { name: "Manager" })).not.toBeInTheDocument();
  });

  it("keeps identity details available while busy but prevents role switching", async () => {
    const user = userEvent.setup();
    const onRoleChange = vi.fn();
    renderHeader({ busy: true, onRoleChange });

    const trigger = screen.getByRole("button", { name: "User menu for Avery Johnson, Seller role" });
    expect(trigger).toBeEnabled();
    await user.click(trigger);

    const seller = screen.getByRole("menuitemradio", { name: "Seller" });
    const manager = screen.getByRole("menuitemradio", { name: "Manager" });
    expect(seller).toHaveAttribute("aria-disabled", "true");
    expect(manager).toHaveAttribute("aria-disabled", "true");

    fireEvent.click(manager);
    expect(onRoleChange).not.toHaveBeenCalled();
  });

  it("opens workspace settings from the manager's user menu", async () => {
    const user = userEvent.setup();
    const onOpenAdmin = vi.fn();
    renderHeader({ onOpenAdmin });

    await user.click(screen.getByRole("button", { name: "User menu for Avery Johnson, Seller role" }));
    await user.click(screen.getByRole("menuitem", { name: "Workspace settings" }));

    expect(onOpenAdmin).toHaveBeenCalledOnce();
  });

  it("does not expose workspace settings without manager permission", async () => {
    const user = userEvent.setup();
    renderHeader({ canManage: false, allowedRoles: ["seller"] });

    await user.click(screen.getByRole("button", { name: "User menu for Avery Johnson, Seller role" }));

    expect(screen.queryByRole("menuitem", { name: "Workspace settings" })).not.toBeInTheDocument();
  });
});
