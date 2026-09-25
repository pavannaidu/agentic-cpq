import { Button, Spinner } from "@databricks/appkit-ui/react";
import { CircleStop } from "lucide-react";
import type { AgentStage, PlanStep, QuotePlanStatus } from "../types";

interface AgentProgressProps {
  stages?: AgentStage[];
  steps?: PlanStep[];
  planStatus?: QuotePlanStatus;
  onCancel: () => void | Promise<void>;
}

export function AgentProgress({ stages = [], steps = [], planStatus, onCancel }: AgentProgressProps) {
  const planCopy = planStatus ? planProgressCopy(steps, planStatus) : null;

  return (
    <div className="agent-progress" role="status" aria-label={planStatus ? "Quote plan progress" : "Genie progress"}>
      <Spinner />
      {planCopy ? (
        <span className="agent-progress-copy">
          <strong>{planCopy.title}</strong>
          {planCopy.detail && <small>{planCopy.detail}</small>}
        </span>
      ) : <span>{progressLabel(stages)}</span>}
      <Button variant="ghost" size="sm" onClick={() => void onCancel()}>
        <CircleStop aria-hidden="true" /> {planStatus ? "Cancel plan" : "Cancel"}
      </Button>
    </div>
  );
}

function planProgressCopy(steps: PlanStep[], status: QuotePlanStatus): { title: string; detail: string } {
  const completed = steps.filter((step) => /completed|skipped/i.test(step.status)).length;
  const current = steps.find((step) => step.status === "in_progress")
    ?? steps.find((step) => !/completed|skipped/i.test(step.status));
  const currentLabel = current?.title || "";
  const detail = steps.length
    ? `${completed} of ${steps.length}${currentLabel ? ` · Next: ${currentLabel}` : ""}`
    : "";
  return {
    title: status === "applying" ? "Applying confirmed changes…" : "Building quote options…",
    detail,
  };
}

function progressLabel(stages: AgentStage[]): string {
  const key = [...stages].reverse().find((stage) => stage.status === "active")?.key
    ?? stages.at(-1)?.key
    ?? "";
  if (/price|quote|structured|data|genie/i.test(key)) return "Checking quote data…";
  if (/source|guidance|knowledge|search|web/i.test(key)) return "Checking sources…";
  return "Working…";
}
