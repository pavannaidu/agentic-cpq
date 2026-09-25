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
  AlertDialogTrigger,
  Badge,
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
  Separator,
} from "@databricks/appkit-ui/react";
import { Check, FileSearch, RefreshCw, TriangleAlert } from "lucide-react";
import { computeQuoteDiff, currency, lineTotal } from "../domain";
import type { DraftLineItem, Evidence, Recommendation, ViewRole } from "../types";

interface RecommendationCardProps {
  recommendation: Recommendation;
  currentLines: DraftLineItem[];
  currentDraftVersion?: number;
  role: ViewRole;
  applied?: boolean;
  authoritativeApplied?: boolean;
  busy?: boolean;
  forceStale?: boolean;
  primaryActionLabel?: string;
  actionDisabled?: boolean;
  actionDisabledLabel?: string;
  onApply: () => Promise<void>;
  onRefresh?: () => Promise<void>;
  onEvidence: (evidence: Evidence) => void;
  evidence: Evidence;
}

export function RecommendationCard({
  recommendation,
  currentLines,
  currentDraftVersion,
  role,
  applied,
  authoritativeApplied,
  busy,
  forceStale,
  primaryActionLabel,
  actionDisabled,
  actionDisabledLabel,
  onApply,
  onRefresh,
  onEvidence,
  evidence,
}: RecommendationCardProps) {
  const mode = recommendation.apply_mode === "replace" ? "replace" : "add";
  const diff = computeQuoteDiff(currentLines, recommendation.items ?? [], mode);
  const changes = diff.added.length + diff.removed.length + diff.changed.length;
  const appliedAndCurrent = Boolean(authoritativeApplied || (applied && changes === 0));
  const appliedTotal = authoritativeApplied ? diff.currentTotal : diff.proposedTotal;
  const stale = !appliedAndCurrent && Boolean(
    forceStale
    || (
      recommendation.draft_version != null
      && currentDraftVersion != null
      && recommendation.draft_version !== currentDraftVersion
    ),
  );
  const applyReady = Boolean(recommendation.recommendation_id?.trim()) && recommendation.revision != null;
  const approvalLabel = diff.proposedApproval
    ? diff.currentApproval ? "Still required" : "Becomes required"
    : diff.currentApproval ? "Cleared" : "Clear";

  const applyButton = (
    <Button
      className="recommendation-apply"
      disabled={busy || appliedAndCurrent || (stale ? !onRefresh : changes === 0 || !applyReady || actionDisabled)}
      onClick={stale ? () => void onRefresh?.() : diff.removed.length ? undefined : () => void onApply()}
    >
      {stale ? <RefreshCw aria-hidden="true" /> : changes === 0 ? <Check aria-hidden="true" /> : null}
      {stale
        ? "Update proposal"
        : changes === 0
          ? "Quote already matches"
          : actionDisabled
            ? actionDisabledLabel || "Action unavailable"
            : !applyReady
            ? "Regenerate to apply"
            : primaryActionLabel || `Apply ${changes} change${changes === 1 ? "" : "s"}`}
    </Button>
  );

  return (
    <Card className="recommendation-card">
      <CardHeader>
        <CardTitle><h3>{recommendation.summary || "Proposed changes"}</h3></CardTitle>
      </CardHeader>
      <CardContent>
        {recommendation.bundle_rationale && <p className="recommendation-rationale">{recommendation.bundle_rationale}</p>}

        {appliedAndCurrent ? (
          <div className="recommendation-applied-state" role="status">
            <Check aria-hidden="true" />
            <span><strong>Applied to quote</strong><small>Current total {currency.format(appliedTotal)}</small></span>
          </div>
        ) : <><div className="recommendation-summary" aria-label="Recommendation impact">
          <SummaryField
            label="Quote total"
            value={currency.format(diff.proposedTotal)}
            detail={formatDelta(diff.delta)}
          />
          <SummaryField
            label="Changes"
            value={String(changes)}
            detail={formatChanges(diff.added.length, diff.removed.length, diff.changed.length)}
          />
          <SummaryField
            label="Approval"
            value={approvalLabel}
            detail={diff.proposedApproval ? "Required before PDF" : "No hold"}
            tone={diff.proposedApproval ? "warning" : "neutral"}
          />
        </div>

        {recommendation.warnings && recommendation.warnings.length > 0 && (
          <Alert className="recommendation-warning">
            <TriangleAlert aria-hidden="true" />
            <AlertDescription>{recommendation.warnings.slice(0, 2).join(" ")}</AlertDescription>
          </Alert>
        )}

        {stale && (
          <Alert className="recommendation-warning">
            <TriangleAlert aria-hidden="true" />
            <AlertDescription>The quote changed. Update this proposal before applying.</AlertDescription>
          </Alert>
        )}

        <Separator />
        <div className="proposal-list">
          {recommendation.items.map((item) => (
            <div className={item.is_addon ? "proposal-line proposal-addon" : "proposal-line"} key={item.covers_sku ? `${item.sku}-${item.covers_sku}` : item.sku}>
              <div>
                <strong>{item.is_addon ? `Equipment Care · ${item.title.replace(/^Equipment Care(?: Plan)?\s*[·:-]?\s*/i, "")}` : item.title}</strong>
                <span>{item.sku} · {item.quantity} × {currency.format(item.unit_price)}</span>
              </div>
              <div className="proposal-price">
                <strong>{currency.format(lineTotal(item))}</strong>
                {item.approval_required && <Badge className="status-warning" variant="outline">Approval</Badge>}
                {role === "manager" && item.gross_margin_pct != null && <span>{Number(item.gross_margin_pct).toFixed(1)}% margin</span>}
              </div>
            </div>
          ))}
        </div>
        </>}
      </CardContent>
      <CardFooter className="recommendation-footer">
        {!appliedAndCurrent && (stale ? applyButton : diff.removed.length > 0 ? (
          <AlertDialog>
            <AlertDialogTrigger asChild>{applyButton}</AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Replace the current quote?</AlertDialogTitle>
                <AlertDialogDescription>
                  Applying this recommendation removes {diff.removed.length} existing line{diff.removed.length === 1 ? "" : "s"}: {diff.removed.map((line) => line.title).join(", ")}.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Keep current quote</AlertDialogCancel>
                <AlertDialogAction onClick={() => void onApply()}>Replace and apply</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        ) : applyButton)}
        <Button variant="outline" onClick={() => onEvidence(evidence)}>
          <FileSearch aria-hidden="true" /> Details
        </Button>
      </CardFooter>
    </Card>
  );
}

function SummaryField({ label, value, detail, tone = "neutral" }: { label: string; value: string; detail: string; tone?: "neutral" | "warning" }) {
  return (
    <div className={`recommendation-summary-field recommendation-summary-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function formatDelta(delta: number): string {
  if (delta === 0) return "No total change";
  return `${delta > 0 ? "+" : "−"}${currency.format(Math.abs(delta))} from current`;
}

function formatChanges(added: number, removed: number, changed: number): string {
  const parts = [
    added ? `${added} added` : "",
    removed ? `${removed} removed` : "",
    changed ? `${changed} updated` : "",
  ].filter(Boolean);
  return parts.join(" · ") || "No line changes";
}
