import { act, fireEvent, render, screen, within } from "@testing-library/react";
import type { ComponentProps } from "react";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { Account } from "../types";

const mocks = vi.hoisted(() => ({
  accounts: vi.fn(),
}));

vi.mock("../api", () => ({
  api: { accounts: mocks.accounts },
}));

import { AccountCombobox } from "./AccountCombobox";

class TestResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

const ACCOUNTS: Account[] = [
  {
    account_id: "acct-river",
    name: "River Dental Group",
    city: "Austin",
    state: "TX",
    specialty: "General dentistry",
    segment: "Group practice",
  },
  {
    account_id: "acct-lake",
    name: "Lakeside Orthodontics",
    city: "Madison",
    state: "WI",
    specialty: "Orthodontics",
    segment: "Independent",
  },
];

function renderCombobox(
  onAccountChange = vi.fn(),
  props: Partial<ComponentProps<typeof AccountCombobox>> = {},
) {
  render(
    <AccountCombobox
      accounts={ACCOUNTS}
      accountId="acct-river"
      onAccountChange={onAccountChange}
      {...props}
    />,
  );
  return onAccountChange;
}

async function openAndSearch(query: string) {
  fireEvent.click(screen.getByRole("combobox", { name: "Select quote account" }));
  const search = screen.getByPlaceholderText("Search accounts…");
  fireEvent.change(search, { target: { value: query } });
  return search;
}

async function advanceSearch(milliseconds = 180) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(milliseconds);
  });
}

describe("AccountCombobox", () => {
  beforeAll(() => {
    vi.stubGlobal("ResizeObserver", TestResizeObserver);
    Object.defineProperty(Element.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(),
    });
  });

  beforeEach(() => {
    vi.useFakeTimers();
    mocks.accounts.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  afterAll(() => {
    vi.unstubAllGlobals();
    Reflect.deleteProperty(Element.prototype, "scrollIntoView");
  });

  it("is accessibly labeled and disables account changes while busy", () => {
    renderCombobox(vi.fn(), { busy: true });

    const trigger = screen.getByRole("combobox", { name: "Select quote account" });
    expect(trigger).toHaveTextContent("River Dental Group");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toBeDisabled();
  });

  it("debounces semantic account search and preserves ranked hits that do not contain the query", async () => {
    const semanticHit: Account = {
      account_id: "acct-smile",
      name: "North Loop Smiles",
      city: "Minneapolis",
      state: "MN",
      specialty: "Prosthodontics",
      segment: "Independent",
    };
    mocks.accounts.mockResolvedValue({ results: [semanticHit], mode: "semantic" });
    renderCombobox();

    const search = await openAndSearch("implant specialist");
    await advanceSearch(179);
    expect(mocks.accounts).not.toHaveBeenCalled();

    await advanceSearch(1);
    expect(mocks.accounts).toHaveBeenCalledOnce();
    const [query, signal] = mocks.accounts.mock.calls[0] as [string, AbortSignal];
    expect(query).toBe("implant specialist");
    expect(signal).toBeInstanceOf(AbortSignal);
    expect(signal.aborted).toBe(false);
    const results = within(screen.getByRole("listbox", { name: "Account results" }));
    expect(results.getByText("North Loop Smiles")).toBeInTheDocument();
    expect(results.queryByText("River Dental Group")).not.toBeInTheDocument();

    fireEvent.change(search, { target: { value: "Madison" } });
    expect(results.queryByText("North Loop Smiles")).not.toBeInTheDocument();
    expect(results.getByText("Lakeside Orthodontics")).toBeInTheDocument();
    expect(mocks.accounts).toHaveBeenCalledOnce();
  });

  it("aborts stale searches and reports loading progress", async () => {
    mocks.accounts.mockReturnValue(new Promise(() => undefined));
    renderCombobox();

    const search = await openAndSearch("orthodontics");
    await advanceSearch();
    expect(screen.getByRole("status", { name: "Searching accounts" })).toBeInTheDocument();

    const firstSignal = mocks.accounts.mock.calls[0]?.[1] as AbortSignal;
    expect(firstSignal.aborted).toBe(false);
    fireEvent.change(search, { target: { value: "pediatric dentistry" } });
    expect(firstSignal.aborted).toBe(true);
  });

  it("selects a semantic result and closes the account list", async () => {
    const semanticHit: Account = {
      account_id: "acct-cedar",
      name: "Cedar Valley Dental",
      city: "Cedar Rapids",
      state: "IA",
      specialty: "Pediatric dentistry",
    };
    mocks.accounts.mockResolvedValue({ results: [semanticHit] });
    const onAccountChange = renderCombobox();

    await openAndSearch("family-focused practice");
    await advanceSearch();
    fireEvent.click(screen.getByText("Cedar Valley Dental"));

    expect(onAccountChange).toHaveBeenCalledWith("acct-cedar");
    expect(screen.getByRole("combobox", { name: "Select quote account" })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.queryByPlaceholderText("Search accounts…")).not.toBeInTheDocument();
  });

  it("falls back to local location matches on errors and exposes an empty state", async () => {
    mocks.accounts.mockRejectedValueOnce(new Error("offline"));
    renderCombobox();

    const search = await openAndSearch("Austin");
    await advanceSearch();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Search is temporarily limited. Showing available accounts.",
    );
    expect(screen.queryByText("Live account search is unavailable. Showing local matches.")).not.toBeInTheDocument();
    expect(
      within(screen.getByRole("listbox", { name: "Account results" })).getByText("River Dental Group"),
    ).toBeInTheDocument();

    mocks.accounts.mockResolvedValueOnce({ results: [] });
    fireEvent.change(search, { target: { value: "no such practice" } });
    await advanceSearch();
    expect(screen.getByText("No accounts match that search.")).toBeInTheDocument();
  });

  it("distinguishes an unavailable account list from a search with no matches", () => {
    const onAccountChange = vi.fn();
    const view = render(
      <AccountCombobox
        accounts={ACCOUNTS}
        accountId="acct-river"
        onAccountChange={onAccountChange}
      />,
    );
    fireEvent.click(screen.getByRole("combobox", { name: "Select quote account" }));

    view.rerender(
      <AccountCombobox accounts={[]} accountId="" onAccountChange={onAccountChange} />,
    );
    expect(screen.getByText("No accounts are available.")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Search accounts…"), { target: { value: "x" } });
    expect(screen.getByText("No accounts match that search.")).toBeInTheDocument();
  });
});
