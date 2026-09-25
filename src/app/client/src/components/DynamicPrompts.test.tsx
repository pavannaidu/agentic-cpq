import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { ConversationMessage, DraftLineItem } from "../types";

const mocks = vi.hoisted(() => ({ followups: vi.fn() }));

vi.mock("../api", () => ({ api: { followups: mocks.followups } }));

import { CopilotPanel } from "./CopilotPanel";

beforeAll(() => {
  vi.stubGlobal("ResizeObserver", class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  });
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
    configurable: true,
    value: vi.fn(),
  });
});

afterAll(() => vi.unstubAllGlobals());

beforeEach(() => mocks.followups.mockReset());

const LINE: DraftLineItem = {
  sku: "CHAIR-1",
  title: "Operatory chair",
  category: "Equipment",
  quantity: 1,
  unit_price: 25_000,
  approval_required: true,
  approval_reason: "Manager review required",
};

const ANSWER: ConversationMessage = {
  id: "answer-1",
  role: "assistant",
  kind: "answer",
  content: "This quote needs manager approval.",
  evidence: { citations: [], sql: "", columns: [], rows: [], checks: [], freshness: [], tools: [], truncated: false },
};

function renderPanel({
  accountId = "account-1",
  draftOrderId = "draft-1",
  currentDraftVersion = 1,
  currentLines = [LINE],
  messages = [],
  onSubmit = vi.fn(async () => undefined),
}: {
  accountId?: string;
  draftOrderId?: string;
  currentDraftVersion?: number;
  currentLines?: DraftLineItem[];
  messages?: ConversationMessage[];
  onSubmit?: (prompt: string) => Promise<void>;
} = {}) {
  const props = {
    accountId,
    draftOrderId,
    currentDraftStatus: "draft",
    currentDraftVersion,
    currentLines,
    messages,
    stages: [],
    role: "seller" as const,
    onSubmit,
    onCancel: vi.fn(),
    onApply: vi.fn(async () => undefined),
    onEvidence: vi.fn(),
  };
  return { props, onSubmit, ...render(<CopilotPanel {...props} />) };
}

describe("dynamic Genie prompts", () => {
  it("clears composer text when the active draft changes", async () => {
    mocks.followups.mockResolvedValue({ suggestions: [] });
    const { props, rerender } = renderPanel();
    const composer = screen.getByRole("textbox", { name: "Message Genie" });

    fireEvent.change(composer, { target: { value: "Apply this to the old quote" } });
    expect(composer).toHaveValue("Apply this to the old quote");

    rerender(<CopilotPanel {...props} draftOrderId="draft-2" />);

    await waitFor(() => expect(screen.getByRole("textbox", { name: "Message Genie" })).toHaveValue(""));
  });

  it("shows model-generated prompts and submits the exact clicked text", async () => {
    const suggestions = [
      "Review approval blockers for this quote",
      "Check account-specific pricing",
      "Draft a customer-ready summary",
      "Identify the best next action",
    ];
    mocks.followups.mockResolvedValue({ suggestions });
    const onSubmit = vi.fn(async () => undefined);

    renderPanel({ onSubmit });

    const group = await screen.findByRole("group", { name: "Suggested prompts" });
    expect(group).toBeInTheDocument();
    expect(screen.getAllByRole("button").filter((button) => suggestions.includes(button.textContent ?? ""))).toHaveLength(4);
    expect(mocks.followups).toHaveBeenCalledWith(
      "draft-1",
      "account-1",
      "seller",
      expect.any(AbortSignal),
    );

    fireEvent.click(screen.getByRole("button", { name: suggestions[0] }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(suggestions[0]));
  });

  it("refreshes for conversation and quote-context changes", async () => {
    mocks.followups
      .mockResolvedValueOnce({ suggestions: ["Build the initial quote"] })
      .mockResolvedValueOnce({ suggestions: ["Resolve the approval requirement"] })
      .mockResolvedValueOnce({ suggestions: ["Review the updated line pricing"] });
    const { props, rerender } = renderPanel();
    await screen.findByRole("button", { name: "Build the initial quote" });

    rerender(<CopilotPanel {...props} messages={[ANSWER]} />);
    await screen.findByRole("button", { name: "Resolve the approval requirement" });

    rerender(
      <CopilotPanel
        {...props}
        messages={[ANSWER]}
        currentDraftVersion={2}
        currentLines={[{ ...LINE, unit_price: 24_000, approval_required: false }]}
      />,
    );
    await screen.findByRole("button", { name: "Review the updated line pricing" });
    expect(mocks.followups).toHaveBeenCalledTimes(3);
  });

  it("aborts stale requests so older account prompts cannot replace the active account", async () => {
    const first = deferred<{ suggestions: string[] }>();
    const second = deferred<{ suggestions: string[] }>();
    mocks.followups
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise);
    const { props, rerender } = renderPanel();
    await waitFor(() => expect(mocks.followups).toHaveBeenCalledTimes(1));
    const firstSignal = mocks.followups.mock.calls[0][3] as AbortSignal;

    rerender(<CopilotPanel {...props} accountId="account-2" draftOrderId="draft-2" />);
    await waitFor(() => expect(mocks.followups).toHaveBeenCalledTimes(2));
    expect(firstSignal.aborted).toBe(true);

    await act(async () => second.resolve({ suggestions: ["Review account two pricing"] }));
    expect(await screen.findByRole("button", { name: "Review account two pricing" })).toBeInTheDocument();
    await act(async () => first.resolve({ suggestions: ["Review stale account pricing"] }));
    expect(screen.queryByRole("button", { name: "Review stale account pricing" })).not.toBeInTheDocument();
  });

  it("uses a restrained recoverable state without static prompt fallbacks", async () => {
    mocks.followups.mockResolvedValue({ suggestions: [] });

    renderPanel();

    expect(await screen.findByText("No tailored suggestions yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Suggested prompts" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /generate.*pdf/i })).not.toBeInTheDocument();
  });
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => { resolve = promiseResolve; });
  return { promise, resolve };
}
