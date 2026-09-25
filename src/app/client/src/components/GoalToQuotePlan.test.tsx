import { TooltipProvider } from "@databricks/appkit-ui/react";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import type { DraftLineItem, QuotePlan, QuotePlanStatus, Recommendation } from "../types";
import { CopilotPanel } from "./CopilotPanel";

const LINE: DraftLineItem = {
  sku: "IMAGING-1",
  title: "Imaging system",
  category: "Imaging",
  quantity: 1,
  unit_price: 25_000,
};

const RECOMMENDATION: Recommendation = {
  summary: "Review the imaging configuration",
  items: [LINE],
  recommendation_id: "recommendation-1",
  revision: 3,
  draft_version: 4,
  apply_mode: "replace",
};

function quotePlan(status: QuotePlanStatus, overrides: Partial<QuotePlan> = {}): QuotePlan {
  return {
    plan_id: "plan-1",
    account_id: "account-1",
    draft_order_id: "draft-1",
    base_draft_version: 4,
    revision: 2,
    goal: "Build an imaging quote",
    status,
    steps: [
      { step_id: "step-1", title: "Confirm account context", status: "completed", sequence: 0 },
      { step_id: "step-2", title: "Review changes", status: "in_progress", sequence: 1 },
    ],
    scenarios: [{
      scenario_id: "scenario-1",
      title: "Recommended configuration",
      recommendation: RECOMMENDATION,
      recommendation_id: "recommendation-1",
      recommendation_revision: 3,
    }],
    selected_scenario_id: "scenario-1",
    action_proposal: {
      proposal_id: "proposal-1",
      action_type: "apply_scenario",
      summary: "Apply the recommended configuration",
      scenario_id: "scenario-1",
      recommendation_id: "recommendation-1",
      recommendation_revision: 3,
      draft_version: 4,
      plan_revision: 2,
      idempotency_key: "idem-1",
      confirmation: {
        token: "confirmation-token",
        token_id: "confirmation-1",
        idempotency_key: "idem-1",
        expires_at: "2099-09-14T20:00:00Z",
      },
      payload: { apply_mode: "replace" },
    },
    ...overrides,
  };
}

function renderPanel(options: {
  plan?: QuotePlan | null;
  planLoading?: boolean;
  currentLines?: DraftLineItem[];
  currentDraftVersion?: number;
  onSubmit?: (prompt: string) => Promise<void>;
  onPlanSelect?: (scenarioId: string) => Promise<void>;
  onPlanConfirm?: () => Promise<void>;
  onPlanCancel?: () => Promise<void>;
  onPlanReload?: () => Promise<void>;
} = {}) {
  return render(
    <TooltipProvider>
      <CopilotPanel
        messages={[]}
        stages={[]}
        currentLines={options.currentLines ?? []}
        currentDraftVersion={options.currentDraftVersion ?? 4}
        role="seller"
        activePlan={options.plan}
        planLoading={options.planLoading}
        onSubmit={options.onSubmit ?? vi.fn(async () => undefined)}
        onCancel={vi.fn()}
        onApply={vi.fn(async () => undefined)}
        onPlanSelect={options.onPlanSelect}
        onPlanConfirm={options.onPlanConfirm}
        onPlanCancel={options.onPlanCancel}
        onPlanReload={options.onPlanReload}
        onEvidence={vi.fn()}
      />
    </TooltipProvider>,
  );
}

const originalScrollIntoView = Object.getOwnPropertyDescriptor(Element.prototype, "scrollIntoView");

beforeAll(() => {
  Object.defineProperty(Element.prototype, "scrollIntoView", { configurable: true, value: vi.fn() });
  vi.stubGlobal("ResizeObserver", class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  });
});

afterAll(() => {
  vi.unstubAllGlobals();
  if (originalScrollIntoView) Object.defineProperty(Element.prototype, "scrollIntoView", originalScrollIntoView);
  else delete (Element.prototype as Partial<Element>).scrollIntoView;
});

describe("minimal goal-to-quote presentation", () => {
  it("keeps plan loading inside the conversation without changing the header or composer", () => {
    const { container } = renderPanel({ planLoading: true });

    const loading = screen.getByRole("status", { name: "Loading quote plan" });
    expect(loading).toBe(container.querySelector(".conversation-log .quote-plan-skeleton"));
    expect(screen.getByRole("heading", { name: "Genie" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message Genie" })).toBeInTheDocument();
    expect(screen.queryByText("Ask about this quote or request changes.")).not.toBeInTheDocument();
    expect(container.querySelector(".dynamic-prompts")).not.toBeInTheDocument();
  });

  it("reuses the compact progress row and exposes cancellation while planning", async () => {
    const user = userEvent.setup();
    const onPlanCancel = vi.fn(async () => undefined);
    const { container } = renderPanel({ plan: quotePlan("planning"), onPlanCancel });

    expect(screen.getByRole("status", { name: "Quote plan progress" })).toHaveTextContent("Building quote options…");
    expect(screen.getByRole("status", { name: "Quote plan progress" })).toHaveTextContent("1 of 2 · Next: Review changes");
    expect(container.querySelector(".dynamic-prompts")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel plan" }));
    expect(onPlanCancel).toHaveBeenCalledOnce();
  });

  it("shows one grounded clarification and leaves the existing composer available", () => {
    const { container } = renderPanel({
      plan: quotePlan("needs_input", { metadata: { clarifying_question: "How many operatories should this cover?" } }),
    });

    expect(screen.getByRole("status", { name: "Quote plan needs input" })).toHaveTextContent(
      "How many operatories should this cover?",
    );
    expect(screen.getByRole("textbox", { name: "Message Genie" })).toBeEnabled();
    expect(container.querySelector(".dynamic-prompts")).not.toBeInTheDocument();
  });

  it("uses the existing recommendation card for ready review and confirmation", async () => {
    const user = userEvent.setup();
    const onPlanConfirm = vi.fn(async () => undefined);
    const onPlanCancel = vi.fn(async () => undefined);
    const { container } = renderPanel({ plan: quotePlan("ready"), onPlanConfirm, onPlanCancel });

    const review = screen.getByLabelText("Quote plan review");
    expect(review).toBe(container.querySelector(".conversation-log .quote-plan-review"));
    expect(within(review).getByRole("heading", { name: "Review the imaging configuration" })).toBeInTheDocument();
    expect(within(review).getByText("1 of 2 complete · Next: Review changes")).toBeInTheDocument();
    expect(within(review).getByText("Quote total")).toBeInTheDocument();
    expect(within(review).queryByText(/task center|workflow|agent answer/i)).not.toBeInTheDocument();
    expect(container.querySelector(".copilot-header .quote-plan-review")).not.toBeInTheDocument();

    await user.click(within(review).getByRole("button", { name: "Confirm & apply" }));
    expect(onPlanConfirm).toHaveBeenCalledOnce();
    await user.click(within(review).getByRole("button", { name: "Cancel plan" }));
    expect(onPlanCancel).toHaveBeenCalledOnce();
  });

  it("shows the scenario selector only when the plan has real alternatives", async () => {
    const user = userEvent.setup();
    const onPlanSelect = vi.fn(async () => undefined);
    const second = {
      scenario_id: "scenario-2",
      title: "Lower upfront cost",
      recommendation: { ...RECOMMENDATION, summary: "Review the lower-cost configuration" },
      recommendation_id: "recommendation-2",
      recommendation_revision: 1,
    };
    renderPanel({
      plan: quotePlan("ready", {
        scenarios: [...(quotePlan("ready").scenarios ?? []), second],
      }),
      onPlanSelect,
    });

    screen.getByRole("combobox", { name: "Quote plan option" }).focus();
    await user.keyboard("{Enter}");
    await user.click(screen.getByRole("option", { name: "Lower upfront cost" }));
    expect(onPlanSelect).toHaveBeenCalledWith("scenario-2");
  });

  it("expires an open confirmation and reloads it without submitting a new planning prompt", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2030-01-01T00:00:00Z"));
    try {
      const onSubmit = vi.fn(async () => undefined);
      const onPlanReload = vi.fn(async () => undefined);
      renderPanel({
        plan: quotePlan("ready", {
          action_proposal: {
            ...quotePlan("ready").action_proposal!,
            confirmation: {
              ...quotePlan("ready").action_proposal!.confirmation!,
              expires_at: "2030-01-01T00:00:01Z",
            },
          },
        }),
        onSubmit,
        onPlanReload,
      });

      expect(screen.getByRole("button", { name: "Confirm & apply" })).toBeEnabled();
      act(() => vi.advanceTimersByTime(1_000));
      expect(screen.getByRole("button", { name: "Confirmation expired" })).toBeDisabled();
      expect(screen.getByText("Confirmation expired. Refresh before applying.")).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "Refresh confirmation" }));
      expect(onPlanReload).toHaveBeenCalledOnce();
      expect(onSubmit).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("surfaces stale and failed plans without exposing internal agent taxonomy", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(async () => undefined);
    const { rerender } = renderPanel({ plan: quotePlan("stale"), currentDraftVersion: 5, onSubmit });

    expect(screen.getByText("The quote changed. Update this proposal before applying.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Update proposal" }));
    expect(onSubmit).toHaveBeenCalledWith("Update this plan for the current quote.");

    rerender(
      <TooltipProvider>
        <CopilotPanel
          messages={[]}
          stages={[]}
          currentLines={[]}
          currentDraftVersion={4}
          role="seller"
          activePlan={quotePlan("failed", { error_message: "Pricing data was unavailable. Your quote was not changed." })}
          onSubmit={onSubmit}
          onCancel={vi.fn()}
          onApply={vi.fn(async () => undefined)}
          onEvidence={vi.fn()}
        />
      </TooltipProvider>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Pricing data was unavailable. Your quote was not changed.");
    expect(screen.queryByText(/supervisor|tool call|chain of thought/i)).not.toBeInTheDocument();
  });

  it("collapses a completed, authoritative plan to the existing applied state", () => {
    renderPanel({ plan: quotePlan("completed"), currentLines: [LINE] });

    expect(screen.getByText("Applied to quote")).toBeInTheDocument();
    expect(screen.getByText("Current total $25,000")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm & apply" })).not.toBeInTheDocument();
    expect(screen.getAllByText(/AI-generated/i)).toHaveLength(1);
  });

  it("uses the live quote total for a completed additive plan even when canonical pricing differs", () => {
    const canonicalLine = { ...LINE, unit_price: 24_500 };
    renderPanel({
      plan: quotePlan("completed", {
        metadata: { applied_draft_version: 5 },
        scenarios: [{
          ...(quotePlan("completed").scenarios ?? [])[0],
          recommendation: { ...RECOMMENDATION, apply_mode: "add" },
        }],
        action_proposal: null,
      }),
      currentLines: [canonicalLine],
      currentDraftVersion: 5,
    });

    expect(screen.getByText("Applied to quote")).toBeInTheDocument();
    expect(screen.getByText("Current total $24,500")).toBeInTheDocument();
    expect(screen.queryByText(/quote changed/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /apply|update proposal/i })).not.toBeInTheDocument();
  });

  it("shows an approval-gated applied plan without calling it stale", () => {
    const secondScenario = {
      scenario_id: "scenario-2",
      title: "Lower upfront cost",
      recommendation: { ...RECOMMENDATION, summary: "Review the lower-cost configuration" },
      recommendation_id: "recommendation-2",
      recommendation_revision: 1,
    };
    renderPanel({
      plan: quotePlan("awaiting_approval", {
        metadata: { applied_draft_version: 5 },
        action_proposal: null,
        scenarios: [...(quotePlan("awaiting_approval").scenarios ?? []), secondScenario],
      }),
      currentLines: [LINE],
      currentDraftVersion: 5,
    });

    expect(screen.getByText("Approval required")).toBeInTheDocument();
    expect(screen.getByText(/confirmed changes are in the quote/i)).toBeInTheDocument();
    expect(screen.getByText("Applied to quote")).toBeInTheDocument();
    expect(screen.queryByText(/quote changed/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel plan" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Quote plan option" })).not.toBeInTheDocument();
  });
});
