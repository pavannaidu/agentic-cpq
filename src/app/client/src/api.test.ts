import { afterEach, describe, expect, it, vi } from "vitest";
import { api, parseSseFrame, quotePdfUrl, streamAgent, type AgentRequest } from "./api";

const REQUEST: AgentRequest = {
  query: "Build a two-operatory quote",
  intent: "build",
  account_id: "account-1",
  view_role: "seller",
  draft_order_id: "draft-1",
  current_order_lines: [],
  conversation_history: [],
  recommendation_context: {},
};

afterEach(() => vi.restoreAllMocks());

describe("quotePdfUrl", () => {
  it("builds distinct inline and download URLs for an immutable quote", () => {
    expect(quotePdfUrl("draft/one", "seller")).toBe(
      "/api/draft-orders/draft%2Fone/quote.pdf?view_role=seller",
    );
    expect(quotePdfUrl("draft/one", "manager", true)).toBe(
      "/api/draft-orders/draft%2Fone/quote.pdf?view_role=manager&download=true",
    );
  });
});

describe("admin settings API", () => {
  it("uses the protected settings endpoints and replaces the complete document", async () => {
    const settings = {
      pdf: {
        layout: "compact" as const,
        show_list_prices: false,
        show_savings: true,
        brand_name: "Northstar",
        document_title: "Customer quote",
        accent_color: "#112233",
        footer_text: "Prepared for review",
        terms_text: "Valid for 14 days.",
        validity_days: 14,
      },
      behavior: {
        approval_threshold: 50000,
        max_seller_discount_pct: 15,
        auto_attach_care_plan: true,
        allow_seller_price_edits: false,
      },
    };
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify(settings), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(settings), { status: 200 }));

    await api.getAdminSettings();
    await api.updateAdminSettings(settings);

    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/admin/settings", expect.objectContaining({ headers: expect.any(Object) }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/admin/settings", expect.objectContaining({
      method: "PUT",
      body: JSON.stringify(settings),
    }));
  });

  it("renders unsaved document settings through the PDF preview endpoint", async () => {
    const pdfSettings = {
      layout: "compact" as const,
      show_list_prices: false,
      show_savings: true,
      brand_name: "Northstar",
      document_title: "Customer quote",
      accent_color: "#112233",
      footer_text: "Prepared for review",
      terms_text: "Valid for 14 days.",
      validity_days: 14,
    };
    const expected = new Blob(["%PDF-preview"], { type: "application/pdf" });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(expected, { status: 200, headers: { "Content-Type": "application/pdf" } }),
    );

    const preview = await api.previewAdminPdf(pdfSettings);

    expect(preview.type).toBe("application/pdf");
    expect(fetchMock).toHaveBeenCalledWith("/api/admin/settings/pdf-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/pdf" },
      body: JSON.stringify(pdfSettings),
    });
  });
});

describe("search API", () => {
  it("forwards AbortSignals to encoded product and account searches", async () => {
    const controller = new AbortController();
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ results: [] }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ results: [] }), { status: 200 }));

    await api.products("same-day crown", "manager", controller.signal);
    await api.accounts("Austin & Round Rock", controller.signal);

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/products/search?q=same-day%20crown&view_role=manager",
      expect.objectContaining({ signal: controller.signal }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/accounts/search?q=Austin%20%26%20Round%20Rock",
      expect.objectContaining({ signal: controller.signal }),
    );
  });
});

describe("follow-up suggestions API", () => {
  it("posts only authoritative draft context and forwards cancellation", async () => {
    const controller = new AbortController();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ suggestions: ["Review approval blockers"] }), { status: 200 }),
    );

    await api.followups("draft/one", "account-1", "manager", controller.signal);

    expect(fetchMock).toHaveBeenCalledWith("/api/followups", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        draft_order_id: "draft/one",
        account_id: "account-1",
        view_role: "manager",
      }),
      signal: controller.signal,
    }));
  });
});

describe("quote plan API", () => {
  const plan = {
    plan_id: "plan-1",
    account_id: "account-1",
    draft_order_id: "draft/one",
    base_draft_version: 4,
    revision: 2,
    goal: "Build an imaging quote",
    status: "needs_input" as const,
  };
  const mutation = {
    expected_plan_revision: 2,
    expected_draft_version: 4,
    view_role: "seller" as const,
  };

  it("rehydrates an optional draft-scoped plan", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(plan), { status: 200 }));

    expect(await api.activePlan("draft/one", "manager")).toBeNull();
    expect(await api.activePlan("draft/one", "manager")).toEqual(plan);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/draft-orders/draft%2Fone/agent-plan?view_role=manager",
      expect.objectContaining({ headers: expect.any(Object) }),
    );
  });

  it("binds resume, selection, cancellation, apply, and PDF confirmation to plan versions", async () => {
    const applyResponse = { plan, order: { draft_order_id: "draft/one", account_id: "account-1", status: "draft", line_items: [], subtotal: 0, grand_total: 0 } };
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify(plan), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(plan), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(plan), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(applyResponse), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(applyResponse), { status: 200 }));
    const confirmation = { ...mutation, confirmation_token: "token-1", idempotency_key: "idem-1" };

    await api.resumePlan("plan/one", { ...mutation, input: "Three operatories" });
    await api.selectPlanScenario("plan/one", "scenario/one", mutation);
    await api.cancelPlan("plan/one", mutation);
    await api.confirmPlanApply("plan/one", confirmation);
    await api.confirmPlanPdf("plan/one", confirmation);

    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/agent/plans/plan%2Fone/resume", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ ...mutation, input: "Three operatories" }),
    }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/agent/plans/plan%2Fone/scenarios/scenario%2Fone/select", expect.objectContaining({
      method: "POST",
      body: JSON.stringify(mutation),
    }));
    expect(fetchMock).toHaveBeenNthCalledWith(3, "/api/agent/plans/plan%2Fone/cancel", expect.objectContaining({ body: JSON.stringify(mutation) }));
    expect(fetchMock).toHaveBeenNthCalledWith(4, "/api/agent/plans/plan%2Fone/confirm-apply", expect.objectContaining({ body: JSON.stringify(confirmation) }));
    expect(fetchMock).toHaveBeenNthCalledWith(5, "/api/agent/plans/plan%2Fone/confirm-pdf", expect.objectContaining({ body: JSON.stringify(confirmation) }));
  });
});

describe("parseSseFrame", () => {
  it("parses supported JSON events", () => {
    expect(parseSseFrame('event: stage\ndata: {"key":"research","label":"Researching"}')).toEqual({
      event: "stage",
      data: { key: "research", label: "Researching" },
    });
  });

  it("parses quote plan snapshots without changing their snake_case contract", () => {
    expect(parseSseFrame('event: plan\ndata: {"plan_id":"plan-1","account_id":"account-1","draft_order_id":"draft-1","base_draft_version":4,"revision":2,"goal":"Build a quote","status":"ready"}')).toEqual({
      event: "plan",
      data: {
        plan_id: "plan-1",
        account_id: "account-1",
        draft_order_id: "draft-1",
        base_draft_version: 4,
        revision: 2,
        goal: "Build a quote",
        status: "ready",
      },
    });
  });

  it("supports CRLF, a UTF-8 BOM, and multiline data", () => {
    expect(parseSseFrame('\uFEFFevent: conversation\r\ndata: {"answer":\r\ndata: "Ready"}')).toEqual({
      event: "conversation",
      data: { answer: "Ready" },
    });
  });

  it("ignores unknown events and malformed JSON", () => {
    expect(parseSseFrame('event: heartbeat\ndata: {"ok":true}')).toBeNull();
    expect(parseSseFrame("event: stage\ndata: not-json")).toBeNull();
    expect(parseSseFrame("event: stage")).toBeNull();
  });
});

describe("streamAgent", () => {
  it("emits complete LF and CRLF frames split across network chunks", async () => {
    const encoder = new TextEncoder();
    const chunks = [
      'event: stage\r\ndata: {"key":"route","status":"active"}\r',
      '\n\r\nevent: recommendation\ndata: {"summary":"Ready","items":[]}',
      '\n\nevent: done\r\ndata: {}\r\n\r\n',
    ];
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
        controller.close();
      },
    });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } }),
    );
    const events: unknown[] = [];

    await streamAgent(REQUEST, new AbortController().signal, (event) => events.push(event));

    expect(events).toEqual([
      { event: "stage", data: { key: "route", status: "active" } },
      { event: "recommendation", data: { summary: "Ready", items: [] } },
      { event: "done", data: {} },
    ]);
    expect(fetchMock).toHaveBeenCalledWith("/api/agent/stream", expect.objectContaining({
      method: "POST",
      body: JSON.stringify(REQUEST),
    }));
  });

  it("parses a final unterminated frame", async () => {
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('event: conversation\ndata: {"answer":"Complete"}'));
        controller.close();
      },
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(body, { status: 200 }));
    const onEvent = vi.fn();

    await streamAgent(REQUEST, new AbortController().signal, onEvent);

    expect(onEvent).toHaveBeenCalledOnce();
    expect(onEvent).toHaveBeenCalledWith({ event: "conversation", data: { answer: "Complete" } });
  });
});
