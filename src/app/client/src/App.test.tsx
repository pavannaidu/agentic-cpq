import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, type AgentRequest } from "./api";
import type { ConversationMessage, DraftOrder, Evidence, QuotePlan, ViewRole } from "./types";

const mocks = vi.hoisted(() => ({
  bootstrap: vi.fn(),
  me: vi.fn(),
  createDraft: vi.fn(),
  saveDraft: vi.fn(),
  resumeDraft: vi.fn(),
  getDraft: vi.fn(),
  activePlan: vi.fn(),
  resumePlan: vi.fn(),
  selectPlanScenario: vi.fn(),
  cancelPlan: vi.fn(),
  confirmPlanApply: vi.fn(),
  agentQuery: vi.fn(),
  streamAgent: vi.fn(),
}));

vi.mock("./api", () => ({
  ApiError: class ApiError extends Error {
    constructor(message: string, readonly status: number) {
      super(message);
    }
  },
  api: {
    bootstrap: mocks.bootstrap,
    me: mocks.me,
    createDraft: mocks.createDraft,
    saveDraft: mocks.saveDraft,
    resumeDraft: mocks.resumeDraft,
    getDraft: mocks.getDraft,
    activePlan: mocks.activePlan,
    resumePlan: mocks.resumePlan,
    selectPlanScenario: mocks.selectPlanScenario,
    cancelPlan: mocks.cancelPlan,
    confirmPlanApply: mocks.confirmPlanApply,
    agentQuery: mocks.agentQuery,
  },
  streamAgent: mocks.streamAgent,
}));

vi.mock("./hooks/useCompactLayout", () => ({ useCompactLayout: () => true }));

vi.mock("./components/WorkspaceHeader", () => ({
  WorkspaceHeader: ({
    role,
    onRoleChange,
    onNewQuote,
    newQuoteDisabled,
  }: {
    role: ViewRole;
    onRoleChange: (role: ViewRole) => void;
    onNewQuote: () => void;
    newQuoteDisabled?: boolean;
  }) => (
    <div>
      <span data-testid="active-role">{role}</span>
      <span data-testid="new-quote-disabled">{String(Boolean(newQuoteDisabled))}</span>
      <button type="button" disabled={newQuoteDisabled} onClick={onNewQuote}>New quote</button>
      <button type="button" onClick={() => onRoleChange("seller")}>Switch to seller</button>
    </div>
  ),
}));

vi.mock("./components/CopilotPanel", () => ({
  CopilotPanel: ({
    messages,
    activePlan,
    onSubmit,
    onPlanConfirm,
    onPlanReload,
    onEvidence,
  }: {
    messages: ConversationMessage[];
    activePlan?: QuotePlan | null;
    onSubmit: (prompt: string) => Promise<void>;
    onPlanConfirm?: () => Promise<void>;
    onPlanReload?: () => Promise<void>;
    onEvidence: (evidence: Evidence) => void;
  }) => {
    const answer = messages.find((message) => message.role === "assistant" && message.kind === "answer");
    const error = messages.find((message) => message.role === "assistant" && message.kind === "error");
    return (
      <div>
        <span data-testid="message-count">{messages.length}</span>
        <span data-testid="plan-status">{activePlan?.status ?? "none"}</span>
        <button type="button" onClick={() => void onSubmit("Show account performance")}>Ask Copilot</button>
        {activePlan?.status === "ready" && <button type="button" onClick={() => void onPlanConfirm?.()}>Confirm plan</button>}
        {activePlan?.status === "ready" && <button type="button" onClick={() => void onPlanReload?.()}>Reload plan</button>}
        {answer?.role === "assistant" && answer.kind === "answer" && (
          <button type="button" onClick={() => onEvidence(answer.evidence)}>Open evidence</button>
        )}
        {error?.role === "assistant" && error.kind === "error" && (
          <div>
            <span>{error.content}</span>
            {error.retryPrompt && <button type="button" onClick={() => void onSubmit(error.retryPrompt ?? "")}>Retry</button>}
          </div>
        )}
      </div>
    );
  },
}));

vi.mock("./components/QuotePanel", () => ({
  QuotePanel: ({ draft }: { draft: DraftOrder | null }) => (
    <div>
      <span data-testid="draft-id">{draft?.draft_order_id}</span>
      <span data-testid="draft-status">{draft?.status}</span>
      <span data-testid="draft-version">{draft?.version}</span>
      <span data-testid="draft-revision">{draft?.revision_number}</span>
      <span data-testid="draft-line-count">{draft?.line_items.length ?? 0}</span>
      <span data-testid="draft-parent">{draft?.parent_draft_order_id ?? "none"}</span>
      <span data-testid="draft-source">{draft?.source_quote_id ?? "none"}</span>
    </div>
  ),
}));
vi.mock("./components/EvidencePanel", () => ({
  EvidencePanel: ({ open, evidence }: { open: boolean; evidence: Evidence | null }) => open
    ? <div data-testid="evidence-panel">{evidence?.sql}</div>
    : null,
}));
vi.mock("./components/HistoryPanel", () => ({
  HistoryPanel: ({ onLoadDraft }: { onLoadDraft: (draft: DraftOrder) => Promise<void> }) => (
    <button type="button" onClick={() => void onLoadDraft({
      draft_order_id: "draft-history",
      account_id: "account-1",
      status: "saved",
      line_items: [],
      subtotal: 0,
      grand_total: 0,
      version: 3,
      revision_number: 1,
    })}>Load historical quote</button>
  ),
}));
vi.mock("./components/ProductDialog", () => ({ ProductDialog: () => null }));

import App from "./App";

const MANAGER_DRAFT: DraftOrder = {
  draft_order_id: "draft-1",
  account_id: "account-1",
  status: "draft",
  line_items: [],
  subtotal: 0,
  grand_total: 0,
  version: 17,
};

const SELLER_DRAFT: DraftOrder = {
  ...MANAGER_DRAFT,
  version: 18,
};

const QUOTE_LINE = {
  sku: "IMAGING-CHAIR",
  title: "Imaging Chair",
  category: "Imaging",
  quantity: 1,
  unit_price: 12_500,
  total_price: 12_500,
};

const WORKING_DRAFT: DraftOrder = {
  ...MANAGER_DRAFT,
  draft_order_id: "draft-working",
  line_items: [QUOTE_LINE],
  subtotal: 12_500,
  grand_total: 12_500,
  revision_number: 1,
};

const NEW_BLANK_DRAFT: DraftOrder = {
  ...MANAGER_DRAFT,
  draft_order_id: "draft-new-blank",
  version: 1,
  revision_number: 1,
  parent_draft_order_id: null,
  source_quote_id: null,
};

const ACTIVE_DRAFT_STORAGE_KEY = "agentic-cpq-active-draft:v1:manager:account-1";
const ACTIVE_ACCOUNT_STORAGE_KEY = "agentic-cpq-active-account:v1:manager";

const storageState = new Map<string, string>();
const storageMock: Storage = {
  get length() { return storageState.size; },
  clear: () => storageState.clear(),
  getItem: (key) => storageState.get(key) ?? null,
  key: (index) => [...storageState.keys()][index] ?? null,
  removeItem: (key) => { storageState.delete(key); },
  setItem: (key, value) => { storageState.set(key, String(value)); },
};

function quotePlan(status: QuotePlan["status"]): QuotePlan {
  return {
    plan_id: "plan-1",
    account_id: "account-1",
    draft_order_id: "draft-1",
    base_draft_version: 17,
    revision: 2,
    goal: "Build an imaging quote",
    status,
    scenarios: [],
    action_proposal: status === "ready" ? {
      proposal_id: "proposal-1",
      action_type: "apply_scenario",
      summary: "Apply the selected quote",
      draft_version: 17,
      plan_revision: 2,
      idempotency_key: "idem-1",
      confirmation: {
        token: "token-1",
        token_id: "token-id-1",
        idempotency_key: "idem-1",
        expires_at: "2099-09-14T20:00:00Z",
      },
    } : null,
  };
}

describe("App role-scoped agent state", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    storageState.clear();
    vi.stubGlobal("localStorage", storageMock);
    mocks.bootstrap.mockResolvedValue({
      default_account_id: "account-1",
      accounts: [{ account_id: "account-1", name: "River Dental" }],
      sample_prompts: [],
      source_freshness: [],
      product_snapshot: [],
    });
    mocks.me.mockResolvedValue({
      username: "Manager",
      authenticated: true,
      allowed_views: ["seller", "manager"],
      default_view: "manager",
      execution_identity: "service_principal",
    });
    mocks.createDraft.mockResolvedValue(MANAGER_DRAFT);
    mocks.saveDraft.mockResolvedValue({ ...MANAGER_DRAFT, status: "saved" });
    mocks.resumeDraft.mockResolvedValue({ draft: null });
    mocks.activePlan.mockResolvedValue(null);
    mocks.agentQuery.mockRejectedValue(new Error("Agent query fallback should not run in this test."));
    mocks.streamAgent.mockImplementation(async (_request, _signal, onEvent) => {
      onEvent({
        event: "conversation",
        data: {
          answer: "Manager-only account analysis",
          sql: "select manager_margin from governed_sales",
          conversation_id: "manager-conversation",
        },
      });
    });
  });

  it("keeps the Databricks attribution in the global footer", async () => {
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("active-role")).toHaveTextContent("manager"));
    expect(mocks.activePlan).toHaveBeenCalledWith("draft-1", "manager");
    expect(screen.getByRole("contentinfo", { name: "Platform attribution" })).toHaveTextContent(
      "Powered by Databricks",
    );
  });

  it("turns an empty Genie response into a retryable error", async () => {
    mocks.streamAgent
      .mockImplementationOnce(async (_request, _signal, onEvent) => {
        onEvent({ event: "conversation", data: { answer: "   " } });
      })
      .mockImplementationOnce(async (_request, _signal, onEvent) => {
        onEvent({ event: "conversation", data: { answer: "Quote updated." } });
      });
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("active-role")).toHaveTextContent("manager"));
    fireEvent.click(screen.getByRole("button", { name: "Ask Copilot" }));

    expect(await screen.findByText("Genie didn't return a usable response. Try again.")).toBeInTheDocument();
    expect(screen.queryByText("No answer was returned.")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(mocks.streamAgent).toHaveBeenCalledTimes(2));
  });

  it("keeps manager context until the seller projection succeeds, then clears all scoped conversation state", async () => {
    let resolveSellerDraft: (draft: DraftOrder) => void = () => undefined;
    mocks.getDraft.mockReturnValueOnce(new Promise<DraftOrder>((resolve) => { resolveSellerDraft = resolve; }));
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("active-role")).toHaveTextContent("manager"));
    fireEvent.click(screen.getByRole("button", { name: "Ask Copilot" }));
    await waitFor(() => expect(screen.getByTestId("message-count")).toHaveTextContent("2"));
    expect((mocks.streamAgent.mock.calls[0]?.[0] as AgentRequest).expected_revision).toBe(17);

    fireEvent.click(screen.getByRole("button", { name: "Open evidence" }));
    expect(screen.getByTestId("evidence-panel")).toHaveTextContent("manager_margin");

    fireEvent.click(screen.getByRole("button", { name: "Switch to seller" }));
    await waitFor(() => expect(mocks.getDraft).toHaveBeenCalledWith("draft-1", "seller"));
    expect(screen.getByTestId("active-role")).toHaveTextContent("manager");
    expect(screen.getByTestId("message-count")).toHaveTextContent("2");
    expect(screen.getByTestId("evidence-panel")).toBeInTheDocument();

    await act(async () => { resolveSellerDraft(SELLER_DRAFT); });
    await waitFor(() => expect(screen.getByTestId("active-role")).toHaveTextContent("seller"));
    expect(screen.getByTestId("message-count")).toHaveTextContent("0");
    expect(screen.queryByTestId("evidence-panel")).not.toBeInTheDocument();
    expect(screen.getByTestId("draft-version")).toHaveTextContent("18");

    fireEvent.click(screen.getByRole("button", { name: "Ask Copilot" }));
    await waitFor(() => expect(mocks.streamAgent).toHaveBeenCalledTimes(2));
    const sellerRequest = mocks.streamAgent.mock.calls[1]?.[0] as AgentRequest;
    expect(sellerRequest).toMatchObject({
      view_role: "seller",
      expected_revision: 18,
      genie_conversation_id: null,
      conversation_history: [],
      recommendation_context: {},
    });
  });

  it("confirms before history replaces an unsaved revision", async () => {
    mocks.resumeDraft.mockResolvedValueOnce({
      draft: {
        ...MANAGER_DRAFT,
        revision_number: 2,
        parent_draft_order_id: "draft-sent",
        source_quote_id: "PPQ-1",
      },
    });
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("draft-version")).toHaveTextContent("17"));
    fireEvent.click(screen.getByRole("button", { name: "Load historical quote" }));

    expect(screen.getByRole("alertdialog", { name: "Load another quote before saving?" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Keep editing" }));
    expect(screen.getByTestId("draft-version")).toHaveTextContent("17");

    fireEvent.click(screen.getByRole("button", { name: "Load historical quote" }));
    fireEvent.click(screen.getByRole("button", { name: "Load anyway" }));
    await waitFor(() => expect(screen.getByTestId("draft-version")).toHaveTextContent("3"));
  });

  it("rehydrates and confirms a version-bound plan without adding global workspace chrome", async () => {
    const readyPlan = quotePlan("ready");
    const completedPlan = { ...readyPlan, status: "completed" as const };
    mocks.activePlan.mockResolvedValueOnce(readyPlan);
    mocks.confirmPlanApply.mockResolvedValueOnce({
      plan: completedPlan,
      order: { ...MANAGER_DRAFT, version: 18 },
    });
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("plan-status")).toHaveTextContent("ready"));
    expect(screen.getByRole("contentinfo", { name: "Platform attribution" })).toHaveTextContent("Powered by Databricks");
    fireEvent.click(screen.getByRole("button", { name: "Confirm plan" }));

    await waitFor(() => expect(mocks.confirmPlanApply).toHaveBeenCalledWith("plan-1", {
      expected_plan_revision: 2,
      expected_draft_version: 17,
      confirmation_token: "token-1",
      idempotency_key: "idem-1",
      view_role: "manager",
    }));
    expect(screen.getByTestId("draft-version")).toHaveTextContent("18");
    expect(screen.getByTestId("plan-status")).toHaveTextContent("completed");
  });

  it("reloads a confirmation through the authoritative active-plan endpoint", async () => {
    const readyPlan = quotePlan("ready");
    mocks.activePlan
      .mockResolvedValueOnce(readyPlan)
      .mockResolvedValueOnce({
        ...readyPlan,
        revision: 3,
        action_proposal: {
          ...readyPlan.action_proposal!,
          plan_revision: 3,
          confirmation: {
            ...readyPlan.action_proposal!.confirmation!,
            token: "token-2",
            token_id: "token-id-2",
          },
        },
      });
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("plan-status")).toHaveTextContent("ready"));
    fireEvent.click(screen.getByRole("button", { name: "Reload plan" }));

    await waitFor(() => expect(mocks.activePlan).toHaveBeenCalledTimes(2));
    expect(mocks.activePlan).toHaveBeenLastCalledWith("draft-1", "manager");
    expect(mocks.streamAgent).not.toHaveBeenCalled();
  });

  it("resumes a clarification plan instead of starting a replacement stream", async () => {
    mocks.activePlan.mockResolvedValueOnce({
      ...quotePlan("needs_input"),
      metadata: { clarifying_question: "How many operatories?" },
    });
    mocks.resumePlan.mockResolvedValueOnce(quotePlan("ready"));
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("plan-status")).toHaveTextContent("needs_input"));
    fireEvent.click(screen.getByRole("button", { name: "Ask Copilot" }));

    await waitFor(() => expect(mocks.resumePlan).toHaveBeenCalledWith("plan-1", {
      input: "Show account performance",
      expected_plan_revision: 2,
      expected_draft_version: 17,
      view_role: "manager",
    }));
    expect(mocks.streamAgent).not.toHaveBeenCalled();
    expect(screen.getByTestId("plan-status")).toHaveTextContent("ready");
  });

  it("preserves a plan returned by the blocking fallback", async () => {
    mocks.streamAgent.mockImplementationOnce(async () => undefined);
    mocks.agentQuery.mockResolvedValueOnce(quotePlan("ready"));
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("plan-status")).toHaveTextContent("none"));
    fireEvent.click(screen.getByRole("button", { name: "Ask Copilot" }));

    await waitFor(() => expect(screen.getByTestId("plan-status")).toHaveTextContent("ready"));
    expect(screen.getByTestId("message-count")).toHaveTextContent("1");
  });

  describe("New quote", () => {
    it("disables the action while the current quote is a pristine blank draft", async () => {
      render(<App />);

      await waitFor(() => expect(screen.getByTestId("draft-id")).toHaveTextContent("draft-1"));
      expect(screen.getByRole("button", { name: "New quote" })).toBeDisabled();
      expect(screen.getByTestId("new-quote-disabled")).toHaveTextContent("true");

      fireEvent.click(screen.getByRole("button", { name: "New quote" }));
      expect(mocks.createDraft).toHaveBeenCalledTimes(1);
    });

    it("shows the exact checkpoint confirmation for an editable quote with products", async () => {
      mocks.resumeDraft.mockResolvedValueOnce({ draft: WORKING_DRAFT });
      render(<App />);

      await waitFor(() => expect(screen.getByTestId("draft-id")).toHaveTextContent("draft-working"));
      fireEvent.click(screen.getByRole("button", { name: "New quote" }));

      const dialog = screen.getByRole("alertdialog", { name: "Start a new quote?" });
      expect(within(dialog).getByText(
        "Save this work to History, then open a blank quote for River Dental.",
      )).toBeInTheDocument();
      expect(within(dialog).getByRole("button", { name: "Keep editing" })).toBeInTheDocument();
      expect(within(dialog).getByRole("button", { name: "Save & start new" })).toBeInTheDocument();
      expect(mocks.saveDraft).not.toHaveBeenCalled();
      expect(mocks.createDraft).not.toHaveBeenCalled();
    });

    it("shows the same checkpoint confirmation when an otherwise-empty quote has an active plan", async () => {
      mocks.activePlan.mockResolvedValueOnce(quotePlan("ready"));
      render(<App />);

      await waitFor(() => expect(screen.getByTestId("plan-status")).toHaveTextContent("ready"));
      fireEvent.click(screen.getByRole("button", { name: "New quote" }));

      const dialog = screen.getByRole("alertdialog", { name: "Start a new quote?" });
      expect(within(dialog).getByText(
        "Save this work to History, then open a blank quote for River Dental.",
      )).toBeInTheDocument();
      expect(within(dialog).getByRole("button", { name: "Save & start new" })).toBeInTheDocument();
    });

    it("saves before creating and keeps the old quote selected until creation succeeds", async () => {
      let resolveCreate: (draft: DraftOrder) => void = () => undefined;
      const savedDraft = { ...WORKING_DRAFT, status: "saved", version: 18 };
      mocks.resumeDraft.mockResolvedValueOnce({ draft: WORKING_DRAFT });
      mocks.saveDraft.mockResolvedValueOnce(savedDraft);
      mocks.createDraft.mockReturnValueOnce(new Promise<DraftOrder>((resolve) => { resolveCreate = resolve; }));
      render(<App />);

      await waitFor(() => expect(screen.getByTestId("draft-id")).toHaveTextContent("draft-working"));
      fireEvent.click(screen.getByRole("button", { name: "New quote" }));
      fireEvent.click(screen.getByRole("button", { name: "Save & start new" }));

      await waitFor(() => expect(mocks.createDraft).toHaveBeenCalledWith("account-1", "manager"));
      expect(mocks.saveDraft).toHaveBeenCalledWith("draft-working", "manager");
      expect(mocks.saveDraft.mock.invocationCallOrder[0]).toBeLessThan(mocks.createDraft.mock.invocationCallOrder[0]);
      expect(screen.getByTestId("draft-id")).toHaveTextContent("draft-working");

      await act(async () => { resolveCreate(NEW_BLANK_DRAFT); });
      await waitFor(() => expect(screen.getByTestId("draft-id")).toHaveTextContent("draft-new-blank"));
      expect(screen.getByTestId("draft-line-count")).toHaveTextContent("0");
      expect(screen.getByTestId("draft-revision")).toHaveTextContent("1");
      expect(screen.getByTestId("draft-parent")).toHaveTextContent("none");
      expect(screen.getByTestId("draft-source")).toHaveTextContent("none");
      expect(localStorage.getItem(ACTIVE_DRAFT_STORAGE_KEY)).toBe("draft-new-blank");
    });

    it("retains the working quote and never creates when the checkpoint save fails", async () => {
      mocks.resumeDraft.mockResolvedValueOnce({ draft: WORKING_DRAFT });
      mocks.saveDraft.mockRejectedValueOnce(new Error("Save failed"));
      render(<App />);

      await waitFor(() => expect(screen.getByTestId("draft-id")).toHaveTextContent("draft-working"));
      fireEvent.click(screen.getByRole("button", { name: "New quote" }));
      fireEvent.click(screen.getByRole("button", { name: "Save & start new" }));

      expect(await screen.findByRole("alert")).toHaveTextContent("Save failed");
      expect(mocks.createDraft).not.toHaveBeenCalled();
      expect(screen.getByTestId("draft-id")).toHaveTextContent("draft-working");
      expect(screen.getByTestId("draft-status")).toHaveTextContent("draft");
    });

    it("retains the saved old quote when creating its replacement fails", async () => {
      const savedDraft = { ...WORKING_DRAFT, status: "saved", version: 18 };
      mocks.resumeDraft.mockResolvedValueOnce({ draft: WORKING_DRAFT });
      mocks.saveDraft.mockResolvedValueOnce(savedDraft);
      mocks.createDraft.mockRejectedValueOnce(new Error("Create failed"));
      render(<App />);

      await waitFor(() => expect(screen.getByTestId("draft-id")).toHaveTextContent("draft-working"));
      fireEvent.click(screen.getByRole("button", { name: "New quote" }));
      fireEvent.click(screen.getByRole("button", { name: "Save & start new" }));

      expect(await screen.findByRole("alert")).toHaveTextContent("Create failed");
      expect(mocks.saveDraft.mock.invocationCallOrder[0]).toBeLessThan(mocks.createDraft.mock.invocationCallOrder[0]);
      expect(screen.getByTestId("draft-id")).toHaveTextContent("draft-working");
      expect(screen.getByTestId("draft-status")).toHaveTextContent("saved");
      expect(localStorage.getItem(ACTIVE_DRAFT_STORAGE_KEY)).toBe("draft-working");
    });

    it.each([
      ["saved", { ...WORKING_DRAFT, draft_order_id: "draft-saved", status: "saved" }],
      ["generated", { ...WORKING_DRAFT, draft_order_id: "draft-generated", status: "quote-created" }],
    ])("starts immediately from a clean %s quote without another save", async (_label, currentDraft) => {
      mocks.resumeDraft.mockResolvedValueOnce({ draft: currentDraft });
      mocks.createDraft.mockResolvedValueOnce(NEW_BLANK_DRAFT);
      render(<App />);

      await waitFor(() => expect(screen.getByTestId("draft-id")).toHaveTextContent(currentDraft.draft_order_id));
      fireEvent.click(screen.getByRole("button", { name: "New quote" }));

      await waitFor(() => expect(screen.getByTestId("draft-id")).toHaveTextContent("draft-new-blank"));
      expect(screen.queryByRole("alertdialog", { name: "Start a new quote?" })).not.toBeInTheDocument();
      expect(mocks.saveDraft).not.toHaveBeenCalled();
      expect(mocks.createDraft).toHaveBeenCalledWith("account-1", "manager");
    });

    it("preserves the selected compact pane and role when starting a new quote", async () => {
      const interaction = userEvent.setup();
      const savedDraft = { ...WORKING_DRAFT, draft_order_id: "draft-saved", status: "saved" };
      mocks.resumeDraft.mockResolvedValueOnce({ draft: savedDraft });
      mocks.createDraft.mockResolvedValueOnce(NEW_BLANK_DRAFT);
      render(<App />);

      await waitFor(() => expect(screen.getByTestId("draft-id")).toHaveTextContent("draft-saved"));
      await interaction.click(screen.getByRole("tab", { name: "Genie" }));
      expect(screen.getByRole("tab", { name: "Genie" })).toHaveAttribute("aria-selected", "true");

      await interaction.click(screen.getByRole("button", { name: "New quote" }));

      await waitFor(() => expect(screen.getByTestId("draft-id")).toHaveTextContent("draft-new-blank"));
      expect(screen.getByRole("tab", { name: "Genie" })).toHaveAttribute("aria-selected", "true");
      expect(screen.getByTestId("active-role")).toHaveTextContent("manager");
    });

    it("clears conversation, plan, and evidence state when the new blank quote becomes active", async () => {
      const savedDraft = { ...WORKING_DRAFT, status: "saved", version: 18 };
      mocks.resumeDraft.mockResolvedValueOnce({ draft: WORKING_DRAFT });
      mocks.activePlan.mockResolvedValueOnce(quotePlan("ready"));
      mocks.saveDraft.mockResolvedValueOnce(savedDraft);
      mocks.createDraft.mockResolvedValueOnce(NEW_BLANK_DRAFT);
      render(<App />);

      await waitFor(() => expect(screen.getByTestId("plan-status")).toHaveTextContent("ready"));
      fireEvent.click(screen.getByRole("button", { name: "Ask Copilot" }));
      await waitFor(() => expect(screen.getByTestId("message-count")).toHaveTextContent("2"));
      fireEvent.click(screen.getByRole("button", { name: "Open evidence" }));
      expect(screen.getByTestId("evidence-panel")).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: "New quote" }));
      fireEvent.click(screen.getByRole("button", { name: "Save & start new" }));

      await waitFor(() => expect(screen.getByTestId("draft-id")).toHaveTextContent("draft-new-blank"));
      expect(screen.getByTestId("message-count")).toHaveTextContent("0");
      expect(screen.getByTestId("plan-status")).toHaveTextContent("none");
      expect(screen.queryByTestId("evidence-panel")).not.toBeInTheDocument();
    });

    it("restores a persisted empty active draft on remount without resuming or creating", async () => {
      const savedDraft = { ...WORKING_DRAFT, draft_order_id: "draft-saved", status: "saved" };
      mocks.resumeDraft.mockResolvedValueOnce({ draft: savedDraft });
      mocks.createDraft.mockResolvedValueOnce(NEW_BLANK_DRAFT);
      const firstRender = render(<App />);

      await waitFor(() => expect(screen.getByTestId("draft-id")).toHaveTextContent("draft-saved"));
      fireEvent.click(screen.getByRole("button", { name: "New quote" }));
      await waitFor(() => expect(screen.getByTestId("draft-id")).toHaveTextContent("draft-new-blank"));
      expect(localStorage.getItem(ACTIVE_DRAFT_STORAGE_KEY)).toBe("draft-new-blank");
      firstRender.unmount();

      mocks.getDraft.mockClear();
      mocks.resumeDraft.mockClear();
      mocks.createDraft.mockClear();
      mocks.getDraft.mockResolvedValueOnce(NEW_BLANK_DRAFT);
      render(<App />);

      await waitFor(() => expect(mocks.getDraft).toHaveBeenCalledWith("draft-new-blank", "manager"));
      expect(screen.getByTestId("draft-id")).toHaveTextContent("draft-new-blank");
      expect(mocks.resumeDraft).not.toHaveBeenCalled();
      expect(mocks.createDraft).not.toHaveBeenCalled();
    });

    it("clears a stale stored draft and falls back to the normal resume path", async () => {
      const resumedDraft = { ...WORKING_DRAFT, draft_order_id: "draft-resumed", status: "saved" };
      localStorage.setItem(ACTIVE_DRAFT_STORAGE_KEY, "draft-stale");
      mocks.getDraft.mockRejectedValueOnce(new ApiError("Draft no longer exists", 404));
      mocks.resumeDraft.mockResolvedValueOnce({ draft: resumedDraft });
      render(<App />);

      await waitFor(() => expect(screen.getByTestId("draft-id")).toHaveTextContent("draft-resumed"));
      expect(mocks.getDraft).toHaveBeenCalledWith("draft-stale", "manager");
      expect(mocks.resumeDraft).toHaveBeenCalledWith("account-1", "manager");
      expect(mocks.createDraft).not.toHaveBeenCalled();
      expect(localStorage.getItem(ACTIVE_DRAFT_STORAGE_KEY)).toBe("draft-resumed");
    });

    it("restores the last non-default account and its empty active draft after refresh", async () => {
      const accountTwoDraft = {
        ...NEW_BLANK_DRAFT,
        draft_order_id: "draft-account-2-empty",
        account_id: "account-2",
      };
      mocks.bootstrap.mockResolvedValueOnce({
        default_account_id: "account-1",
        accounts: [
          { account_id: "account-1", name: "River Dental" },
          { account_id: "account-2", name: "Lakeside Dental" },
        ],
        sample_prompts: [],
        source_freshness: [],
        product_snapshot: [],
      });
      localStorage.setItem(ACTIVE_ACCOUNT_STORAGE_KEY, "account-2");
      localStorage.setItem(
        "agentic-cpq-active-draft:v1:manager:account-2",
        "draft-account-2-empty",
      );
      mocks.getDraft.mockResolvedValueOnce(accountTwoDraft);

      render(<App />);

      await waitFor(() => expect(screen.getByTestId("draft-id")).toHaveTextContent("draft-account-2-empty"));
      expect(mocks.getDraft).toHaveBeenCalledWith("draft-account-2-empty", "manager");
      expect(mocks.resumeDraft).not.toHaveBeenCalled();
      expect(mocks.createDraft).not.toHaveBeenCalled();
      expect(localStorage.getItem(ACTIVE_ACCOUNT_STORAGE_KEY)).toBe("account-2");
    });

    it("preserves an empty-draft pointer and offers retry after a transient validation failure", async () => {
      localStorage.setItem(ACTIVE_DRAFT_STORAGE_KEY, "draft-empty-offline");
      mocks.getDraft.mockRejectedValueOnce(new Error("Network temporarily unavailable"));

      render(<App />);

      expect(await screen.findByRole("alert")).toHaveTextContent("Network temporarily unavailable");
      expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
      expect(localStorage.getItem(ACTIVE_DRAFT_STORAGE_KEY)).toBe("draft-empty-offline");
      expect(mocks.resumeDraft).not.toHaveBeenCalled();
      expect(mocks.createDraft).not.toHaveBeenCalled();
    });
  });
});
