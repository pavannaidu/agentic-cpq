import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { Product } from "../types";

const mocks = vi.hoisted(() => ({
  products: vi.fn(),
}));

vi.mock("../api", () => ({
  api: { products: mocks.products },
}));

import { ProductDialog } from "./ProductDialog";

class TestResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

const LOCAL_PRODUCTS: Product[] = [
  {
    sku: "SCAN-100",
    title: "Digital Intraoral Scanner",
    category: "Digital imaging",
    description: "Chairside scanning system",
    unit_price: 18_500,
    warranty_eligible: true,
  },
  {
    sku: "CHAIR-200",
    title: "Patient Chair",
    category: "Operatory",
    unit_price: 9_250,
  },
];

function renderDialog(onAdd = vi.fn(async () => undefined), onOpenChange = vi.fn()) {
  render(
    <ProductDialog
      open
      products={LOCAL_PRODUCTS}
      role="seller"
      onOpenChange={onOpenChange}
      onAdd={onAdd}
    />,
  );
  return { onAdd, onOpenChange };
}

async function advanceSearch(milliseconds = 220) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(milliseconds);
  });
}

describe("ProductDialog catalog search", () => {
  beforeAll(() => {
    vi.stubGlobal("ResizeObserver", TestResizeObserver);
    Object.defineProperty(Element.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(),
    });
  });

  beforeEach(() => {
    vi.useFakeTimers();
    mocks.products.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  afterAll(() => {
    vi.unstubAllGlobals();
    Reflect.deleteProperty(Element.prototype, "scrollIntoView");
  });

  it("debounces semantic search, passes a cancellation signal, and does not literally filter ranked hits", async () => {
    const semanticHit: Product = {
      sku: "CAD-410",
      title: "Chairside Milling Unit",
      category: "CAD/CAM",
      unit_price: 42_000,
    };
    mocks.products.mockResolvedValue({ results: [semanticHit], mode: "semantic" });
    renderDialog();

    const search = screen.getByPlaceholderText("Search products, SKUs, or categories…");
    fireEvent.change(search, { target: { value: "same day restorations" } });

    await advanceSearch(219);
    expect(mocks.products).not.toHaveBeenCalled();

    await advanceSearch(1);
    expect(mocks.products).toHaveBeenCalledOnce();
    const [query, role, signal] = mocks.products.mock.calls[0] as [string, string, AbortSignal];
    expect(query).toBe("same day restorations");
    expect(role).toBe("seller");
    expect(signal).toBeInstanceOf(AbortSignal);
    expect(signal.aborted).toBe(false);
    expect(screen.getByText("Chairside Milling Unit")).toBeInTheDocument();
    expect(screen.queryByText("Digital Intraoral Scanner")).not.toBeInTheDocument();

    fireEvent.change(search, { target: { value: "patient chair" } });
    expect(screen.queryByText("Chairside Milling Unit")).not.toBeInTheDocument();
    expect(screen.getByText("Patient Chair")).toBeInTheDocument();
    expect(mocks.products).toHaveBeenCalledOnce();
  });

  it("aborts an in-flight request when the search changes", async () => {
    mocks.products.mockReturnValue(new Promise(() => undefined));
    renderDialog();

    const search = screen.getByPlaceholderText("Search products, SKUs, or categories…");
    fireEvent.change(search, { target: { value: "scanner" } });
    await advanceSearch();

    const firstSignal = mocks.products.mock.calls[0]?.[2] as AbortSignal;
    expect(firstSignal.aborted).toBe(false);

    fireEvent.change(search, { target: { value: "scanner cart" } });
    expect(firstSignal.aborted).toBe(true);
  });

  it("shows loading feedback and invokes both selection callbacks", async () => {
    let resolveSearch!: (value: { results: Product[] }) => void;
    mocks.products.mockReturnValue(new Promise((resolve) => { resolveSearch = resolve; }));
    const onAdd = vi.fn(async () => undefined);
    const onOpenChange = vi.fn();
    renderDialog(onAdd, onOpenChange);

    fireEvent.change(
      screen.getByPlaceholderText("Search products, SKUs, or categories…"),
      { target: { value: "digital workflow" } },
    );
    await advanceSearch();
    expect(screen.getByRole("status", { name: "Searching catalog" })).toBeInTheDocument();

    await act(async () => {
      resolveSearch({ results: [LOCAL_PRODUCTS[0]] });
    });
    fireEvent.click(screen.getByText("Digital Intraoral Scanner"));

    await act(async () => undefined);
    expect(onAdd).toHaveBeenCalledWith(LOCAL_PRODUCTS[0]);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("falls back to local matches on server errors and exposes a useful empty state", async () => {
    mocks.products.mockRejectedValueOnce(new Error("offline"));
    renderDialog();

    const search = screen.getByPlaceholderText("Search products, SKUs, or categories…");
    fireEvent.change(search, { target: { value: "scanner" } });
    await advanceSearch();

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Search is temporarily limited. Showing available products.",
    );
    expect(screen.getByText("Account pricing is applied automatically.")).toBeInTheDocument();
    expect(screen.queryByText(/governed catalog/i)).not.toBeInTheDocument();
    expect(screen.getByText("Digital Intraoral Scanner")).toBeInTheDocument();

    mocks.products.mockResolvedValueOnce({ results: [] });
    fireEvent.change(search, { target: { value: "unobtainium" } });
    await advanceSearch();

    expect(screen.getByText("No catalog products match that search.")).toBeInTheDocument();
  });

  it("distinguishes an empty catalog from a search with no matches", () => {
    render(
      <ProductDialog
        open
        products={[]}
        role="seller"
        onOpenChange={vi.fn()}
        onAdd={vi.fn(async () => undefined)}
      />,
    );

    const search = screen.getByPlaceholderText("Search products, SKUs, or categories…");
    expect(screen.getByText("No catalog products are available.")).toBeInTheDocument();

    fireEvent.change(search, { target: { value: "x" } });
    expect(screen.getByText("No catalog products match that search.")).toBeInTheDocument();
    expect(screen.queryByText("No catalog products are available.")).not.toBeInTheDocument();
  });

  it("keeps the dialog open and shows an inline error when adding a product fails", async () => {
    const onAdd = vi.fn().mockRejectedValue(new Error("write failed"));
    const onOpenChange = vi.fn();
    renderDialog(onAdd, onOpenChange);

    fireEvent.click(screen.getByText("Digital Intraoral Scanner"));
    await act(async () => undefined);

    expect(onAdd).toHaveBeenCalledWith(LOCAL_PRODUCTS[0]);
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Unable to add this product. Please try again.",
    );
    expect(screen.getByRole("dialog", { name: "Add product" })).toBeInTheDocument();
  });
});
