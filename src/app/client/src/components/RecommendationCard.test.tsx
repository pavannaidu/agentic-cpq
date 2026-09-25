import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { DraftLineItem, Evidence, Recommendation } from "../types";
import { RecommendationCard } from "./RecommendationCard";

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

function line(sku: string, price: number): DraftLineItem {
  return {
    sku,
    title: `Product ${sku}`,
    category: "Equipment",
    quantity: 1,
    unit_price: price,
  };
}

function recommendation(items: DraftLineItem[], applyMode: "add" | "replace" = "add"): Recommendation {
  return {
    summary: "A governed recommendation",
    items,
    apply_mode: applyMode,
    recommendation_id: "recommendation-1",
    revision: 1,
  };
}

describe("RecommendationCard", () => {
  it("applies an additive recommendation and opens its evidence", async () => {
    const user = userEvent.setup();
    const onApply = vi.fn(async () => undefined);
    const onEvidence = vi.fn();
    const proposed = line("NEW", 500);
    render(
      <RecommendationCard
        recommendation={recommendation([proposed])}
        currentLines={[]}
        role="seller"
        onApply={onApply}
        onEvidence={onEvidence}
        evidence={EVIDENCE}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Apply 1 change" }));
    expect(onApply).toHaveBeenCalledOnce();
    expect(onApply).toHaveBeenCalledWith();

    await user.click(screen.getByRole("button", { name: "Details" }));
    expect(onEvidence).toHaveBeenCalledWith(EVIDENCE);
    expect(screen.getByRole("heading", { name: "A governed recommendation" })).toBeInTheDocument();
    expect(screen.queryByText("Ready", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText("Recommended next quote", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText(/AI-generated/i)).not.toBeInTheDocument();
  });

  it("requires confirmation before replacing existing quote lines", async () => {
    const user = userEvent.setup();
    const onApply = vi.fn(async () => undefined);
    const oldLine = line("OLD", 250);
    const newLine = line("NEW", 500);
    render(
      <RecommendationCard
        recommendation={recommendation([newLine], "replace")}
        currentLines={[oldLine]}
        role="seller"
        onApply={onApply}
        onEvidence={vi.fn()}
        evidence={EVIDENCE}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Apply 2 changes" }));
    expect(onApply).not.toHaveBeenCalled();
    expect(screen.getByRole("alertdialog", { name: "Replace the current quote?" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Replace and apply" }));
    expect(onApply).toHaveBeenCalledOnce();
    expect(onApply).toHaveBeenCalledWith();
  });

  it("disables apply when the quote already matches", () => {
    const matching = line("MATCH", 100);
    render(
      <RecommendationCard
        recommendation={recommendation([matching])}
        currentLines={[matching]}
        role="seller"
        onApply={vi.fn(async () => undefined)}
        onEvidence={vi.fn()}
        evidence={EVIDENCE}
      />,
    );

    expect(screen.getByRole("button", { name: "Quote already matches" })).toBeDisabled();
  });

  it("keeps evidence available but prevents applying a recommendation without identity metadata", async () => {
    const user = userEvent.setup();
    const onApply = vi.fn(async () => undefined);
    const onEvidence = vi.fn();
    render(
      <RecommendationCard
        recommendation={{ ...recommendation([line("NEW", 500)]), recommendation_id: undefined }}
        currentLines={[]}
        role="seller"
        onApply={onApply}
        onEvidence={onEvidence}
        evidence={EVIDENCE}
      />,
    );

    expect(screen.getByRole("button", { name: "Regenerate to apply" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Details" }));
    expect(onEvidence).toHaveBeenCalledWith(EVIDENCE);
    expect(onApply).not.toHaveBeenCalled();
  });
});
