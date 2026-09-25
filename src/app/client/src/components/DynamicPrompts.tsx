import { Button, Skeleton } from "@databricks/appkit-ui/react";
import { RefreshCw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type { ConversationMessage, DraftLineItem, ViewRole } from "../types";

type SuggestionStatus = "idle" | "loading" | "ready" | "error";

interface DynamicPromptsProps {
  accountId?: string;
  draftOrderId?: string;
  draftVersion?: number;
  draftStatus?: string;
  lines: DraftLineItem[];
  messages: ConversationMessage[];
  role: ViewRole;
  ready: boolean;
  disabled?: boolean;
  emptyConversation?: boolean;
  onSelect: (prompt: string) => void;
}

export function DynamicPrompts({
  accountId,
  draftOrderId,
  draftVersion,
  draftStatus,
  lines,
  messages,
  role,
  ready,
  disabled,
  emptyConversation,
  onSelect,
}: DynamicPromptsProps) {
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [status, setStatus] = useState<SuggestionStatus>("idle");
  const [refreshVersion, setRefreshVersion] = useState(0);
  const requestVersion = useRef(0);
  const quoteContextKey = useMemo(
    () => JSON.stringify(lines.map((line) => ({
      sku: line.sku,
      quantity: line.quantity,
      unit_price: line.unit_price,
      approval_required: Boolean(line.approval_required),
      approval_reason: line.approval_reason ?? "",
    }))),
    [lines],
  );
  const conversationContextKey = useMemo(
    () => JSON.stringify(messages.slice(-8).map((message) => ({
      id: message.id,
      role: message.role,
      kind: message.kind,
      content: messageContent(message),
    }))),
    [messages],
  );

  useEffect(() => {
    const version = requestVersion.current + 1;
    requestVersion.current = version;

    if (!ready || disabled || !accountId || !draftOrderId) {
      if (!accountId || !draftOrderId) {
        setSuggestions([]);
        setStatus("idle");
      }
      return;
    }

    const controller = new AbortController();
    setSuggestions([]);
    setStatus("loading");
    void api.followups(draftOrderId, accountId, role, controller.signal)
      .then((response) => {
        if (controller.signal.aborted || requestVersion.current !== version) return;
        setSuggestions(normalizeSuggestions(response.suggestions));
        setStatus("ready");
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted || requestVersion.current !== version || isAbortError(cause)) return;
        setSuggestions([]);
        setStatus("error");
      });

    return () => controller.abort();
  }, [
    accountId,
    conversationContextKey,
    disabled,
    draftOrderId,
    draftStatus,
    draftVersion,
    quoteContextKey,
    ready,
    refreshVersion,
    role,
  ]);

  if (!ready || disabled || !accountId || !draftOrderId || status === "idle") return null;

  const className = `dynamic-prompts${emptyConversation ? " dynamic-prompts-empty" : ""}`;

  if (status === "loading") {
    return (
      <div className={`${className} dynamic-prompts-loading`} role="status" aria-label="Preparing suggestions">
        {[0, 1, 2].map((row) => <Skeleton key={row} />)}
      </div>
    );
  }

  if (status === "error" || suggestions.length === 0) {
    return (
      <div className={`${className} dynamic-prompts-unavailable`}>
        <span role="status">{status === "error" ? "Suggestions are temporarily unavailable." : "No tailored suggestions yet."}</span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setRefreshVersion((current) => current + 1)}
        >
          <RefreshCw aria-hidden="true" /> Refresh
        </Button>
      </div>
    );
  }

  return (
    <div className={className} role="group" aria-label="Suggested prompts">
      {suggestions.map((suggestion) => (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="dynamic-prompt"
          onClick={() => onSelect(suggestion)}
          key={suggestion}
        >
          {suggestion}
        </Button>
      ))}
    </div>
  );
}

function normalizeSuggestions(values: unknown): string[] {
  if (!Array.isArray(values)) return [];
  const unique: string[] = [];
  for (const value of values) {
    if (typeof value !== "string") continue;
    const suggestion = value.trim();
    if (!suggestion || suggestion.length > 120 || unique.includes(suggestion)) continue;
    unique.push(suggestion);
    if (unique.length === 4) break;
  }
  return unique;
}

function messageContent(message: ConversationMessage): string {
  if (message.role === "user" || message.kind === "answer" || message.kind === "error") {
    return message.content.slice(0, 400);
  }
  return message.recommendation.summary.slice(0, 400);
}

function isAbortError(cause: unknown): boolean {
  return cause instanceof DOMException && cause.name === "AbortError";
}
