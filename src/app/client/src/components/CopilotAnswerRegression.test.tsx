import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import type { ConversationMessage, Evidence } from "../types";
import { CopilotPanel } from "./CopilotPanel";

const EVIDENCE: Evidence = {
  citations: [],
  sql: "select governed_answer",
  columns: [],
  rows: [],
  checks: [],
  freshness: [],
  tools: ["genie"],
  truncated: false,
};

function answer(error = false): ConversationMessage {
  return {
    id: error ? "partial-answer" : "normal-answer",
    role: "assistant",
    kind: "answer",
    content: error ? "Some governed results were unavailable." : "Revenue increased by twelve percent.",
    evidence: EVIDENCE,
    error,
  };
}

function renderAnswer(message: ConversationMessage, onEvidence = vi.fn()) {
  render(
      <CopilotPanel
        messages={[message]}
        stages={[]}
        currentLines={[]}
      role="seller"
      onSubmit={vi.fn(async () => undefined)}
      onCancel={vi.fn()}
      onApply={vi.fn(async () => undefined)}
      onEvidence={onEvidence}
    />,
  );
}

const originalScrollIntoView = Object.getOwnPropertyDescriptor(Element.prototype, "scrollIntoView");

beforeAll(() => {
  Object.defineProperty(Element.prototype, "scrollIntoView", {
    configurable: true,
    value: vi.fn(),
  });
  vi.stubGlobal("ResizeObserver", class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  });
});

afterAll(() => {
  vi.unstubAllGlobals();
  if (originalScrollIntoView) {
    Object.defineProperty(Element.prototype, "scrollIntoView", originalScrollIntoView);
  } else {
    delete (Element.prototype as Partial<Element>).scrollIntoView;
  }
});

describe("CopilotPanel answer cards", () => {
  it("renders a normal answer without redundant chrome and keeps evidence accessible", async () => {
    const user = userEvent.setup();
    const onEvidence = vi.fn();
    renderAnswer(answer(), onEvidence);

    const copy = screen.getByText("Revenue increased by twelve percent.");
    const card = copy.closest(".message-answer");
    expect(card).not.toBeNull();

    const answerCard = within(card as HTMLElement);
    expect(answerCard.queryByText("Genie", { exact: true })).not.toBeInTheDocument();
    expect(answerCard.queryByText("Answer", { exact: true })).not.toBeInTheDocument();
    expect(answerCard.queryByRole("heading", { name: "Agent answer" })).not.toBeInTheDocument();
    expect(answerCard.queryByText(/AI-generated/i)).not.toBeInTheDocument();
    expect(screen.getAllByText("AI-generated. Review Details for sources and query.", { exact: true })).toHaveLength(1);
    expect(screen.queryByText("AI-generated · verify", { exact: true })).not.toBeInTheDocument();
    expect(document.querySelector(".copilot-governance")).not.toBeInTheDocument();

    await user.click(answerCard.getByRole("button", { name: "Details" }));
    expect(onEvidence).toHaveBeenCalledOnce();
    expect(onEvidence).toHaveBeenCalledWith(EVIDENCE);
  });

  it("retains a clear destructive status for a partial answer", () => {
    renderAnswer(answer(true));

    const copy = screen.getByText("Some governed results were unavailable.");
    const card = copy.closest(".message-answer");
    expect(card).not.toBeNull();

    const partial = within(card as HTMLElement).getByText("Some information unavailable", { exact: true });
    expect(partial).toHaveAttribute("data-slot", "badge");
    expect(partial).toHaveClass("bg-destructive");
  });

  it("renders a quote recommendation without stacked assistant labels", () => {
    renderAnswer({
      id: "recommendation",
      role: "assistant",
      kind: "recommendation",
      recommendation: {
        summary: "Add an imaging system",
        recommendation_id: "recommendation-1",
        revision: 1,
        items: [{
          sku: "IMAGING-1",
          title: "Imaging system",
          category: "Imaging",
          quantity: 1,
          unit_price: 25_000,
        }],
      },
      evidence: EVIDENCE,
    });

    const recommendation = screen.getByRole("heading", { name: "Add an imaging system" })
      .closest(".message-recommendation");
    expect(recommendation).not.toBeNull();
    const result = within(recommendation as HTMLElement);
    expect(result.queryByText("Genie", { exact: true })).not.toBeInTheDocument();
    expect(result.queryByText("Quote action", { exact: true })).not.toBeInTheDocument();
    expect(result.queryByText("Recommended next quote", { exact: true })).not.toBeInTheDocument();
    expect(result.queryByText("Ready", { exact: true })).not.toBeInTheDocument();
    expect(result.queryByText(/AI-generated/i)).not.toBeInTheDocument();
    expect(screen.getAllByText("AI-generated. Review Details for sources and query.", { exact: true })).toHaveLength(1);
    expect(screen.queryByText("AI-generated · verify", { exact: true })).not.toBeInTheDocument();
  });
});
