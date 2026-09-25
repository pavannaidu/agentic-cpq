import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupTextarea,
  ScrollArea,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@databricks/appkit-ui/react";
import {
  ArrowUp,
  FileSearch,
  PanelRightClose,
  RefreshCw,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { safeExternalUrl } from "../domain";
import type { AgentStage, ConversationMessage, DraftLineItem, Evidence, QuotePlan, ViewRole } from "../types";
import { AgentProgress } from "./AgentProgress";
import { DynamicPrompts } from "./DynamicPrompts";
import { QuotePlanPresentation, QuotePlanSkeleton } from "./QuotePlanPresentation";
import { RecommendationCard } from "./RecommendationCard";

interface CopilotPanelProps {
  messages: ConversationMessage[];
  stages: AgentStage[];
  currentLines: DraftLineItem[];
  accountId?: string;
  draftOrderId?: string;
  currentDraftStatus?: string;
  currentDraftVersion?: number;
  role: ViewRole;
  activePlan?: QuotePlan | null;
  planLoading?: boolean;
  executionIdentity?: string;
  busy?: boolean;
  applyBusy?: boolean;
  ready?: boolean;
  onSubmit: (prompt: string) => Promise<void>;
  onCancel: () => void;
  onApply: (messageId: string) => Promise<void>;
  onPlanSelect?: (scenarioId: string) => Promise<void>;
  onPlanConfirm?: () => Promise<void>;
  onPlanCancel?: () => Promise<void>;
  onPlanReload?: () => Promise<void>;
  onEvidence: (evidence: Evidence) => void;
  onCollapse?: () => void;
}

export function CopilotPanel({
  messages,
  stages,
  currentLines,
  accountId,
  draftOrderId,
  currentDraftStatus,
  currentDraftVersion,
  role,
  activePlan,
  planLoading,
  executionIdentity,
  busy,
  applyBusy,
  ready = true,
  onSubmit,
  onCancel,
  onApply,
  onPlanSelect = async () => undefined,
  onPlanConfirm = async () => undefined,
  onPlanCancel = async () => undefined,
  onPlanReload = async () => undefined,
  onEvidence,
  onCollapse,
}: CopilotPanelProps) {
  const [prompt, setPrompt] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const controlsBusy = Boolean(busy || applyBusy || !ready);

  useEffect(() => {
    if (messages.length || busy) {
      endRef.current?.scrollIntoView({ block: "nearest", behavior: messages.length > 1 ? "smooth" : "auto" });
    }
  }, [activePlan, busy, messages, planLoading, stages]);

  useEffect(() => {
    setPrompt("");
  }, [draftOrderId]);

  const submit = async (value = prompt) => {
    const trimmed = value.trim();
    if (!trimmed || controlsBusy) return;
    setPrompt("");
    await onSubmit(trimmed);
  };

  return (
    <section className="copilot-workspace" aria-labelledby="copilot-title">
      <header className="copilot-header">
        <div className="copilot-header-copy">
          <div className="copilot-title-line">
            <h2 id="copilot-title">Genie</h2>
          </div>
        </div>
        <div className="copilot-header-actions">
          {onCollapse && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon-sm" onClick={onCollapse} aria-label="Collapse Genie">
                  <PanelRightClose aria-hidden="true" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Collapse Genie</TooltipContent>
            </Tooltip>
          )}
        </div>
      </header>

      <ScrollArea className="conversation-scroll">
        <div className="conversation-log" role="log" aria-live="polite" aria-busy={busy} aria-label="Genie conversation">
          {messages.length === 0 && !activePlan && !planLoading ? (
            <div className="copilot-empty-state">
              <p>Ask about this quote or request changes.</p>
            </div>
          ) : messages.map((message) => {
              if (message.role === "user") {
                return (
                  <div className="message-row message-user" aria-label="Your message" key={message.id}>
                    <p>{message.content}</p>
                  </div>
                );
              }
              if (message.kind === "recommendation") {
                return (
                  <div className="message-row message-agent message-recommendation" key={message.id}>
                    <RecommendationCard
                      recommendation={message.recommendation}
                      currentLines={currentLines}
                      currentDraftVersion={currentDraftVersion}
                      role={role}
                      applied={message.applied}
                      busy={busy || applyBusy}
                      onApply={() => onApply(message.id)}
                      onRefresh={() => submit("Update the proposal for the current quote.")}
                      onEvidence={onEvidence}
                      evidence={message.evidence}
                    />
                  </div>
                );
              }
              if (message.kind === "answer") {
                return (
                  <article className="message-answer" key={message.id}>
                    {message.error && <Badge variant="destructive" className="answer-status">Some information unavailable</Badge>}
                    <div className="answer-copy">{renderAnswer(message.content || "Response unavailable.")}</div>
                    <div className="answer-footer">
                      <Button variant="outline" size="sm" onClick={() => onEvidence(message.evidence)}><FileSearch aria-hidden="true" /> Details</Button>
                    </div>
                  </article>
                );
              }
              return (
                <Alert variant="destructive" className="message-error" key={message.id}>
                  <AlertDescription>
                    <span>{message.content}</span>
                    {message.retryPrompt && (
                      <Button variant="outline" size="sm" disabled={controlsBusy} onClick={() => void submit(message.retryPrompt)}>
                        <RefreshCw aria-hidden="true" /> Retry
                      </Button>
                    )}
                  </AlertDescription>
                </Alert>
              );
            })}

          {planLoading ? <QuotePlanSkeleton /> : activePlan ? (
            <QuotePlanPresentation
              plan={activePlan}
              currentLines={currentLines}
              currentDraftVersion={currentDraftVersion}
              role={role}
              executionIdentity={executionIdentity}
              busy={controlsBusy}
              onSelectScenario={onPlanSelect}
              onConfirm={onPlanConfirm}
              onCancel={onPlanCancel}
              onRefresh={() => submit("Update this plan for the current quote.")}
              onPlanReload={onPlanReload}
              onEvidence={onEvidence}
            />
          ) : (
            <DynamicPrompts
              accountId={accountId}
              draftOrderId={draftOrderId}
              draftVersion={currentDraftVersion}
              draftStatus={currentDraftStatus}
              lines={currentLines}
              messages={messages}
              role={role}
              ready={ready}
              disabled={controlsBusy}
              emptyConversation={messages.length === 0}
              onSelect={(suggestion) => { void submit(suggestion); }}
            />
          )}

          {busy && !activePlan && !planLoading && <AgentProgress stages={stages} onCancel={onCancel} />}
          <div ref={endRef} />
        </div>
      </ScrollArea>

      <div className="copilot-composer">
        <form onSubmit={(event) => { event.preventDefault(); void submit(); }}>
          <InputGroup className="composer-input-group">
            <InputGroupTextarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                  event.preventDefault();
                  void submit();
                }
              }}
              disabled={controlsBusy}
              placeholder="Message Genie…"
              aria-label="Message Genie"
              rows={1}
            />
            <InputGroupAddon align="block-end" className="composer-addon">
              <InputGroupButton type="submit" size="icon-sm" variant="default" disabled={controlsBusy || !prompt.trim()} aria-label="Send message">
                <ArrowUp aria-hidden="true" />
              </InputGroupButton>
            </InputGroupAddon>
          </InputGroup>
        </form>
        <p className="copilot-disclaimer">AI-generated. Review Details for sources and query.</p>
      </div>
    </section>
  );
}

function renderAnswer(value: string): ReactNode[] {
  const linkPattern = /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)|(https?:\/\/[^\s),;]+)/g;
  const nodes: ReactNode[] = [];
  let cursor = 0;
  for (const match of value.matchAll(linkPattern)) {
    const index = match.index ?? 0;
    if (index > cursor) nodes.push(value.slice(cursor, index));
    const rawUrl = match[2] || match[3];
    const url = safeExternalUrl(rawUrl.replace(/(?:%20)+$/i, ""));
    nodes.push(url ? (
      <a href={url} target="_blank" rel="noreferrer" key={`${index}-${url}`}>{match[1] || rawUrl}</a>
    ) : (match[1] || rawUrl));
    cursor = index + match[0].length;
  }
  if (cursor < value.length) nodes.push(value.slice(cursor));
  return nodes;
}
