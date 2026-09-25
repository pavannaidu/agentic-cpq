import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import type { AdminSettings } from "../types";
import { AdminSettingsPanel } from "./AdminSettingsPanel";

const SETTINGS: AdminSettings = {
  pdf: {
    layout: "classic",
    show_list_prices: true,
    show_savings: true,
    brand_name: "QUOTE WORKSPACE",
    document_title: "Customer quote",
    accent_color: "#FF3621",
    footer_text: "Powered by Databricks",
    terms_text: "Pricing is valid for 30 days.",
    validity_days: 30,
  },
  behavior: {
    approval_threshold: 80000,
    max_seller_discount_pct: 20,
    auto_attach_care_plan: true,
    allow_seller_price_edits: true,
  },
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

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("AdminSettingsPanel", () => {
  it("loads the manager settings and exposes both focused sections", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "getAdminSettings").mockResolvedValue(SETTINGS);

    render(<AdminSettingsPanel open onOpenChange={vi.fn()} />);

    expect(await screen.findByDisplayValue("QUOTE WORKSPACE")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Quote PDF" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("button", { name: "Preview PDF" })).toBeEnabled();
    expect(screen.getByLabelText("Show list prices")).toBeChecked();
    expect(screen.queryByLabelText(/settings summary/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Current configuration impact" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "PDF design" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Quote rules" }));
    expect(screen.getByLabelText("Quote total review threshold")).toHaveValue(80000);
    expect(screen.getByLabelText("Discount review threshold")).toHaveValue(20);
    expect(screen.getByLabelText("Review deep discounts")).toBeChecked();
    expect(screen.getByLabelText("Edit net prices")).toBeChecked();
    expect(screen.getByLabelText("Attach eligible care plans")).toBeChecked();
  });

  it("preserves unsaved changes while moving between focused sections", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "getAdminSettings").mockResolvedValue(SETTINGS);

    render(<AdminSettingsPanel open onOpenChange={vi.fn()} />);

    const title = await screen.findByLabelText("Document title");
    await user.clear(title);
    await user.type(title, "Enterprise proposal");
    await user.click(screen.getByRole("tab", { name: "Quote rules" }));
    const threshold = screen.getByLabelText("Quote total review threshold");
    await user.clear(threshold);
    await user.type(threshold, "95000");
    await user.click(screen.getByLabelText("Attach eligible care plans"));

    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    expect(screen.queryByLabelText(/settings summary/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Quote PDF" }));
    expect(screen.getByLabelText("Document title")).toHaveValue("Enterprise proposal");
  });

  it("restores the previous discount threshold after temporarily disabling review", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "getAdminSettings").mockResolvedValue({
      ...SETTINGS,
      behavior: { ...SETTINGS.behavior, max_seller_discount_pct: 100 },
    });

    render(<AdminSettingsPanel open onOpenChange={vi.fn()} />);

    await user.click(await screen.findByRole("tab", { name: "Quote rules" }));
    expect(screen.getByLabelText("Review deep discounts")).not.toBeChecked();
    expect(screen.queryByLabelText("Discount review threshold")).not.toBeInTheDocument();

    await user.click(screen.getByLabelText("Review deep discounts"));
    expect(screen.getByLabelText("Discount review threshold")).toHaveValue(20);

    const limit = screen.getByLabelText("Discount review threshold");
    await user.clear(limit);
    await user.type(limit, "17.5");
    await user.click(screen.getByLabelText("Review deep discounts"));
    await user.click(screen.getByLabelText("Review deep discounts"));
    expect(screen.getByLabelText("Discount review threshold")).toHaveValue(17.5);
  });

  it("confirms before closing with unsaved changes", async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    vi.spyOn(api, "getAdminSettings").mockResolvedValue(SETTINGS);

    render(<AdminSettingsPanel open onOpenChange={onOpenChange} />);

    const title = await screen.findByLabelText("Document title");
    await user.clear(title);
    await user.type(title, "Unsaved proposal");
    await user.click(screen.getByRole("button", { name: "Close" }));

    const dialog = screen.getByRole("alertdialog", { name: "Discard unsaved changes?" });
    expect(dialog).toHaveTextContent("have not been saved");
    expect(onOpenChange).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole("button", { name: "Continue editing" }));
    expect(screen.getByLabelText("Document title")).toHaveValue("Unsaved proposal");

    await user.click(screen.getByRole("button", { name: "Close" }));
    const reopenedDialog = screen.getByRole("alertdialog", { name: "Discard unsaved changes?" });
    await user.click(within(reopenedDialog).getByRole("button", { name: "Discard changes" }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("opens a server-rendered sample PDF with unsaved document settings", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "getAdminSettings").mockResolvedValue(SETTINGS);
    const preview = vi.spyOn(api, "previewAdminPdf").mockResolvedValue(
      new Blob(["%PDF-preview"], { type: "application/pdf" }),
    );
    const replace = vi.fn();
    const close = vi.fn();
    vi.spyOn(window, "open").mockReturnValue({
      location: { replace },
      close,
      opener: window,
    } as unknown as Window);
    const createObjectURL = vi.fn(() => "blob:sample-pdf");
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL: vi.fn() });

    render(<AdminSettingsPanel open onOpenChange={vi.fn()} />);

    const title = await screen.findByLabelText("Document title");
    await user.clear(title);
    await user.type(title, "Unsaved proposal");
    await user.click(screen.getByRole("button", { name: "Preview PDF" }));

    await waitFor(() => expect(preview).toHaveBeenCalledOnce());
    expect(preview).toHaveBeenCalledWith({ ...SETTINGS.pdf, document_title: "Unsaved proposal" });
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(replace).toHaveBeenCalledWith("blob:sample-pdf");
    expect(close).not.toHaveBeenCalled();
  });

  it("resets local edits and saves the complete validated settings document", async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    vi.spyOn(api, "getAdminSettings").mockResolvedValue(SETTINGS);
    const update = vi.spyOn(api, "updateAdminSettings").mockImplementation(async (settings) => settings);

    render(<AdminSettingsPanel open onOpenChange={vi.fn()} onSaved={onSaved} />);

    const brand = await screen.findByLabelText("Brand name");
    await user.clear(brand);
    await user.type(brand, "Northstar Dental");
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Discard changes" }));
    expect(brand).toHaveValue("QUOTE WORKSPACE");

    await user.clear(brand);
    await user.type(brand, "Northstar Dental");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(update).toHaveBeenCalledOnce());
    expect(update).toHaveBeenCalledWith({
      ...SETTINGS,
      pdf: { ...SETTINGS.pdf, brand_name: "Northstar Dental" },
    });
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(onSaved).toHaveBeenCalledWith({
      ...SETTINGS,
      pdf: { ...SETTINGS.pdf, brand_name: "Northstar Dental" },
    });
  });

  it("keeps invalid values local and presents API failures without closing", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "getAdminSettings").mockResolvedValue(SETTINGS);
    const update = vi.spyOn(api, "updateAdminSettings").mockRejectedValue(new Error("Only managers can update settings."));

    render(<AdminSettingsPanel open onOpenChange={vi.fn()} />);

    const color = await screen.findByLabelText("Accent color");
    await user.clear(color);
    await user.type(color, "orange");
    expect(screen.getByText(/six-digit hex color/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    expect(update).not.toHaveBeenCalled();

    await user.clear(color);
    await user.type(color, "#112233");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Only managers can update settings.")).toBeInTheDocument();
  });

  it("keeps PDF preview available when only a quote rule is invalid", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "getAdminSettings").mockResolvedValue(SETTINGS);

    render(<AdminSettingsPanel open onOpenChange={vi.fn()} />);

    await user.click(await screen.findByRole("tab", { name: "Quote rules" }));
    const threshold = screen.getByLabelText("Quote total review threshold");
    await user.clear(threshold);
    await user.type(threshold, "0");
    expect(screen.getByText(/review threshold must be greater than zero/i)).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Quote PDF" }));
    expect(screen.getByRole("button", { name: "Preview PDF" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  });

  it("protects unsaved workspace settings from an accidental page exit", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "getAdminSettings").mockResolvedValue(SETTINGS);
    render(<AdminSettingsPanel open onOpenChange={vi.fn()} />);

    const title = await screen.findByLabelText("Document title");
    const cleanExit = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(cleanExit);
    expect(cleanExit.defaultPrevented).toBe(false);

    await user.clear(title);
    await user.type(title, "Enterprise proposal");
    const dirtyExit = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirtyExit);
    expect(dirtyExit.defaultPrevented).toBe(true);
  });
});
