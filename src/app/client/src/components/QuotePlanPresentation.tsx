import {
  Alert,
  AlertDescription,
  AlertTitle,
  Button,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
} from "@databricks/appkit-ui/react";
import { Check, RefreshCw, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { evidenceFromRecommendation } from "../domain";
import type { DraftLineItem, Evidence, QuotePlan, QuoteScenario, Recommendation, ViewRole } from "../types";
import { AgentProgress } from "./AgentProgress";
import { RecommendationCard } from "./RecommendationCard";

interface QuotePlanPresentationProps {
  plan: QuotePlan;
  currentLines: DraftLineItem[];
  currentDraftVersion?: number;
  role: ViewRole;
  executionIdentity?: string;
  busy?: boolean;
  onSelectScenario: (scenarioId: string) => Promise<void>;
  onConfirm: () => Promise<void>;
  onCancel: () => Promise<void>;
  onRefresh: () => Promise<void>;
  onPlanReload: () => Promise<void>;
  onEvidence: (evidence: Evidence) => void;
}

export function QuotePlanPresentation({
  plan,
  currentLines,
  currentDraftVersion,
  role,
  executionIdentity,
  busy,
  onSelectScenario,
  onConfirm,
  onCancel,
  onRefresh,
  onPlanReload,
  onEvidence,
}: QuotePlanPresentationProps) {
  const confirmationExpired = useConfirmationExpired(
    plan.status === "ready" ? plan.action_proposal?.confirmation?.expires_at : undefined,
  );

  if (plan.status === "cancelled") return null;

  if (plan.status === "planning" || plan.status === "applying") {
    return (
      <AgentProgress
        steps={plan.steps}
        planStatus={plan.status}
        onCancel={onCancel}
      />
    );
  }

  if (plan.status === "needs_input") {
    return (
      <div className="quote-plan-prompt" role="status" aria-label="Quote plan needs input">
        <div>
          <strong>One detail needed</strong>
          <span>{clarificationPrompt(plan) || "Reply below with the missing quote detail."}</span>
        </div>
        <Button variant="ghost" size="sm" disabled={busy} onClick={() => void onCancel()}>Cancel plan</Button>
      </div>
    );
  }

  if (plan.status === "failed") {
    return (
      <Alert variant="destructive" className="quote-plan-notice">
        <TriangleAlert aria-hidden="true" />
        <AlertTitle>Plan could not be completed</AlertTitle>
        <AlertDescription>
          <span>{plan.error_message || metadataText(plan, "message") || "Your quote was not changed."}</span>
          <Button variant="outline" size="sm" disabled={busy} onClick={() => void onRefresh()}>
            <RefreshCw aria-hidden="true" /> Try again
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  const scenarios = plan.scenarios ?? [];
  const selected = selectedScenario(plan, scenarios);
  const recommendation = selected?.recommendation
    ? recommendationForPlan(selected.recommendation, selected, plan)
    : null;
  const applied = plan.status === "completed"
    || plan.status === "ready_for_pdf"
    || plan.status === "awaiting_approval";
  const stale = !applied && (
    plan.status === "stale"
    || (currentDraftVersion != null && planDraftVersion(plan) !== currentDraftVersion)
  );
  const stepSummary = progressSummary(plan);
  const canCancel = plan.status === "ready";

  return (
    <div className="quote-plan-review" aria-label="Quote plan review" data-plan-status={plan.status}>
      {((!applied && Boolean(stepSummary)) || canCancel || confirmationExpired) && (
        <div className="quote-plan-meta">
          {!applied && (confirmationExpired || stepSummary) && (
            <p className="quote-plan-step-summary">
              {confirmationExpired ? "Confirmation expired. Refresh before applying." : stepSummary}
            </p>
          )}
          <div className="quote-plan-meta-actions">
            {confirmationExpired && (
              <Button variant="outline" size="sm" disabled={busy} onClick={() => void onPlanReload()}>
                <RefreshCw aria-hidden="true" /> Refresh confirmation
              </Button>
            )}
            {canCancel && (
              <Button variant="ghost" size="sm" disabled={busy} onClick={() => void onCancel()}>
                Cancel plan
              </Button>
            )}
          </div>
        </div>
      )}
      {plan.status === "ready" && scenarios.length > 1 && (
        <div className="quote-plan-scenario">
          <span>Option</span>
          <Select
            value={selected?.scenario_id}
            onValueChange={(scenarioId) => void onSelectScenario(scenarioId)}
            disabled={busy}
          >
            <SelectTrigger aria-label="Quote plan option">
              <SelectValue placeholder="Choose an option" />
            </SelectTrigger>
            <SelectContent>
              {scenarios.map((scenario) => (
                <SelectItem value={scenario.scenario_id} key={scenario.scenario_id}>
                  {scenarioLabel(scenario)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {plan.status === "awaiting_approval" && (
        <Alert className="quote-plan-notice">
          <AlertTitle>Approval required</AlertTitle>
          <AlertDescription>The confirmed changes are in the quote. Approval is required before its PDF can be generated.</AlertDescription>
        </Alert>
      )}

      {!recommendation ? (
        <Alert className="quote-plan-notice">
          {applied ? <Check aria-hidden="true" /> : undefined}
          <AlertTitle>{applied ? "Applied to quote" : scenarios.length > 1 ? "Choose an option" : "Plan unavailable"}</AlertTitle>
          <AlertDescription>
            {applied
              ? metadataText(plan, "summary") || "The confirmed changes are now in the quote."
              : scenarios.length > 1
                ? "Select an option to review its quote impact."
                : metadataText(plan, "message") || "Ask Genie to update this plan."}
          </AlertDescription>
        </Alert>
      ) : (
        <RecommendationCard
          recommendation={recommendation}
          currentLines={currentLines}
          currentDraftVersion={currentDraftVersion}
          role={role}
          applied={applied}
          authoritativeApplied={applied}
          busy={busy}
          forceStale={applied ? false : stale}
          primaryActionLabel="Confirm & apply"
          actionDisabled={plan.status !== "ready" || confirmationExpired || !plan.action_proposal?.confirmation?.token?.trim()}
          actionDisabledLabel={confirmationExpired
            ? "Confirmation expired"
            : plan.status === "awaiting_approval"
              ? "Awaiting approval"
              : "Confirmation unavailable"}
          onApply={onConfirm}
          onRefresh={onRefresh}
          onEvidence={onEvidence}
          evidence={evidenceFromRecommendation(recommendation, executionIdentity)}
        />
      )}
    </div>
  );
}

export function QuotePlanSkeleton() {
  return (
    <div className="quote-plan-skeleton" role="status" aria-label="Loading quote plan">
      <Skeleton />
      <Skeleton />
    </div>
  );
}

function selectedScenario(plan: QuotePlan, scenarios: QuoteScenario[]): QuoteScenario | undefined {
  const explicit = scenarios.find((scenario) => scenario.scenario_id === plan.selected_scenario_id);
  return explicit ?? (scenarios.length === 1 ? scenarios[0] : undefined);
}

function recommendationForPlan(recommendation: Recommendation, scenario: QuoteScenario, plan: QuotePlan): Recommendation {
  const action = plan.action_proposal;
  const applyMode = action?.payload?.apply_mode;
  return {
    ...recommendation,
    recommendation_id: action?.recommendation_id || scenario.recommendation_id || recommendation.recommendation_id,
    revision: action?.recommendation_revision ?? scenario.recommendation_revision ?? recommendation.revision,
    apply_mode: applyMode === "replace" || applyMode === "add" ? applyMode : recommendation.apply_mode,
    draft_version: recommendation.draft_version ?? plan.base_draft_version,
  };
}

function scenarioLabel(scenario: QuoteScenario): string {
  return scenario.title || scenario.summary || "Quote option";
}

function clarificationPrompt(plan: QuotePlan): string {
  if (typeof plan.metadata?.clarifying_question === "string") return plan.metadata.clarifying_question;
  const clarification = plan.metadata?.clarification;
  if (typeof clarification === "string") return clarification;
  if (clarification && typeof clarification === "object") {
    const value = clarification as Record<string, unknown>;
    if (typeof value.question === "string") return value.question;
    if (typeof value.prompt === "string") return value.prompt;
    if (typeof value.message === "string") return value.message;
  }
  return metadataText(plan, "question") || metadataText(plan, "message");
}

function metadataText(plan: QuotePlan, key: string): string {
  const value = plan.metadata?.[key];
  return typeof value === "string" ? value : "";
}

function progressSummary(plan: QuotePlan): string {
  const steps = plan.steps ?? [];
  if (!steps.length) return "";
  const completed = steps.filter((step) => step.status === "completed" || step.status === "skipped").length;
  const current = steps.find((step) => step.status === "in_progress" || step.status === "needs_input")
    ?? steps.find((step) => step.status === "pending");
  return `${completed} of ${steps.length} complete${current ? ` · Next: ${current.title}` : ""}`;
}

function planDraftVersion(plan: QuotePlan): number {
  if (
    (plan.status === "awaiting_approval" || plan.status === "ready_for_pdf" || plan.status === "completed")
    && typeof plan.metadata?.applied_draft_version === "number"
  ) {
    return plan.metadata.applied_draft_version;
  }
  return plan.base_draft_version;
}

function useConfirmationExpired(expiresAt?: string): boolean {
  const [expired, setExpired] = useState(() => confirmationHasExpired(expiresAt));

  useEffect(() => {
    if (!expiresAt) {
      setExpired(false);
      return;
    }
    const deadline = Date.parse(expiresAt);
    if (!Number.isFinite(deadline)) {
      setExpired(true);
      return;
    }

    let timer: number | undefined;
    const update = () => {
      const remaining = deadline - Date.now();
      setExpired(remaining <= 0);
      if (remaining > 0) {
        timer = window.setTimeout(update, Math.min(remaining, 2_147_483_647));
      }
    };
    update();
    return () => {
      if (timer != null) window.clearTimeout(timer);
    };
  }, [expiresAt]);

  return expired;
}

function confirmationHasExpired(expiresAt?: string): boolean {
  if (!expiresAt) return false;
  const deadline = Date.parse(expiresAt);
  return !Number.isFinite(deadline) || Date.now() >= deadline;
}
