import type {
  Account,
  AdminSettings,
  AgentIntent,
  AgentStreamEvent,
  BootstrapState,
  CurrentUser,
  DraftLineItem,
  DraftOrder,
  FollowupSuggestionsResponse,
  GenieResponse,
  HistoryResponse,
  Product,
  QuotePlan,
  QuotePdfSettings,
  Recommendation,
  ViewRole,
} from "./types";

export interface SearchMetadata {
  mode: string;
  fallback_used: boolean;
}

export interface SearchResponse<T> {
  results: T[];
  metadata?: SearchMetadata;
  source?: string;
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

export async function fetchJson<T>(url: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  if (!response.ok) {
    let message = await response.text();
    try {
      const payload = JSON.parse(message) as { detail?: string };
      message = payload.detail ?? message;
    } catch {
      // Retain the public response text.
    }
    throw new ApiError(message || `Request failed (${response.status})`, response.status);
  }
  return await response.json() as T;
}

async function fetchOptionalJson<T>(url: string, init: RequestInit = {}): Promise<T | null> {
  const response = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  if (response.status === 204) return null;
  if (!response.ok) {
    let message = await response.text();
    try {
      const payload = JSON.parse(message) as { detail?: string };
      message = payload.detail ?? message;
    } catch {
      // Retain the public response text.
    }
    throw new ApiError(message || `Request failed (${response.status})`, response.status);
  }
  return await response.json() as T;
}

export function quotePdfUrl(draftId: string, role: ViewRole, download = false): string {
  const params = new URLSearchParams({ view_role: role });
  if (download) params.set("download", "true");
  return `/api/draft-orders/${encodeURIComponent(draftId)}/quote.pdf?${params.toString()}`;
}

export const api = {
  bootstrap: () => fetchJson<BootstrapState>("/api/bootstrap-state"),
  me: () => fetchJson<CurrentUser>("/api/me"),
  getAdminSettings: () => fetchJson<AdminSettings>("/api/admin/settings"),
  updateAdminSettings: (settings: AdminSettings) =>
    fetchJson<AdminSettings>("/api/admin/settings", {
      method: "PUT",
      body: JSON.stringify(settings),
    }),
  previewAdminPdf: async (settings: QuotePdfSettings) => {
    const response = await fetch("/api/admin/settings/pdf-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/pdf" },
      body: JSON.stringify(settings),
    });
    if (!response.ok) {
      let message = await response.text();
      try {
        const payload = JSON.parse(message) as { detail?: string };
        message = payload.detail ?? message;
      } catch {
        // Retain the public response text.
      }
      throw new ApiError(message || `Request failed (${response.status})`, response.status);
    }
    return response.blob();
  },
  runrate: () => fetchJson<Record<string, unknown>>("/api/intelligence/overpay-runrate"),
  createDraft: (accountId: string, role: ViewRole) =>
    fetchJson<DraftOrder>("/api/draft-orders", {
      method: "POST",
      body: JSON.stringify({ account_id: accountId, line_items: [], view_role: role }),
    }),
  resumeDraft: (accountId: string, role: ViewRole) =>
    fetchJson<{ draft: DraftOrder | null }>(`/api/draft-orders/resume?account_id=${encodeURIComponent(accountId)}&view_role=${role}`),
  getDraft: (draftId: string, role: ViewRole) =>
    fetchJson<DraftOrder>(`/api/draft-orders/${encodeURIComponent(draftId)}?view_role=${role}`),
  createRevision: (draftId: string, role: ViewRole) =>
    fetchJson<DraftOrder>(`/api/draft-orders/${encodeURIComponent(draftId)}/revisions`, {
      method: "POST",
      body: JSON.stringify({ view_role: role }),
    }),
  patchDraft: (draftId: string, lines: DraftLineItem[], role: ViewRole, expectedVersion?: number) =>
    fetchJson<DraftOrder>(`/api/draft-orders/${encodeURIComponent(draftId)}`, {
      method: "PATCH",
      body: JSON.stringify({ line_items: lines, view_role: role, expected_version: expectedVersion }),
    }),
  addLine: (draftId: string, accountId: string, sku: string, role: ViewRole, expectedVersion?: number) =>
    fetchJson<DraftOrder>("/api/quote/add-line", {
      method: "POST",
      body: JSON.stringify({ draft_order_id: draftId, account_id: accountId, sku, quantity: 1, view_role: role, expected_version: expectedVersion }),
    }),
  setPrice: (draftId: string, accountId: string, sku: string, unitPrice: number, role: ViewRole, expectedVersion?: number) =>
    fetchJson<DraftOrder>("/api/quote/set-price", {
      method: "POST",
      body: JSON.stringify({ draft_order_id: draftId, account_id: accountId, sku, unit_price: unitPrice, view_role: role, expected_version: expectedVersion }),
    }),
  saveDraft: (draftId: string, role: ViewRole) => fetchJson<DraftOrder>(`/api/draft-orders/${encodeURIComponent(draftId)}/save?view_role=${role}`, { method: "POST" }),
  generateQuotePdf: async (draftId: string, role: ViewRole) => {
    const response = await fetch(`/api/draft-orders/${encodeURIComponent(draftId)}/quote.pdf?view_role=${role}`, {
      method: "POST",
      headers: { Accept: "application/pdf" },
    });
    if (!response.ok) {
      let message = await response.text();
      try {
        const payload = JSON.parse(message) as { detail?: string };
        message = payload.detail ?? message;
      } catch {
        // Retain the public response text.
      }
      throw new ApiError(message || `Request failed (${response.status})`, response.status);
    }
    const disposition = response.headers.get("Content-Disposition") ?? "";
    const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || `quote-${draftId}.pdf`;
    return { blob: await response.blob(), filename };
  },
  history: (accountId: string, role: ViewRole) => fetchJson<HistoryResponse>(`/api/history?account_id=${encodeURIComponent(accountId)}&view_role=${role}`),
  deleteDraft: (draftId: string) => fetchJson<{ deleted: boolean }>(`/api/draft-orders/${encodeURIComponent(draftId)}`, { method: "DELETE" }),
  products: (query: string, role: ViewRole = "seller", signal?: AbortSignal) =>
    fetchJson<SearchResponse<Product>>(
      `/api/products/search?q=${encodeURIComponent(query)}&view_role=${role}`,
      { signal },
    ),
  accounts: (query: string, signal?: AbortSignal) =>
    fetchJson<SearchResponse<Account>>(
      `/api/accounts/search?q=${encodeURIComponent(query)}`,
      { signal },
    ),
  recommendationForRole: (draftId: string, role: ViewRole) =>
    fetchJson<Recommendation>("/api/recommendation/view", {
      method: "POST",
      body: JSON.stringify({ draft_order_id: draftId, view_role: role }),
    }),
  applyRecommendation: (draftId: string, recommendationId: string, expectedRevision: number, mode: "add" | "replace", role: ViewRole) =>
    fetchJson<{ order: DraftOrder; recommendation_id: string; revision: number; mode: string; already_applied: boolean }>(`/api/draft-orders/${encodeURIComponent(draftId)}/recommendations/apply`, {
      method: "POST",
      body: JSON.stringify({ recommendation_id: recommendationId, expected_revision: expectedRevision, mode, view_role: role }),
    }),
  activePlan: (draftId: string, role: ViewRole) =>
    fetchOptionalJson<QuotePlan>(`/api/draft-orders/${encodeURIComponent(draftId)}/agent-plan?view_role=${role}`),
  selectPlanScenario: (planId: string, scenarioId: string, request: PlanMutationRequest) =>
    fetchJson<QuotePlan>(`/api/agent/plans/${encodeURIComponent(planId)}/scenarios/${encodeURIComponent(scenarioId)}/select`, {
      method: "POST",
      body: JSON.stringify(request),
    }),
  resumePlan: (planId: string, request: PlanResumeRequest) =>
    fetchJson<QuotePlan>(`/api/agent/plans/${encodeURIComponent(planId)}/resume`, {
      method: "POST",
      body: JSON.stringify(request),
    }),
  cancelPlan: (planId: string, request: PlanMutationRequest) =>
    fetchJson<QuotePlan>(`/api/agent/plans/${encodeURIComponent(planId)}/cancel`, {
      method: "POST",
      body: JSON.stringify(request),
    }),
  confirmPlanPdf: (planId: string, request: PlanConfirmApplyRequest) =>
    fetchJson<PlanApplyResponse>(`/api/agent/plans/${encodeURIComponent(planId)}/confirm-pdf`, {
      method: "POST",
      body: JSON.stringify(request),
    }),
  confirmPlanApply: (planId: string, request: PlanConfirmApplyRequest) =>
    fetchJson<PlanApplyResponse>(`/api/agent/plans/${encodeURIComponent(planId)}/confirm-apply`, {
      method: "POST",
      body: JSON.stringify(request),
    }),
  followups: (draftId: string, accountId: string, role: ViewRole, signal?: AbortSignal) =>
    fetchJson<FollowupSuggestionsResponse>("/api/followups", {
      method: "POST",
      body: JSON.stringify({
        draft_order_id: draftId,
        account_id: accountId,
        view_role: role,
      }),
      signal,
    }),
  agentQuery: (request: AgentRequest, signal?: AbortSignal) =>
    fetchJson<Recommendation | QuotePlan | (Record<string, unknown> & { answer?: string; mode?: string })>("/api/agent/query", {
      method: "POST",
      body: JSON.stringify(request),
      signal,
    }),
};

export interface AgentRequest {
  query: string;
  intent: AgentIntent;
  account_id: string;
  view_role: ViewRole;
  draft_order_id: string;
  current_order_lines: DraftLineItem[];
  conversation_history: Array<{ role: string; content: string }>;
  recommendation_context: Record<string, unknown>;
  genie_conversation_id?: string | null;
  expected_revision?: number;
}

export interface PlanMutationRequest {
  expected_plan_revision: number;
  expected_draft_version: number;
  view_role: ViewRole;
}

export interface PlanConfirmApplyRequest extends PlanMutationRequest {
  confirmation_token: string;
  idempotency_key: string;
}

export interface PlanResumeRequest extends PlanMutationRequest {
  input: string;
}

export interface PlanApplyResponse {
  plan: QuotePlan;
  order: DraftOrder;
}

export async function streamAgent(
  request: AgentRequest,
  signal: AbortSignal,
  onEvent: (event: AgentStreamEvent) => void,
): Promise<void> {
  const response = await fetch("/api/agent/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(request),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new ApiError(response.ok ? "The agent stream was empty." : await response.text(), response.status);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const frames = buffer.split(/\r\n\r\n|\n\n|\r\r/);
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const parsed = parseSseFrame(frame);
      if (parsed) onEvent(parsed);
    }
    if (done) break;
  }
  if (buffer.trim()) {
    const parsed = parseSseFrame(buffer);
    if (parsed) onEvent(parsed);
  }
}

export function parseSseFrame(frame: string): AgentStreamEvent | null {
  let eventName = "message";
  const data: string[] = [];
  for (const line of frame.replace(/^\uFEFF/, "").split(/\r\n|\r|\n/)) {
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  if (!data.length || !["stage", "plan", "recommendation", "conversation", "error", "done"].includes(eventName)) return null;
  try {
    return { event: eventName, data: JSON.parse(data.join("\n")) } as AgentStreamEvent;
  } catch {
    return null;
  }
}
