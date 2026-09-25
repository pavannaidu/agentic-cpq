import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Button,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
  ScrollArea,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@databricks/appkit-ui/react";
import { ChevronDown, ExternalLink, X } from "lucide-react";
import type { ReactNode } from "react";
import { safeExternalUrl } from "../domain";
import type { Evidence } from "../types";

interface EvidencePanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  evidence: Evidence | null;
  compact: boolean;
}

export function EvidencePanel({ open, onOpenChange, evidence, compact }: EvidencePanelProps) {
  const content = <EvidenceContent evidence={evidence} />;
  const description = evidenceDescription(evidence?.executionIdentity);
  if (compact) {
    return (
      <Drawer open={open} onOpenChange={onOpenChange} direction="bottom">
        <DrawerContent className="evidence-drawer">
          <DrawerHeader style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) max-content", textAlign: "left" }}>
            <div>
              <DrawerTitle>Details</DrawerTitle>
              <DrawerDescription>{description}</DrawerDescription>
            </div>
            <DrawerClose asChild>
              <Button type="button" variant="ghost" size="icon-sm" aria-label="Close details">
                <X aria-hidden="true" />
              </Button>
            </DrawerClose>
          </DrawerHeader>
          {content}
        </DrawerContent>
      </Drawer>
    );
  }
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="evidence-sheet">
        <SheetHeader>
          <SheetTitle>Details</SheetTitle>
          <SheetDescription>{description}</SheetDescription>
        </SheetHeader>
        {content}
      </SheetContent>
    </Sheet>
  );
}

function EvidenceContent({ evidence }: { evidence: Evidence | null }) {
  if (!evidence) {
    return (
      <Empty className="panel-empty">
        <EmptyHeader>
          <EmptyTitle>No details selected</EmptyTitle>
          <EmptyDescription>Select Details on a response.</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }
  const hasQuery = Boolean(evidence.sql || (evidence.columns.length && evidence.rows.length));
  const hasDetails = evidence.citations.length > 0
    || evidence.checks.length > 0
    || evidence.freshness.length > 0
    || hasQuery;
  return (
    <ScrollArea className="evidence-scroll">
      <div className="evidence-content">
        {evidence.partial && (
          <Alert className="partial-alert">
            <AlertTitle>Limited details</AlertTitle>
            <AlertDescription>Some supporting details were unavailable.</AlertDescription>
          </Alert>
        )}

        {evidence.citations.length > 0 && (
          <EvidenceSection title="Sources">
            <div className="source-list">
              {evidence.citations.map((citation, index) => {
                const href = safeExternalUrl(citation.url);
                const detail = cleanCitationDetail(citation.detail);
                const label = sourceLabel(citation.source);
                return (
                  <article className="source-item" key={`${citation.source}-${citation.title}-${index}`}>
                    <div>
                      <strong>{citation.title || label}</strong>
                    </div>
                    <p>{[label, detail].filter(Boolean).join(" · ")}</p>
                    {href && (
                      <a className="source-link" href={href} target="_blank" rel="noreferrer">
                        Open <ExternalLink aria-hidden="true" />
                      </a>
                    )}
                  </article>
                );
              })}
            </div>
          </EvidenceSection>
        )}

        {evidence.checks.length > 0 && (
          <EvidenceSection title="Checks">
            <ul className="check-list">
              {evidence.checks.map((check, index) => (
                <li key={`${check.label}-${index}`}>
                  <span><strong>{check.label}</strong>{check.detail && <small>{check.detail}</small>}</span>
                  <Badge variant={/fail|error|blocked/i.test(check.status) ? "destructive" : "outline"}>{check.status}</Badge>
                </li>
              ))}
            </ul>
          </EvidenceSection>
        )}

        {evidence.freshness.length > 0 && (
          <EvidenceSection title="Data status">
            <ul className="freshness-list">
              {evidence.freshness.map((item, index) => (
                <li key={`${item.source}-${item.status}-${index}`}>
                  <strong>{dataSourceLabel(item.source)}</strong>
                  <span>{dataStatusLabel(item.status)}</span>
                  {item.detail?.trim() && <small>{item.detail.trim()}</small>}
                </li>
              ))}
            </ul>
          </EvidenceSection>
        )}

        {hasQuery && (
          <Collapsible>
            <CollapsibleTrigger className="collapsible-trigger">
              View query details <ChevronDown aria-hidden="true" />
            </CollapsibleTrigger>
            <CollapsibleContent>
              {evidence.sql && <pre className="sql-block"><code>{evidence.sql}</code></pre>}
              {evidence.columns.length > 0 && evidence.rows.length > 0 && (
                <div className="table-scroll query-results" tabIndex={0} aria-label="Returned data">
                  <Table>
                    <TableHeader>
                      <TableRow>{evidence.columns.map((column) => <TableHead key={column}>{column}</TableHead>)}</TableRow>
                    </TableHeader>
                    <TableBody>
                      {evidence.rows.slice(0, 20).map((row, rowIndex) => (
                        <TableRow key={rowIndex}>
                          {evidence.columns.map((column, columnIndex) => (
                            <TableCell key={`${column}-${columnIndex}`}>{formatCell(row[columnIndex])}</TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
              {evidence.truncated && <p className="muted-copy">Results are truncated.</p>}
            </CollapsibleContent>
          </Collapsible>
        )}

        {!hasDetails && !evidence.partial && <p className="muted-copy evidence-empty-copy">No supporting details were returned.</p>}
      </div>
    </ScrollArea>
  );
}

function EvidenceSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="evidence-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function formatCell(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function sourceLabel(source?: string): string {
  const normalized = (source ?? "").trim().toLowerCase().replaceAll("-", "_");
  if (!normalized) return "Reference";
  if (["genie_volume", "volume", "document", "documents"].includes(normalized)) return "Guidance";
  if (["web", "web_search", "system.ai.web_search"].includes(normalized)) return "External reference";
  if (["sql", "lakebase", "unity_catalog", "catalog", "genie", "genie_agent_mode", "genie_intelligence", "genie_conversation_api"].includes(normalized)) return "Workspace data";
  return "Reference";
}

function evidenceDescription(executionIdentity?: string): string {
  const identity = (executionIdentity ?? "").trim().toLowerCase();
  if (identity === "on_behalf_of") return "Uses your workspace access.";
  if (identity === "service_principal" || identity.startsWith("databricks-app:")) {
    return "Uses approved app access.";
  }
  return "Supporting details for a selected response.";
}

function dataSourceLabel(source?: string): string {
  const value = (source ?? "").trim();
  const category = sourceLabel(value);
  if (category !== "Reference") return category;
  if (!value) return "Data";
  if (/^[A-Z0-9]{2,6}$/.test(value)) return value;
  return humanizeLabel(value);
}

function dataStatusLabel(status?: string): string {
  const value = (status ?? "").trim();
  const normalized = value.toLowerCase().replace(/[\s_-]+/g, "_");
  if (["current", "fresh", "live", "ready", "loaded", "available"].includes(normalized)) return "Current";
  if (["stale", "delayed", "warning", "needs_attention"].includes(normalized)) return "Needs attention";
  if (["unavailable", "error", "failed", "offline"].includes(normalized)) return "Unavailable";
  return value ? humanizeLabel(value) : "Available";
}

function humanizeLabel(value: string): string {
  const words = value.replace(/[._-]+/g, " ").replace(/\s+/g, " ").trim().toLowerCase();
  return words.replace(/\b\w/g, (character) => character.toUpperCase());
}

function cleanCitationDetail(detail?: string): string {
  const value = (detail ?? "").trim();
  if (!value || /^\[?\d+\]?$/.test(value) || /^\[\d+$/.test(value)) return "";
  return value;
}
