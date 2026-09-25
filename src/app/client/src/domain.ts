import type { DraftLineItem, Evidence, GenieCitation, GenieResponse, QuoteDiff, Recommendation, SourceEvidence, ViewRole } from "./types";

export const QUOTE_APPROVAL_THRESHOLD = 80_000;

const wholeDollarCurrency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const centCurrency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export const currency = {
  format(value: number): string {
    const amount = Number(value);
    return Number.isInteger(amount) ? wholeDollarCurrency.format(amount) : centCurrency.format(amount);
  },
};

export function safeExternalUrl(value?: string): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

export function lineKey(line: DraftLineItem): string {
  return line.covers_sku ? `${line.sku}::${line.covers_sku}` : line.sku;
}

export function lineTotal(line: DraftLineItem): number {
  return Number(line.total_price ?? line.unit_price * line.quantity);
}

export function groupQuoteLines(lines: DraftLineItem[]): Array<{ parent: DraftLineItem; children: DraftLineItem[] }> {
  const children = new Map<string, DraftLineItem[]>();
  for (const line of lines) {
    if (line.is_addon && line.covers_sku) {
      children.set(line.covers_sku, [...(children.get(line.covers_sku) ?? []), line]);
    }
  }
  const groups = lines
    .filter((line) => !line.is_addon)
    .map((parent) => ({ parent, children: children.get(parent.sku) ?? [] }));
  const orphaned = lines.filter(
    (line) => line.is_addon && (!line.covers_sku || !lines.some((candidate) => !candidate.is_addon && candidate.sku === line.covers_sku)),
  );
  return [...groups, ...orphaned.map((parent) => ({ parent, children: [] }))];
}

export function sanitizeDraftForRole<T extends { line_items: DraftLineItem[] }>(order: T, role: ViewRole): T {
  if (role === "manager") return order;
  return {
    ...order,
    line_items: order.line_items.map(({ supplier_cost: _supplierCost, gross_margin_pct: _margin, overpay_amount: _overpay, legacy_supplier_cost: _legacy, correct_supplier_cost: _correct, ...line }) => line),
  } as T;
}

export function sanitizeRecommendationForRole(recommendation: Recommendation, role: ViewRole): Recommendation {
  if (role === "manager") return recommendation;
  return {
    ...recommendation,
    items: recommendation.items.map(({ supplier_cost: _supplierCost, gross_margin_pct: _margin, overpay_amount: _overpay, legacy_supplier_cost: _legacy, correct_supplier_cost: _correct, ...line }) => line),
    manager_insights: undefined,
    overpay_prevented_total: undefined,
  };
}

export function computeQuoteDiff(current: DraftLineItem[], proposed: DraftLineItem[], mode: "add" | "replace" = "add"): QuoteDiff {
  const currentByKey = new Map(current.map((line) => [lineKey(line), line]));
  const proposedByKey = new Map(proposed.map((line) => [lineKey(line), line]));
  const added = proposed.filter((line) => !currentByKey.has(lineKey(line)));
  const removed = mode === "replace" ? current.filter((line) => !proposedByKey.has(lineKey(line))) : [];
  const changed = proposed.flatMap((after) => {
    const before = currentByKey.get(lineKey(after));
    if (!before) return [];
    return before.quantity !== after.quantity || before.unit_price !== after.unit_price
      ? [{ before, after }]
      : [];
  });
  const resultLines = mode === "replace"
    ? proposed.map((line) => ({ ...line }))
    : [
        ...current.map((line) => {
          const proposedLine = proposedByKey.get(lineKey(line));
          return proposedLine ? { ...line, ...proposedLine } : { ...line };
        }),
        ...added.map((line) => ({ ...line })),
      ];
  const currentTotal = current.reduce((sum, line) => sum + lineTotal(line), 0);
  const proposedTotal = resultLines.reduce((sum, line) => sum + lineTotal(line), 0);
  return {
    added,
    removed,
    changed,
    currentTotal,
    proposedTotal,
    delta: proposedTotal - currentTotal,
    currentApproval: current.some((line) => Boolean(line.approval_required)),
    proposedApproval: resultLines.some((line) => Boolean(line.approval_required)),
    protectionTotal: resultLines.filter((line) => line.is_addon).reduce((sum, line) => sum + lineTotal(line), 0),
    resultLines,
  };
}

export function evidenceFromRecommendation(recommendation: Recommendation, executionIdentity?: string): Evidence {
  const envelope = recommendation.evidence?.find((item) => item.status !== "unavailable") ?? recommendation.evidence?.[0];
  if (envelope) {
    const fromEnvelope = evidenceFromGenie(envelope, executionIdentity);
    const recommendationChecks = [
      ...(recommendation.pricing_controls ?? []),
      ...(recommendation.quote_readiness ?? []),
      ...(recommendation.requirements_coverage ?? []),
      ...(recommendation.source_lineage ?? []),
    ];
    return {
      ...fromEnvelope,
      checks: [...fromEnvelope.checks, ...recommendationChecks],
      freshness: fromEnvelope.freshness.length ? fromEnvelope.freshness : recommendation.source_freshness ?? [],
      tools: [...new Set([...fromEnvelope.tools, ...metadataTools(recommendation)])],
    };
  }
  const itemCitations = recommendation.items.flatMap((item) => [...(item.citations ?? []), ...(item.insights ?? [])]);
  const citations = dedupeEvidence([...(recommendation.citations ?? []), ...itemCitations]);
  const checks = [
    ...(recommendation.pricing_controls ?? []),
    ...(recommendation.quote_readiness ?? []),
    ...(recommendation.requirements_coverage ?? []),
    ...(recommendation.source_lineage ?? []),
  ];
  return {
    citations,
    sql: recommendation.sql ?? "",
    columns: recommendation.columns ?? [],
    rows: recommendation.rows ?? [],
    checks,
    freshness: recommendation.source_freshness ?? [],
    tools: metadataTools(recommendation),
    truncated: Boolean(recommendation.truncated),
    executionIdentity,
    partial: citations.length === 0 && !(recommendation.sql ?? "") && checks.length === 0,
  };
}

export function evidenceFromGenie(response: GenieResponse, executionIdentity?: string): Evidence {
  const nested = response.evidence?.find((item) => item.status !== "unavailable") ?? response.evidence?.[0];
  if (nested) {
    return evidenceFromGenie(
      {
        ...nested,
        execution_identity: nested.execution_identity ?? response.metadata?.execution_identity ?? response.execution_identity,
      },
      executionIdentity,
    );
  }
  const attachment = response.sql_attachments?.[0];
  const citations = (response.citations ?? []).map(normalizeCitation);
  const freshness = response.source_freshness?.length
    ? response.source_freshness
    : response.freshness
      ? [{
          source: response.source ?? "Genie",
          status: response.freshness.status ?? "live",
          detail: response.freshness.detail ?? (response.freshness.retrieved_at ? `Retrieved ${response.freshness.retrieved_at}` : "Returned for this request."),
        }]
      : [];
  return {
    citations,
    sql: attachment?.sql ?? response.sql ?? "",
    columns: attachment?.columns ?? response.columns ?? [],
    rows: attachment?.rows ?? response.rows ?? [],
    checks: response.checks ?? [],
    freshness,
    tools: response.source ? [response.source] : ["genie"],
    truncated: Boolean(attachment?.truncated ?? response.truncated),
    executionIdentity: response.execution_identity ?? response.metadata?.execution_identity ?? executionIdentity,
    partial: citations.length === 0 && !(attachment?.sql ?? response.sql ?? "") && (response.checks ?? []).length === 0,
  };
}

function metadataTools(recommendation: Recommendation): string[] {
  return Array.isArray(recommendation.metadata?.tools_used)
    ? recommendation.metadata.tools_used.filter((value): value is string => typeof value === "string")
    : [];
}

function normalizeCitation(citation: SourceEvidence | GenieCitation): SourceEvidence {
  if ("detail" in citation) return citation;
  return {
    source: citation.source ?? "Genie",
    title: citation.title ?? "Governed source",
    detail: citation.snippet ?? citation.uri ?? "Source returned by Genie.",
    url: citation.uri || undefined,
  };
}

function dedupeEvidence(items: SourceEvidence[]): SourceEvidence[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = `${item.source}|${item.title}|${item.detail}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function quoteSnapshot(lines: DraftLineItem[]): string {
  return JSON.stringify(
    lines
      .map((line) => ({ key: lineKey(line), quantity: line.quantity, unit_price: Number(line.unit_price) }))
      .sort((a, b) => a.key.localeCompare(b.key)),
  );
}

export function blendedMargin(lines: DraftLineItem[]): number | null {
  let revenue = 0;
  let weighted = 0;
  for (const line of lines) {
    const total = lineTotal(line);
    if (line.gross_margin_pct == null || total <= 0) continue;
    revenue += total;
    weighted += Number(line.gross_margin_pct) * total;
  }
  return revenue > 0 ? weighted / revenue : null;
}

export function historyDiff(current: DraftLineItem[], historical: DraftLineItem[]): QuoteDiff {
  return computeQuoteDiff(current, historical, "replace");
}
