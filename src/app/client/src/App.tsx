import {
  Alert,
  AlertDescription,
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Badge,
  Button,
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  TooltipProvider,
} from "@databricks/appkit-ui/react";
import { Bot, RefreshCw, ShoppingCart, TriangleAlert, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api, streamAgent, type AgentRequest } from "./api";
import { CopilotPanel } from "./components/CopilotPanel";
import { AdminSettingsPanel } from "./components/AdminSettingsPanel";
import { EvidencePanel } from "./components/EvidencePanel";
import { HistoryPanel } from "./components/HistoryPanel";
import { ProductDialog } from "./components/ProductDialog";
import { QuotePanel } from "./components/QuotePanel";
import { WorkspaceHeader } from "./components/WorkspaceHeader";
import {
  evidenceFromGenie,
  evidenceFromRecommendation,
  lineKey,
  QUOTE_APPROVAL_THRESHOLD,
  quoteSnapshot,
  sanitizeDraftForRole,
  sanitizeRecommendationForRole,
} from "./domain";
import { useCompactLayout } from "./hooks/useCompactLayout";
import type {
  AgentStage,
  BootstrapState,
  ConversationMessage,
  CurrentUser,
  DraftLineItem,
  DraftOrder,
  Evidence,
  GenieResponse,
  Product,
  QuotePlan,
  Recommendation,
  ViewRole,
} from "./types";

type Notice = { tone: "success" | "error"; message: string };

const ACTIVE_DRAFT_STORAGE_PREFIX = "agentic-cpq-active-draft:v1";
const ACTIVE_ACCOUNT_STORAGE_PREFIX = "agentic-cpq-active-account:v1";
const TERMINAL_PLAN_STATUSES = new Set(["completed", "stale", "failed", "cancelled"]);

export default function App() {
  const compact = useCompactLayout();
  const [bootstrap, setBootstrap] = useState<BootstrapState | null>(null);
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [accountId, setAccountId] = useState("");
  const [draft, setDraft] = useState<DraftOrder | null>(null);
  const [role, setRole] = useState<ViewRole>("seller");
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [stages, setStages] = useState<AgentStage[]>([]);
  const [activePlan, setActivePlan] = useState<QuotePlan | null>(null);
  const [planLoading, setPlanLoading] = useState(true);
  const [agentBusy, setAgentBusy] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [genieConversationId, setGenieConversationId] = useState<string | undefined>();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [savedSnapshot, setSavedSnapshot] = useState("[]");
  const [productOpen, setProductOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [adminOpen, setAdminOpen] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [selectedEvidence, setSelectedEvidence] = useState<Evidence | null>(null);
  const [mobileTab, setMobileTab] = useState("quote");
  const [copilotUnread, setCopilotUnread] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(() => {
    try { return localStorage.getItem("agentic-cpq-assistant-open") !== "false"; } catch { return true; }
  });
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  const [notice, setNotice] = useState<Notice | null>(null);
  const [pendingAccountId, setPendingAccountId] = useState<string | null>(null);
  const [pendingHistoricalDraft, setPendingHistoricalDraft] = useState<DraftOrder | null>(null);
  const [newQuoteConfirmationOpen, setNewQuoteConfirmationOpen] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);
  const initializedRef = useRef(false);
  const planLoadRef = useRef(0);

  const allowedRoles = useMemo<ViewRole[]>(() => {
    const values = (user?.allowed_views ?? []).filter((value): value is ViewRole => value === "seller" || value === "manager");
    return values.includes("manager") ? ["seller", "manager"] : ["seller"];
  }, [user]);
  const activeAccount = useMemo(
    () => bootstrap?.accounts.find((account) => account.account_id === accountId) ?? null,
    [accountId, bootstrap],
  );
  const busy = agentBusy || actionBusy;
  const dirty = draft
    ? quoteSnapshot(draft.line_items) !== savedSnapshot
      || (draft.status === "draft" && Number(draft.revision_number ?? 1) > 1)
    : false;
  const hasActivePlan = Boolean(activePlan && !TERMINAL_PLAN_STATUSES.has(activePlan.status));
  const pristineBlankDraft = Boolean(
    draft
    && draft.status === "draft"
    && draft.line_items.length === 0
    && !dirty
    && !hasActivePlan,
  );
  const newQuoteNeedsCheckpoint = Boolean(
    draft
    && draft.status !== "quote-created"
    && (dirty || draft.status === "draft" && draft.line_items.length > 0 || hasActivePlan),
  );
  const executionIdentity = user?.execution_identity ?? "service_principal";

  const loadActivePlan = useCallback(async (draftId: string, planRole: ViewRole) => {
    const requestId = ++planLoadRef.current;
    setPlanLoading(true);
    setActivePlan(null);
    try {
      const plan = await api.activePlan(draftId, planRole);
      if (requestId === planLoadRef.current) {
        setActivePlan(plan ? sanitizeQuotePlanForRole(plan, planRole) : null);
      }
    } catch {
      // Plan rehydration is additive; keep the existing quote workspace available if it fails.
    } finally {
      if (requestId === planLoadRef.current) setPlanLoading(false);
    }
  }, []);

  const activateDraft = useCallback((
    nextDraft: DraftOrder,
    storageUser: CurrentUser | null = user,
    focusQuote = false,
  ) => {
    planLoadRef.current += 1;
    setDraft(nextDraft);
    setAccountId(nextDraft.account_id);
    setMessages([]);
    setStages([]);
    setActivePlan(null);
    setPlanLoading(false);
    setGenieConversationId(undefined);
    setSavedSnapshot(quoteSnapshot(nextDraft.line_items));
    setSelectedEvidence(null);
    setEvidenceOpen(false);
    setCopilotUnread(false);
    setProductOpen(false);
    setHistoryOpen(false);
    setPendingHistoricalDraft(null);
    setNewQuoteConfirmationOpen(false);
    persistActiveDraftId(storageUser, nextDraft.account_id, nextDraft.draft_order_id);
    persistActiveAccountId(storageUser, nextDraft.account_id);
    if (focusQuote) {
      if (compact) setMobileTab("quote");
      window.setTimeout(() => document.getElementById("quote-title")?.focus(), compact ? 120 : 0);
    }
  }, [compact, user]);

  const refreshIfStale = async (cause: unknown): Promise<boolean> => {
    if (
      !(cause instanceof ApiError)
      || cause.status !== 409
      || !draft
      || !/stale|changed after|immutable|different owner/i.test(cause.message)
    ) {
      return false;
    }
    try {
      const current = sanitizeDraftForRole(
        await api.getDraft(draft.draft_order_id, role),
        role,
      );
      setDraft(current);
      setNotice({
        tone: "error",
        message: `${cause.message} The workspace has been refreshed to the latest version.`,
      });
      return true;
    } catch {
      return false;
    }
  };

  const initialize = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const [state, currentUser] = await Promise.all([
        api.bootstrap(),
        api.me().catch(() => ({ authenticated: false, username: "Local development" } as CurrentUser)),
      ]);
      const defaultAccountId = state.default_account_id || state.accounts[0]?.account_id;
      const persistedAccountId = readActiveAccountId(currentUser);
      const initialAccountId = persistedAccountId
        && state.accounts.some((account) => account.account_id === persistedAccountId)
        ? persistedAccountId
        : defaultAccountId;
      if (!initialAccountId) throw new Error("No quote accounts are configured for this app.");
      if (persistedAccountId && persistedAccountId !== initialAccountId) clearActiveAccountId(currentUser);
      const initialRole: ViewRole = currentUser.allowed_views?.includes("manager") && currentUser.default_view === "manager" ? "manager" : "seller";
      const order = sanitizeDraftForRole(
        await resolveDraftForAccount(currentUser, initialAccountId, initialRole),
        initialRole,
      );
      setBootstrap(state);
      setUser(currentUser);
      setRole(initialRole);
      activateDraft(order, currentUser, false);
      await loadActivePlan(order.draft_order_id, initialRole);
    } catch (cause) {
      setLoadError(publicError(cause, "The quote workspace could not be loaded."));
      setPlanLoading(false);
    } finally {
      setLoading(false);
    }
  }, [activateDraft, loadActivePlan]);

  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;
    void initialize();
  }, [initialize]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 6000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    if ((compact && mobileTab === "copilot") || (!compact && assistantOpen)) setCopilotUnread(false);
  }, [assistantOpen, compact, mobileTab]);

  useEffect(() => {
    try { localStorage.setItem("agentic-cpq-assistant-open", String(assistantOpen)); } catch { /* Storage may be disabled. */ }
  }, [assistantOpen]);

  useEffect(() => {
    if (!dirty) return;
    const preventAccidentalExit = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", preventAccidentalExit);
    return () => window.removeEventListener("beforeunload", preventAccidentalExit);
  }, [dirty]);

  const changeAccount = async (nextAccountId: string) => {
    if (!nextAccountId || nextAccountId === accountId || busy) return;
    setActionBusy(true);
    try {
      const order = sanitizeDraftForRole(
        await resolveDraftForAccount(user, nextAccountId, role),
        role,
      );
      activateDraft(order);
      await loadActivePlan(order.draft_order_id, role);
      setNotice({ tone: "success", message: "The quote workspace is ready for the selected account." });
    } catch (cause) {
      setNotice({ tone: "error", message: publicError(cause, "A new draft could not be created.") });
    } finally {
      setActionBusy(false);
    }
  };

  const requestAccountChange = (nextAccountId: string) => {
    if (!nextAccountId || nextAccountId === accountId || busy) return;
    if (dirty) {
      setPendingAccountId(nextAccountId);
      return;
    }
    void changeAccount(nextAccountId);
  };

  const changeRole = async (nextRole: ViewRole) => {
    if (busy || !allowedRoles.includes(nextRole) || nextRole === role) return;
    if (!draft) {
      setRole(nextRole);
      setMessages([]);
      setStages([]);
      setActivePlan(null);
      setPlanLoading(false);
      setGenieConversationId(undefined);
      setSelectedEvidence(null);
      setEvidenceOpen(false);
      return;
    }
    setActionBusy(true);
    try {
      const nextDraft = sanitizeDraftForRole(await api.getDraft(draft.draft_order_id, nextRole), nextRole);
      setRole(nextRole);
      setDraft(nextDraft);
      setMessages([]);
      setStages([]);
      setGenieConversationId(undefined);
      setSelectedEvidence(null);
      setEvidenceOpen(false);
      await loadActivePlan(nextDraft.draft_order_id, nextRole);
      setNotice({ tone: "success", message: `${nextRole === "manager" ? "Manager" : "Seller"} role selected.` });
    } catch (cause) {
      setNotice({ tone: "error", message: publicError(cause, "The requested view is unavailable.") });
    } finally {
      setActionBusy(false);
    }
  };

  const replaceDraft = async (lines: DraftLineItem[]): Promise<DraftOrder> => {
    if (!draft) throw new Error("The draft is not ready yet.");
    const result = sanitizeDraftForRole(await api.patchDraft(draft.draft_order_id, lines, role, draft.version), role);
    setDraft(result);
    return result;
  };

  const handleQuantity = async (line: DraftLineItem, quantity: number) => {
    if (!draft || quantity < 1) return;
    setActionBusy(true);
    try {
      const next = draft.line_items.map((item) => lineKey(item) === lineKey(line) ? { ...item, quantity } : item);
      await replaceDraft(next);
    } catch (cause) {
      if (!(await refreshIfStale(cause))) {
        setNotice({ tone: "error", message: publicError(cause, "Quantity could not be updated.") });
      }
    } finally {
      setActionBusy(false);
    }
  };

  const handleSetPrice = async (line: DraftLineItem, unitPrice: number) => {
    if (!draft) return;
    setActionBusy(true);
    try {
      const result = sanitizeDraftForRole(await api.setPrice(draft.draft_order_id, accountId, line.sku, unitPrice, role, draft.version), role);
      setDraft(result);
      if (result.line_items.some((item) => item.sku === line.sku && item.approval_required)) {
        setNotice({ tone: "error", message: "The new price requires approval before this quote can be sent." });
      }
    } catch (cause) {
      if (!(await refreshIfStale(cause))) {
        setNotice({ tone: "error", message: publicError(cause, "The net price could not be updated.") });
      }
      throw cause;
    } finally {
      setActionBusy(false);
    }
  };

  const handleRemove = async (line: DraftLineItem) => {
    if (!draft) return;
    setActionBusy(true);
    try {
      const next = draft.line_items.filter((item) => {
        if (line.is_addon) return lineKey(item) !== lineKey(line);
        return item.sku !== line.sku && item.covers_sku !== line.sku;
      });
      await replaceDraft(next);
      setNotice({ tone: "success", message: `${line.title} was removed from the quote.` });
    } catch (cause) {
      if (!(await refreshIfStale(cause))) {
        setNotice({ tone: "error", message: publicError(cause, "The quote line could not be removed.") });
      }
    } finally {
      setActionBusy(false);
    }
  };

  const handleAddProduct = async (product: Product) => {
    if (!draft) return;
    setActionBusy(true);
    try {
      const result = sanitizeDraftForRole(await api.addLine(draft.draft_order_id, accountId, product.sku, role, draft.version), role);
      setDraft(result);
      setNotice({ tone: "success", message: `${product.title} was added with account pricing${product.warranty_eligible ? " and eligible care" : ""}.` });
    } catch (cause) {
      if (!(await refreshIfStale(cause))) {
        setNotice({ tone: "error", message: publicError(cause, "The product could not be added.") });
      }
      throw cause;
    } finally {
      setActionBusy(false);
    }
  };

  const saveDraftCheckpoint = async (draftToSave: DraftOrder): Promise<DraftOrder> => {
    const result = sanitizeDraftForRole(
      await api.saveDraft(draftToSave.draft_order_id, role),
      role,
    );
    setDraft(result);
    setSavedSnapshot(quoteSnapshot(result.line_items));
    persistActiveDraftId(user, result.account_id, result.draft_order_id);
    return result;
  };

  const handleSave = async () => {
    if (!draft) return;
    setActionBusy(true);
    try {
      await saveDraftCheckpoint(draft);
      setNotice({ tone: "success", message: "Draft saved and available in quote history." });
    } catch (cause) {
      if (!(await refreshIfStale(cause))) {
        setNotice({ tone: "error", message: publicError(cause, "The draft could not be saved.") });
      }
    } finally {
      setActionBusy(false);
    }
  };

  const startNewQuote = async (saveFirst: boolean) => {
    if (!draft || !accountId || busy || loading || planLoading || pristineBlankDraft) return;
    const currentDraft = draft;
    let checkpointSaved = false;
    setNewQuoteConfirmationOpen(false);
    setActionBusy(true);
    try {
      if (saveFirst) {
        await saveDraftCheckpoint(currentDraft);
        checkpointSaved = true;
      }
      const nextDraft = sanitizeDraftForRole(await api.createDraft(accountId, role), role);
      activateDraft(nextDraft);
      setNotice({
        tone: "success",
        message: `New quote ready for ${activeAccount?.name || "this account"}.`,
      });
    } catch (cause) {
      if (!checkpointSaved && saveFirst) {
        if (!(await refreshIfStale(cause))) {
          setNotice({ tone: "error", message: publicError(cause, "The draft could not be saved. Your current quote is still open.") });
        }
      } else {
        setNotice({
          tone: "error",
          message: publicError(
            cause,
            checkpointSaved
              ? "Your work was saved, but a new quote could not be started. The saved quote is still open."
              : "A new quote could not be started. Your current quote is still open.",
          ),
        });
      }
    } finally {
      setActionBusy(false);
    }
  };

  const requestNewQuote = () => {
    if (!draft || busy || loading || planLoading || pristineBlankDraft) return;
    if (newQuoteNeedsCheckpoint) {
      setNewQuoteConfirmationOpen(true);
      return;
    }
    void startNewQuote(false);
  };

  const handleGeneratePdf = async () => {
    if (!draft) return;
    setActionBusy(true);
    try {
      const document = await api.generateQuotePdf(draft.draft_order_id, role);
      const downloadUrl = URL.createObjectURL(document.blob);
      const link = window.document.createElement("a");
      link.href = downloadUrl;
      link.download = document.filename;
      window.document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(downloadUrl);
      const result = sanitizeDraftForRole(await api.getDraft(draft.draft_order_id, role), role);
      setDraft(result);
      setSavedSnapshot(quoteSnapshot(result.line_items));
      await loadActivePlan(result.draft_order_id, role);
      setNotice({ tone: "success", message: `${document.filename} was generated and downloaded.` });
    } catch (cause) {
      if (!(await refreshIfStale(cause))) {
        setNotice({ tone: "error", message: publicError(cause, "The quote PDF could not be generated.") });
      }
    } finally {
      setActionBusy(false);
    }
  };

  const handleCreateRevision = async () => {
    if (!draft || draft.status !== "quote-created") return;
    setActionBusy(true);
    try {
      const result = sanitizeDraftForRole(
        await api.createRevision(draft.draft_order_id, role),
        role,
      );
      activateDraft(result, user, true);
      await loadActivePlan(result.draft_order_id, role);
      setNotice({
        tone: "success",
        message: "Working copy ready. The generated quote remains unchanged.",
      });
    } catch (cause) {
      setNotice({ tone: "error", message: publicError(cause, "A quote revision could not be created.") });
    } finally {
      setActionBusy(false);
    }
  };

  const openEvidence = (evidence: Evidence) => {
    setSelectedEvidence(evidence);
    setEvidenceOpen(true);
  };

  const submitPrompt = async (prompt: string) => {
    if (!draft || busy) return;
    const userMessage: ConversationMessage = { id: makeId("user"), role: "user", kind: "text", content: prompt };
    const conversationHistory = toConversationHistory(messages);
    setMessages((current) => [...current, userMessage]);
    setStages([]);
    setAgentBusy(true);
    const controller = new AbortController();
    controllerRef.current = controller;

    try {
      if (activePlan?.status === "needs_input") {
        const resumed = await api.resumePlan(activePlan.plan_id, {
          input: prompt,
          expected_plan_revision: activePlan.revision,
          expected_draft_version: Number(draft.version ?? activePlan.base_draft_version),
          view_role: role,
        });
        setActivePlan(sanitizeQuotePlanForRole(resumed, role));
        if ((compact && mobileTab !== "copilot") || (!compact && !assistantOpen)) setCopilotUnread(true);
        return;
      }

      const request: AgentRequest = {
        query: prompt,
        intent: "auto",
        account_id: accountId,
        view_role: role,
        draft_order_id: draft.draft_order_id,
        current_order_lines: draft.line_items,
        conversation_history: conversationHistory,
        recommendation_context: latestRecommendationContext(messages),
        genie_conversation_id: genieConversationId ?? null,
        expected_revision: Number(draft.version ?? 0),
      };
      let received = false;
      let streamError = "";
      await streamAgent(request, controller.signal, (event) => {
        if (event.event === "stage") {
          setStages((current) => updateStages(current, event.data));
        } else if (event.event === "plan") {
          setActivePlan(sanitizeQuotePlanForRole(event.data, role));
          if ((compact && mobileTab !== "copilot") || (!compact && !assistantOpen)) setCopilotUnread(true);
          received = true;
        } else if (event.event === "recommendation") {
          appendRecommendation(event.data);
          received = true;
        } else if (event.event === "conversation") {
          appendAnswer(event.data as GenieResponse, prompt);
          received = true;
        } else if (event.event === "error") {
          streamError = event.data.detail || "Genie couldn't complete this request. Try again.";
        }
      });

      if (!received && !controller.signal.aborted) {
        if (streamError) throw new Error(streamError);
        const result = await api.agentQuery(request, controller.signal);
        if (isQuotePlan(result)) {
          setActivePlan(sanitizeQuotePlanForRole(result, role));
          if ((compact && mobileTab !== "copilot") || (!compact && !assistantOpen)) setCopilotUnread(true);
        }
        else if (isRecommendation(result)) appendRecommendation(result);
        else appendAnswer(result as GenieResponse, prompt);
      }
    } catch (cause) {
      const canceled = isAbortError(cause) || controller.signal.aborted;
      setMessages((current) => [...current, {
        id: makeId("error"),
        role: "assistant",
        kind: "error",
        content: canceled ? "Request canceled. Your quote was not changed." : publicError(cause, "The request could not be completed."),
        retryPrompt: canceled ? undefined : prompt,
      }]);
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null;
      setAgentBusy(false);
      setStages([]);
    }
  };

  const appendAnswer = (result: GenieResponse, retryPrompt?: string) => {
    const conversationId = result.genie_conversation_id || result.conversation_id;
    if (conversationId) setGenieConversationId(conversationId);
    const content = (result.answer || result.text || result.knowledge_fallback?.answer || "").trim();
    if (!content) {
      setMessages((current) => [...current, {
        id: makeId("error"),
        role: "assistant",
        kind: "error",
        content: "Genie didn't return a usable response. Try again.",
        retryPrompt,
      }]);
      if ((compact && mobileTab !== "copilot") || (!compact && !assistantOpen)) setCopilotUnread(true);
      return;
    }
    const partial = Boolean(
      result.error
      || result.knowledge_fallback_used
      || (result.status && /partial|unavailable|error|failed/i.test(result.status)),
    );
    setMessages((current) => [...current, {
      id: makeId("answer"),
      role: "assistant",
      kind: "answer",
      content,
      evidence: evidenceFromGenie(result, executionIdentity),
      error: partial,
    }]);
    if ((compact && mobileTab !== "copilot") || (!compact && !assistantOpen)) setCopilotUnread(true);
  };

  const appendRecommendation = (raw: Recommendation) => {
    const recommendation = sanitizeRecommendationForRole(raw, role);
    setMessages((current) => [...current, {
      id: makeId("recommendation"),
      role: "assistant",
      kind: "recommendation",
      recommendation,
      evidence: evidenceFromRecommendation(recommendation, executionIdentity),
    }]);
    if ((compact && mobileTab !== "copilot") || (!compact && !assistantOpen)) setCopilotUnread(true);
  };

  const applyRecommendation = async (messageId: string) => {
    if (!draft || actionBusy || agentBusy) return;
    const message = messages.find((candidate) => candidate.id === messageId);
    if (!message || message.role !== "assistant" || message.kind !== "recommendation") return;
    const recommendationId = message.recommendation.recommendation_id;
    const revision = message.recommendation.revision;
    if (!recommendationId || revision == null) {
      setNotice({ tone: "error", message: "This proposal can’t be applied. Request an updated version." });
      return;
    }
    setActionBusy(true);
    try {
      const mode = message.recommendation.apply_mode === "replace" ? "replace" : "add";
      const result = await api.applyRecommendation(draft.draft_order_id, recommendationId, revision, mode, role);
      setDraft(sanitizeDraftForRole(result.order, role));
      setMessages((current) => current.map((message) => message.id === messageId && message.role === "assistant" && message.kind === "recommendation" ? { ...message, applied: true } : message));
      setNotice({ tone: "success", message: result.already_applied ? "That recommendation was already applied; the quote is current." : "Recommendation applied to the live quote." });
      if (compact) setMobileTab("quote");
      window.setTimeout(() => document.getElementById("quote-title")?.focus(), compact ? 120 : 0);
    } catch (cause) {
      if (!(await refreshIfStale(cause))) {
        setNotice({ tone: "error", message: publicError(cause, "The recommendation could not be applied.") });
      }
    } finally {
      setActionBusy(false);
    }
  };

  const selectPlanScenario = async (scenarioId: string) => {
    if (!draft || !activePlan || actionBusy || agentBusy || scenarioId === activePlan.selected_scenario_id) return;
    setActionBusy(true);
    try {
      const result = await api.selectPlanScenario(activePlan.plan_id, scenarioId, {
        expected_plan_revision: activePlan.revision,
        expected_draft_version: Number(draft.version ?? activePlan.base_draft_version),
        view_role: role,
      });
      setActivePlan(sanitizeQuotePlanForRole(result, role));
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) {
        await loadActivePlan(draft.draft_order_id, role);
      }
      setNotice({ tone: "error", message: publicError(cause, "The quote option could not be selected.") });
    } finally {
      setActionBusy(false);
    }
  };

  const cancelPlan = async () => {
    if (!draft || !activePlan || actionBusy) return;
    if (agentBusy) controllerRef.current?.abort();
    setActionBusy(true);
    try {
      const result = await api.cancelPlan(activePlan.plan_id, {
        expected_plan_revision: activePlan.revision,
        expected_draft_version: Number(draft.version ?? activePlan.base_draft_version),
        view_role: role,
      });
      setActivePlan(result.status === "cancelled" ? null : sanitizeQuotePlanForRole(result, role));
      setStages([]);
      setNotice({ tone: "success", message: "Quote plan cancelled. The quote was not changed." });
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) {
        await loadActivePlan(draft.draft_order_id, role);
      }
      setNotice({ tone: "error", message: publicError(cause, "The quote plan could not be cancelled.") });
    } finally {
      setActionBusy(false);
    }
  };

  const confirmPlan = async () => {
    if (!draft || !activePlan || actionBusy || agentBusy) return;
    const proposal = activePlan.action_proposal;
    const confirmation = proposal?.confirmation;
    if (!proposal || !confirmation?.token?.trim()) {
      setNotice({ tone: "error", message: "This plan can’t be confirmed. Ask Genie to refresh it." });
      return;
    }
    setActionBusy(true);
    try {
      const result = await api.confirmPlanApply(activePlan.plan_id, {
        expected_plan_revision: activePlan.revision,
        expected_draft_version: Number(draft.version ?? activePlan.base_draft_version),
        confirmation_token: confirmation.token,
        idempotency_key: confirmation.idempotency_key || proposal.idempotency_key,
        view_role: role,
      });
      const nextDraft = sanitizeDraftForRole(result.order, role);
      setDraft(nextDraft);
      setActivePlan(sanitizeQuotePlanForRole(result.plan, role));
      setNotice({ tone: "success", message: "Confirmed changes applied to the quote." });
      if (compact) setMobileTab("quote");
      window.setTimeout(() => document.getElementById("quote-title")?.focus(), compact ? 120 : 0);
    } catch (cause) {
      if (!(await refreshIfStale(cause)) && cause instanceof ApiError && cause.status === 409) {
        await loadActivePlan(draft.draft_order_id, role);
      }
      setNotice({ tone: "error", message: publicError(cause, "The quote plan could not be applied.") });
    } finally {
      setActionBusy(false);
    }
  };

  const loadHistoricalDraft = async (historical: DraftOrder) => {
    const safeDraft = sanitizeDraftForRole(historical, role);
    activateDraft(safeDraft);
    await loadActivePlan(safeDraft.draft_order_id, role);
    setNotice({
      tone: "success",
      message: historical.status === "quote-created"
        ? "Generated quote loaded read-only. Create a revision to make changes."
        : "Saved draft loaded into the workspace.",
    });
  };

  const requestHistoricalDraft = async (historical: DraftOrder) => {
    if (dirty && historical.draft_order_id !== draft?.draft_order_id) {
      setPendingHistoricalDraft(historical);
      return;
    }
    await loadHistoricalDraft(historical);
  };

  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    document.documentElement.classList.toggle("light", !next);
    try { localStorage.setItem("quote-studio-theme", next ? "dark" : "light"); } catch { /* Storage may be disabled. */ }
  };

  if (loadError && !bootstrap) {
    return (
      <main className="fatal-state">
        <Alert variant="destructive">
          <TriangleAlert aria-hidden="true" />
          <AlertDescription>{loadError}</AlertDescription>
        </Alert>
        <Button onClick={() => void initialize()}><RefreshCw aria-hidden="true" /> Retry</Button>
      </main>
    );
  }

  const copilot = (
    <CopilotPanel
      messages={messages}
      stages={stages}
      currentLines={draft?.line_items ?? []}
      accountId={accountId}
      draftOrderId={draft?.draft_order_id}
      currentDraftStatus={draft?.status}
      currentDraftVersion={draft?.version}
      role={role}
      activePlan={activePlan}
      planLoading={planLoading}
      executionIdentity={executionIdentity}
      busy={agentBusy}
      applyBusy={actionBusy}
      ready={!loading && !planLoading && Boolean(draft)}
      onSubmit={submitPrompt}
      onCancel={() => controllerRef.current?.abort()}
      onApply={applyRecommendation}
      onPlanSelect={selectPlanScenario}
      onPlanConfirm={confirmPlan}
      onPlanCancel={cancelPlan}
      onPlanReload={() => draft ? loadActivePlan(draft.draft_order_id, role) : Promise.resolve()}
      onEvidence={openEvidence}
      onCollapse={compact ? undefined : () => setAssistantOpen(false)}
    />
  );
  const quote = (
    <QuotePanel
      account={activeAccount}
      draft={draft}
      freshness={bootstrap?.source_freshness ?? []}
      role={role}
      approvalThreshold={bootstrap?.quote_policy?.approval_threshold ?? QUOTE_APPROVAL_THRESHOLD}
      canEditNetPrice={role === "manager" || (bootstrap?.quote_policy?.allow_seller_price_edits ?? true)}
      busy={busy}
      loading={loading}
      dirty={dirty}
      onOpenProducts={() => setProductOpen(true)}
      onQuantity={handleQuantity}
      onSetPrice={handleSetPrice}
      onRemove={handleRemove}
      onSave={handleSave}
      onSend={handleGeneratePdf}
      onCreateRevision={handleCreateRevision}
    />
  );

  return (
    <TooltipProvider delayDuration={250}>
      <div className="app-shell">
        <WorkspaceHeader
          accounts={bootstrap?.accounts ?? []}
          accountId={accountId}
          user={user}
          role={role}
          allowedRoles={allowedRoles}
          dark={dark}
          busy={busy || loading}
          onAccountChange={requestAccountChange}
          onRoleChange={(value) => void changeRole(value)}
          onOpenAdmin={() => setAdminOpen(true)}
          onNewQuote={requestNewQuote}
          newQuoteDisabled={loading || planLoading || !draft || pristineBlankDraft}
          onHistory={() => setHistoryOpen(true)}
          onToggleTheme={toggleTheme}
        />

        {notice && (
          <Alert
            className={`app-notice notice-${notice.tone}`}
            variant={notice.tone === "error" ? "destructive" : "default"}
            role={notice.tone === "error" ? "alert" : "status"}
            aria-live={notice.tone === "error" ? "assertive" : "polite"}
          >
            <AlertDescription>{notice.message}</AlertDescription>
            <Button size="icon-sm" variant="ghost" onClick={() => setNotice(null)} aria-label="Dismiss notification"><X aria-hidden="true" /></Button>
          </Alert>
        )}

        {compact ? (
          <Tabs value={mobileTab} onValueChange={setMobileTab} className="compact-workspace">
            <TabsList className="compact-tabs">
              <TabsTrigger value="copilot">
                <Bot aria-hidden="true" /> Genie
                {agentBusy && <span className="tab-activity" aria-label="Assistant is working" />}
                {!agentBusy && copilotUnread && <Badge variant="secondary" aria-label="New assistant result">New</Badge>}
              </TabsTrigger>
              <TabsTrigger value="quote"><ShoppingCart aria-hidden="true" /> Quote</TabsTrigger>
            </TabsList>
            <TabsContent value="copilot" forceMount className="compact-panel">{copilot}</TabsContent>
            <TabsContent value="quote" forceMount className="compact-panel">{quote}</TabsContent>
          </Tabs>
        ) : (
          <div className="desktop-layout">
            {assistantOpen ? (
              <ResizablePanelGroup direction="horizontal" className="desktop-workspace" autoSaveId="agentic-cpq-quote-first-layout">
                <ResizablePanel defaultSize={68} minSize={52}>{quote}</ResizablePanel>
                <ResizableHandle withHandle />
                <ResizablePanel defaultSize={32} minSize={28} maxSize={48}>{copilot}</ResizablePanel>
              </ResizablePanelGroup>
            ) : (
              <>
                <div className="desktop-quote-only">{quote}</div>
                <aside className="assistant-launcher" aria-label="Genie collapsed">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setAssistantOpen(true)}
                    aria-label="Open Genie"
                  >
                    <Bot aria-hidden="true" />
                  </Button>
                  <span>Genie</span>
                  {(agentBusy || copilotUnread) && <i aria-label={agentBusy ? "Genie is working" : "New Genie result"} />}
                </aside>
              </>
            )}
          </div>
        )}

        <footer className="app-attribution" aria-label="Platform attribution">
          <span>Powered by <strong>Databricks</strong></span>
        </footer>

        <ProductDialog open={productOpen} products={bootstrap?.product_snapshot ?? []} role={role} onOpenChange={setProductOpen} onAdd={handleAddProduct} />
        <HistoryPanel
          open={historyOpen}
          compact={compact}
          account={activeAccount}
          currentDraft={draft}
          role={role}
          onOpenChange={setHistoryOpen}
          onLoadDraft={requestHistoricalDraft}
        />
        <EvidencePanel open={evidenceOpen} compact={compact} evidence={selectedEvidence} onOpenChange={setEvidenceOpen} />
        {user?.can_manage && (
          <AdminSettingsPanel
            open={adminOpen}
            onOpenChange={setAdminOpen}
            onSaved={(updated) => {
              setBootstrap((current) => current ? { ...current, quote_policy: { ...updated.behavior } } : current);
            }}
          />
        )}
        <AlertDialog open={pendingAccountId != null} onOpenChange={(open) => { if (!open) setPendingAccountId(null); }}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Switch before saving to history?</AlertDialogTitle>
              <AlertDialogDescription>
                Your edits are stored in this working draft, but it will not appear in quote history until you save it.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Keep editing</AlertDialogCancel>
              <AlertDialogAction onClick={() => {
                const nextAccountId = pendingAccountId;
                setPendingAccountId(null);
                if (nextAccountId) void changeAccount(nextAccountId);
              }}>Switch anyway</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
        <AlertDialog open={pendingHistoricalDraft != null} onOpenChange={(open) => { if (!open) setPendingHistoricalDraft(null); }}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Load another quote before saving?</AlertDialogTitle>
              <AlertDialogDescription>
                This quote has working changes. Save them first if you want a visible checkpoint in quote history.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Keep editing</AlertDialogCancel>
              <AlertDialogAction onClick={() => {
                const historical = pendingHistoricalDraft;
                setPendingHistoricalDraft(null);
                if (historical) void loadHistoricalDraft(historical);
              }}>Load anyway</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
        <AlertDialog open={newQuoteConfirmationOpen} onOpenChange={setNewQuoteConfirmationOpen}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Start a new quote?</AlertDialogTitle>
              <AlertDialogDescription>
                Save this work to History, then open a blank quote for {activeAccount?.name || "this account"}.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Keep editing</AlertDialogCancel>
              <AlertDialogAction onClick={() => void startNewQuote(true)}>Save &amp; start new</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </TooltipProvider>
  );
}

function updateStages(current: AgentStage[], event: Partial<AgentStage> & { key: string }): AgentStage[] {
  const status: AgentStage["status"] = event.status === "done" ? "done" : "active";
  const next = current.map((stage) => stage.status === "active" && stage.key !== event.key ? { ...stage, status: "done" as const } : stage);
  const index = next.findIndex((stage) => stage.key === event.key);
  const stage = { key: event.key, label: event.label || humanize(event.key), status };
  if (index === -1) return [...next, stage];
  return next.map((item, itemIndex) => itemIndex === index ? stage : item);
}

function toConversationHistory(messages: ConversationMessage[]): Array<{ role: string; content: string }> {
  return messages.slice(-8).flatMap((message) => {
    if (message.role === "user") return [{ role: "user", content: message.content }];
    if (message.kind === "answer") return [{ role: "assistant", content: message.content.slice(0, 1600) }];
    if (message.kind === "recommendation") return [{ role: "assistant", content: `${message.recommendation.summary} (${message.recommendation.items.length} quote lines)` }];
    return [];
  });
}

function latestRecommendationContext(messages: ConversationMessage[]): Record<string, unknown> {
  const recommendation = [...messages].reverse().find((message) => message.role === "assistant" && message.kind === "recommendation");
  return recommendation?.role === "assistant" && recommendation.kind === "recommendation" ? { ...recommendation.recommendation } : {};
}

function sanitizeQuotePlanForRole(plan: QuotePlan, role: ViewRole): QuotePlan {
  if (role === "manager") return plan;
  return {
    ...plan,
    scenarios: plan.scenarios?.map((scenario) => ({
      ...scenario,
      recommendation: scenario.recommendation
        ? sanitizeRecommendationForRole(scenario.recommendation, role)
        : scenario.recommendation,
    })),
  };
}

function isRecommendation(value: unknown): value is Recommendation {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return typeof record.summary === "string" && Array.isArray(record.items);
}

function isQuotePlan(value: unknown): value is QuotePlan {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return typeof record.plan_id === "string"
    && typeof record.goal === "string"
    && typeof record.status === "string"
    && typeof record.revision === "number";
}

function makeId(prefix: string): string {
  return `${prefix}-${typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`}`;
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function isAbortError(cause: unknown): boolean {
  return cause instanceof DOMException && cause.name === "AbortError";
}

function publicError(cause: unknown, fallback: string): string {
  if (!(cause instanceof Error) || !cause.message) return fallback;
  if (/\{\s*"detail"/i.test(cause.message)) {
    try {
      const parsed = JSON.parse(cause.message) as { detail?: string };
      return parsed.detail || fallback;
    } catch { return fallback; }
  }
  return cause.message;
}

async function resolveDraftForAccount(
  user: CurrentUser | null,
  accountId: string,
  role: ViewRole,
): Promise<DraftOrder> {
  const persistedDraftId = readActiveDraftId(user, accountId);
  if (persistedDraftId) {
    try {
      const candidate = await api.getDraft(persistedDraftId, role);
      if (candidate.account_id === accountId) return candidate;
      clearActiveDraftId(user, accountId);
    } catch (cause) {
      if (!isDefinitiveStoredDraftMiss(cause)) throw cause;
      clearActiveDraftId(user, accountId);
    }
  }

  const resumable = await api.resumeDraft(accountId, role).catch(() => ({ draft: null }));
  return resumable.draft ?? await api.createDraft(accountId, role);
}

function isDefinitiveStoredDraftMiss(cause: unknown): boolean {
  return cause instanceof ApiError && [400, 403, 404, 409].includes(cause.status);
}

function storageIdentity(user: CurrentUser | null): string {
  return (user?.email || user?.username || "anonymous").trim().toLocaleLowerCase();
}

function activeDraftStorageKey(user: CurrentUser | null, accountId: string): string {
  return `${ACTIVE_DRAFT_STORAGE_PREFIX}:${encodeURIComponent(storageIdentity(user))}:${encodeURIComponent(accountId)}`;
}

function readActiveDraftId(user: CurrentUser | null, accountId: string): string | null {
  try {
    return localStorage.getItem(activeDraftStorageKey(user, accountId))?.trim() || null;
  } catch {
    return null;
  }
}

function persistActiveDraftId(user: CurrentUser | null, accountId: string, draftId: string): void {
  try {
    localStorage.setItem(activeDraftStorageKey(user, accountId), draftId);
  } catch {
    // The workspace remains usable when browser storage is disabled.
  }
}

function clearActiveDraftId(user: CurrentUser | null, accountId: string): void {
  try {
    localStorage.removeItem(activeDraftStorageKey(user, accountId));
  } catch {
    // The fallback resume path remains available when browser storage is disabled.
  }
}

function activeAccountStorageKey(user: CurrentUser | null): string {
  return `${ACTIVE_ACCOUNT_STORAGE_PREFIX}:${encodeURIComponent(storageIdentity(user))}`;
}

function readActiveAccountId(user: CurrentUser | null): string | null {
  try {
    return localStorage.getItem(activeAccountStorageKey(user))?.trim() || null;
  } catch {
    return null;
  }
}

function persistActiveAccountId(user: CurrentUser | null, accountId: string): void {
  try {
    localStorage.setItem(activeAccountStorageKey(user), accountId);
  } catch {
    // Account selection remains in memory when browser storage is disabled.
  }
}

function clearActiveAccountId(user: CurrentUser | null): void {
  try {
    localStorage.removeItem(activeAccountStorageKey(user));
  } catch {
    // Bootstrap's configured default account remains available.
  }
}
