import { Check, CircleDollarSign, ClipboardCheck, FileDown, PackagePlus } from "lucide-react";
import { QUOTE_APPROVAL_THRESHOLD } from "../domain";
import type { DraftOrder } from "../types";

interface QuoteLifecycleProps {
  draft: DraftOrder | null;
  approvalThreshold?: number;
}

const STEPS = [
  { label: "Configure", icon: PackagePlus },
  { label: "Price", icon: CircleDollarSign },
  { label: "Review", icon: ClipboardCheck },
  { label: "Generate", icon: FileDown },
] as const;

type StepState = "complete" | "current" | "upcoming";

export function QuoteLifecycle({ draft, approvalThreshold = QUOTE_APPROVAL_THRESHOLD }: QuoteLifecycleProps) {
  const lines = draft?.line_items ?? [];
  const quoteCreated = Boolean(draft?.quote_id) || draft?.status === "quote-created";
  const needsApproval = lines.some((line) => Boolean(line.approval_required))
    || Number(draft?.grand_total ?? 0) > approvalThreshold;
  const currentStep = quoteCreated ? STEPS.length - 1 : lines.length === 0 ? 0 : needsApproval ? 1 : 2;

  return (
    <nav className="quote-lifecycle" aria-label="Quote lifecycle">
      <span className="sr-only">Quote lifecycle</span>
      <ol className="quote-lifecycle-list">
        {STEPS.map((step, index) => {
          const state: StepState = quoteCreated || index < currentStep
            ? "complete"
            : index === currentStep
              ? "current"
              : "upcoming";
          const Icon = state === "complete" ? Check : step.icon;
          const isCurrent = index === currentStep;

          return (
            <li
              className="quote-lifecycle-step"
              data-state={state}
              aria-current={isCurrent ? "step" : undefined}
              aria-label={`${step.label} — ${state}`}
              key={step.label}
            >
              <span className="quote-lifecycle-marker" aria-hidden="true">
                <Icon />
              </span>
              <span className="quote-lifecycle-label">{step.label}</span>
              {index < STEPS.length - 1 && <span className="quote-lifecycle-connector" aria-hidden="true" />}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
