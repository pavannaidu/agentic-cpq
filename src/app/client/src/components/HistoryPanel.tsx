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
  AlertTitle,
  Badge,
  Button,
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemFooter,
  ItemGroup,
  ItemTitle,
  ScrollArea,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  Skeleton,
} from "@databricks/appkit-ui/react";
import { ArrowRight, Download, Eye, FileClock, LockKeyhole, RotateCcw, Trash2, TriangleAlert, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, quotePdfUrl } from "../api";
import { currency, historyDiff, sanitizeDraftForRole } from "../domain";
import type { Account, DraftOrder, HistoryItem, QuoteDiff, ViewRole } from "../types";

interface HistoryPanelProps {
  open: boolean;
  compact: boolean;
  account: Account | null;
  currentDraft: DraftOrder | null;
  role: ViewRole;
  onOpenChange: (open: boolean) => void;
  onLoadDraft: (draft: DraftOrder) => Promise<void>;
}

export function HistoryPanel({ open, compact, account, currentDraft, role, onOpenChange, onLoadDraft }: HistoryPanelProps) {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [selected, setSelected] = useState<DraftOrder | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedLoadingId, setSelectedLoadingId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [workingId, setWorkingId] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    if (!account) return;
    setLoading(true);
    setError("");
    try {
      const result = await api.history(account.account_id, role);
      setItems(result.items);
    } catch (cause) {
      setError(publicError(cause, "History could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, [account, role]);

  useEffect(() => {
    if (!open) {
      setSelected(null);
      return;
    }
    void loadHistory();
  }, [loadHistory, open]);

  const inspect = async (item: HistoryItem) => {
    if (selected?.draft_order_id === item.draft_order_id) {
      setSelected(null);
      return;
    }
    setSelected(null);
    setSelectedLoadingId(item.draft_order_id);
    setError("");
    try {
      const draft = await api.getDraft(item.draft_order_id, role);
      setSelected(sanitizeDraftForRole(draft, role));
    } catch (cause) {
      setError(publicError(cause, "That saved quote could not be opened."));
    } finally {
      setSelectedLoadingId(null);
    }
  };

  const loadSelected = async () => {
    if (!selected) return;
    setWorkingId(selected.draft_order_id);
    try {
      await onLoadDraft(selected);
      onOpenChange(false);
    } finally {
      setWorkingId(null);
    }
  };

  const remove = async (item: HistoryItem) => {
    setWorkingId(item.draft_order_id);
    setError("");
    try {
      await api.deleteDraft(item.draft_order_id);
      if (selected?.draft_order_id === item.draft_order_id) setSelected(null);
      await loadHistory();
    } catch (cause) {
      setError(publicError(cause, "The saved quote could not be deleted."));
    } finally {
      setWorkingId(null);
    }
  };

  const diff = selected && currentDraft ? historyDiff(currentDraft.line_items, selected.line_items) : null;
  const content = (
    <HistoryContent
      items={items}
      selected={selected}
      diff={diff}
      loading={loading}
      selectedLoadingId={selectedLoadingId}
      workingId={workingId}
      currentDraftId={currentDraft?.draft_order_id}
      role={role}
      error={error}
      onInspect={inspect}
      onLoadSelected={loadSelected}
      onRemove={remove}
    />
  );

  if (compact) {
    return (
      <Drawer open={open} onOpenChange={onOpenChange} direction="bottom">
        <DrawerContent className="history-drawer">
          <DrawerHeader style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) max-content", textAlign: "left" }}>
            <div>
              <DrawerTitle>History</DrawerTitle>
              <DrawerDescription>{account?.name || "Current account"}</DrawerDescription>
            </div>
            <DrawerClose asChild>
              <Button type="button" variant="ghost" size="icon-sm" aria-label="Close history">
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
      <SheetContent side="right" className="history-sheet">
        <SheetHeader>
          <SheetTitle>History</SheetTitle>
          <SheetDescription>{account?.name || "Current account"}</SheetDescription>
        </SheetHeader>
        {content}
      </SheetContent>
    </Sheet>
  );
}

interface HistoryContentProps {
  items: HistoryItem[];
  selected: DraftOrder | null;
  diff: QuoteDiff | null;
  loading: boolean;
  selectedLoadingId: string | null;
  workingId: string | null;
  currentDraftId?: string;
  role: ViewRole;
  error: string;
  onInspect: (item: HistoryItem) => Promise<void>;
  onLoadSelected: () => Promise<void>;
  onRemove: (item: HistoryItem) => Promise<void>;
}

function HistoryContent({ items, selected, diff, loading, selectedLoadingId, workingId, currentDraftId, role, error, onInspect, onLoadSelected, onRemove }: HistoryContentProps) {
  return (
    <ScrollArea className="history-scroll">
      <div className="history-content">
        {error && (
          <Alert variant="destructive">
            <TriangleAlert aria-hidden="true" />
            <AlertTitle>History unavailable</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {loading ? (
          <div className="history-skeleton">
            {[0, 1, 2].map((item) => <Skeleton key={item} />)}
          </div>
        ) : items.length === 0 ? (
          <Empty className="panel-empty">
            <EmptyHeader>
              <EmptyMedia variant="icon"><FileClock aria-hidden="true" /></EmptyMedia>
              <EmptyTitle>No saved quotes yet</EmptyTitle>
              <EmptyDescription>Save a draft and it will appear here.</EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <ItemGroup className="history-list">
            {items.map((item) => {
              const selectedHere = selected?.draft_order_id === item.draft_order_id;
              const loadingHere = selectedLoadingId === item.draft_order_id;
              const expanded = selectedHere || loadingHere;
              const revision = item.revision_number ?? 1;
              const itemType = item.quote_id ? "Quote" : "Draft";
              const previewId = `history-preview-${item.draft_order_id}`;
              return (
              <Item key={item.draft_order_id} variant={expanded ? "muted" : "outline"}>
                <ItemContent>
                  <ItemTitle>
                    <button
                      type="button"
                      onClick={() => void onInspect(item)}
                      disabled={workingId != null || (selectedLoadingId != null && !loadingHere)}
                      aria-expanded={expanded}
                      aria-controls={previewId}
                    >
                      {itemType} · Rev {revision}
                    </button>
                  </ItemTitle>
                  <ItemDescription>
                    {formatDate(item.updated_at)} · {currency.format(item.grand_total)}
                  </ItemDescription>
                </ItemContent>
                <ItemActions>
                  {item.draft_order_id === currentDraftId && <Badge variant="secondary">Current</Badge>}
                  {item.status === "quote-created" ? (
                    <span className="history-lock" title="Quotes cannot be deleted" aria-label="Quote cannot be deleted">
                      <LockKeyhole aria-hidden="true" />
                    </span>
                  ) : (
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button variant="ghost" size="icon-sm" disabled={workingId != null || item.draft_order_id === currentDraftId} aria-label={item.draft_order_id === currentDraftId ? "Current draft cannot be deleted" : `Delete revision ${revision}`}>
                          <Trash2 aria-hidden="true" />
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Delete this saved draft?</AlertDialogTitle>
                          <AlertDialogDescription>This permanently deletes the saved draft.</AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Keep it</AlertDialogCancel>
                          <AlertDialogAction onClick={() => void onRemove(item)}>Delete saved draft</AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  )}
                </ItemActions>
                {expanded && (
                  <ItemFooter
                    id={previewId}
                    className="history-inline-preview"
                    aria-busy={loadingHere || undefined}
                  >
                    {loadingHere ? (
                      <Skeleton className="history-preview-skeleton" />
                    ) : selectedHere && diff ? (
                      <HistoryPreview selected={selected} diff={diff} role={role} working={workingId != null} onLoad={onLoadSelected} />
                    ) : null}
                  </ItemFooter>
                )}
              </Item>
              );
            })}
          </ItemGroup>
        )}
      </div>
    </ScrollArea>
  );
}

function HistoryPreview({ selected, diff, role, working, onLoad }: { selected: DraftOrder; diff: QuoteDiff; role: ViewRole; working: boolean; onLoad: () => Promise<void> }) {
  const generated = selected.status === "quote-created";
  return (
    <section className="history-preview" aria-label="Selected quote comparison">
      <div className="history-total-change">
        <div><span>Current</span><strong>{currency.format(diff.currentTotal)}</strong></div>
        <ArrowRight aria-hidden="true" />
        <div><span>Selected</span><strong>{currency.format(diff.proposedTotal)}</strong></div>
      </div>
      <div className="history-diff-grid">
        <span><strong>+{diff.added.length}</strong> added</span>
        <span><strong>−{diff.removed.length}</strong> removed</span>
        <span><strong>~{diff.changed.length}</strong> changed</span>
      </div>
      <div className="history-preview-actions">
        {generated && (
          <>
            <Button variant="outline" size="sm" asChild>
              <a href={quotePdfUrl(selected.draft_order_id, role)} target="_blank" rel="noreferrer">
                <Eye aria-hidden="true" /> View PDF
              </a>
            </Button>
            <Button variant="outline" size="sm" asChild>
              <a href={quotePdfUrl(selected.draft_order_id, role, true)} download>
                <Download aria-hidden="true" /> Download PDF
              </a>
            </Button>
          </>
        )}
        <Button size="sm" onClick={() => void onLoad()} disabled={working}>
          {generated ? <LockKeyhole aria-hidden="true" /> : <RotateCcw aria-hidden="true" />}
          {generated ? "Open quote" : "Load draft"}
        </Button>
      </div>
    </section>
  );
}

function formatDate(value?: string): string {
  if (!value) return "Recently updated";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Recently updated";
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(date);
}

function publicError(cause: unknown, fallback: string): string {
  return cause instanceof Error && cause.message ? cause.message : fallback;
}
