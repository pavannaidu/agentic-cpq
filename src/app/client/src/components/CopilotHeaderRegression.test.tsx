import { render, screen, within } from "@testing-library/react";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { CopilotPanel } from "./CopilotPanel";

beforeAll(() => {
  vi.stubGlobal("ResizeObserver", class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  });
});

afterAll(() => vi.unstubAllGlobals());

function renderEmptyState(
  onSubmit = vi.fn(async (_prompt: string) => undefined),
) {
  return {
    onSubmit,
    ...render(
        <CopilotPanel
          messages={[]}
          stages={[]}
          currentLines={[]}
        role="seller"
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        onApply={vi.fn(async () => undefined)}
        onEvidence={vi.fn()}
      />,
    ),
  };
}

describe("CopilotPanel header", () => {
  it("uses one concise Genie identity without claiming web provenance", () => {
    const { container } = render(
      <CopilotPanel
        messages={[]}
        stages={[]}
        currentLines={[]}
        role="seller"
        onSubmit={vi.fn(async () => undefined)}
        onCancel={vi.fn()}
        onApply={vi.fn(async () => undefined)}
        onEvidence={vi.fn()}
      />,
    );

    const heading = screen.getByRole("heading", { name: "Genie" });
    const header = heading.closest("header");
    expect(header).not.toBeNull();
    expect(within(header as HTMLElement).queryByText(
      "Quotes and governed sales answers.",
    )).not.toBeInTheDocument();
    expect((header as HTMLElement).querySelector('[data-slot="badge"]')).not.toBeInTheDocument();

    expect(screen.queryByText("Genie + Web", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText("Genie data + current web research", { exact: true })).not.toBeInTheDocument();
    expect(container.querySelector(".copilot-workspace")).toHaveAccessibleName("Genie");
  });

  it("uses the concise quote-first composer prompt", () => {
    renderEmptyState();

    expect(screen.getByRole("textbox", { name: "Message Genie" })).toHaveAttribute(
      "placeholder",
      "Message Genie…",
    );
  });

  it("keeps the empty state focused on one concise instruction", () => {
    const { container } = renderEmptyState();
    const emptyState = container.querySelector(".copilot-empty-state");
    const composer = container.querySelector(".copilot-composer");

    expect(emptyState).not.toBeNull();
    expect(within(emptyState as HTMLElement).getByText(
      "Ask about this quote or request changes.",
    )).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Suggested" })).not.toBeInTheDocument();
    expect(container.querySelector(".guided-start")).not.toBeInTheDocument();

    expect(composer).not.toBeNull();
    expect(within(composer as HTMLElement).getByText(
      "AI-generated. Review Details for sources and query.",
    )).toBeInTheDocument();
    expect(screen.getAllByText(/AI-generated/i)).toHaveLength(1);
    expect(within(emptyState as HTMLElement).queryByText(/AI-generated/i)).not.toBeInTheDocument();
  });
});
