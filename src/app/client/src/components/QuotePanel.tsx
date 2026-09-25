import {
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
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
  InputGroupText,
  Skeleton,
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@databricks/appkit-ui/react";
import {
  ChevronLeft,
  ChevronRight,
  Clock3,
  CopyPlus,
  Download,
  Eye,
  FileDown,
  Minus,
  Plus,
  Save,
  Search,
  ShoppingCart,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { Fragment, useEffect, useMemo, useState } from "react";
import { quotePdfUrl } from "../api";
import { currency, groupQuoteLines, lineKey, lineTotal, QUOTE_APPROVAL_THRESHOLD } from "../domain";
import type { Account, DraftLineItem, DraftOrder, SourceFreshness, ViewRole } from "../types";

interface QuotePanelProps {
  account: Account | null;
  draft: DraftOrder | null;
  freshness: SourceFreshness[];
  role: ViewRole;
  approvalThreshold?: number;
  canEditNetPrice?: boolean;
  busy?: boolean;
  loading?: boolean;
  dirty?: boolean;
  onOpenProducts: () => void;
  onQuantity: (line: DraftLineItem, quantity: number) => Promise<void>;
  onSetPrice: (line: DraftLineItem, unitPrice: number) => Promise<void>;
  onRemove: (line: DraftLineItem) => Promise<void>;
  onSave: () => Promise<void>;
  onSend: () => Promise<void>;
  onCreateRevision: () => Promise<void>;
}

const QUOTE_PAGE_SIZE = 50;

export function QuotePanel({
  account,
  draft,
  freshness,
  role,
  approvalThreshold = QUOTE_APPROVAL_THRESHOLD,
  canEditNetPrice = true,
  busy,
  loading,
  dirty,
  onOpenProducts,
  onQuantity,
  onSetPrice,
  onRemove,
  onSave,
  onSend,
  onCreateRevision,
}: QuotePanelProps) {
  const [lineFilter, setLineFilter] = useState("");
  const [approvalsOnly, setApprovalsOnly] = useState(false);
  const [page, setPage] = useState(1);
  const lines = draft?.line_items ?? [];
  const groups = useMemo(() => groupQuoteLines(lines), [lines]);
  const equipmentCount = lines.filter((line) => !line.is_addon).length;
  const protectCount = lines.filter((line) => line.is_addon).length;
  const approvalCount = lines.filter((line) => line.approval_required).length;
  const thresholdApproval = Number(draft?.grand_total ?? 0) > approvalThreshold;
  const approvalRequired = approvalCount > 0 || thresholdApproval;
  const approvalValue = approvalRequired
    ? `${approvalCount + (thresholdApproval ? 1 : 0)} required`
    : "Clear";
  const approvalDetail = thresholdApproval
    ? `Quote total above ${currency.format(approvalThreshold)}`
    : approvalCount
      ? "Resolve before sending"
      : "No pricing hold";
  const sourceNote = freshness[0]?.detail || "Catalog and account pricing";
  const quoteSent = draft?.status === "quote-created";
  const revisionNumber = draft?.revision_number ?? 1;
  const sourceQuoteId = draft?.source_quote_id ? shortId(draft.source_quote_id) : "";
  const locked = quoteSent;
  const listValue = lines.reduce(
    (total, line) => total + Number(line.list_price ?? line.unit_price) * Number(line.quantity ?? 1),
    0,
  );
  const customerSavings = Math.max(0, listValue - Number(draft?.grand_total ?? 0));
  const savingsRate = listValue > 0 ? (customerSavings / listValue) * 100 : 0;
  const showCommercialSummary = customerSavings > 0 || approvalRequired;
  const visibleGroups = useMemo(() => {
    const query = lineFilter.trim().toLocaleLowerCase();
    return groups.filter(({ parent, children }) => {
      if (approvalsOnly && !parent.approval_required) return false;
      if (!query) return true;
      return [parent, ...children].some((line) => (
        `${line.title} ${line.sku} ${line.category}`.toLocaleLowerCase().includes(query)
      ));
    });
  }, [approvalsOnly, groups, lineFilter]);
  const pageCount = Math.max(1, Math.ceil(visibleGroups.length / QUOTE_PAGE_SIZE));
  const activePage = Math.min(page, pageCount);
  const pageStart = (activePage - 1) * QUOTE_PAGE_SIZE;
  const pageGroups = useMemo(
    () => visibleGroups.slice(pageStart, pageStart + QUOTE_PAGE_SIZE),
    [pageStart, visibleGroups],
  );
  const categoryGroups = useMemo(() => groupByCategory(pageGroups), [pageGroups]);

  useEffect(() => {
    setLineFilter("");
    setApprovalsOnly(false);
    setPage(1);
  }, [draft?.draft_order_id]);
  useEffect(() => setPage(1), [approvalsOnly, lineFilter]);
  useEffect(() => setPage((current) => Math.min(current, pageCount)), [pageCount]);

  return (
    <section className="quote-workspace" aria-labelledby="quote-title">
      <header className="quote-summary-bar">
        <div className="quote-heading">
          <div className="quote-heading-copy">
            <p className="eyebrow">
              Quote
            </p>
            <div className="quote-title-row">
              <h2 id="quote-title" tabIndex={-1}>{account?.name || "Quote workspace"}</h2>
              {draft && (
                <Badge variant={quoteSent ? "secondary" : "outline"} className="quote-status-badge">
                  {quoteStatus(draft.status)}
                </Badge>
              )}
            </div>
            {!quoteSent && revisionNumber > 1 && sourceQuoteId && (
              <p className="quote-lineage">Based on quote {sourceQuoteId}</p>
            )}
          </div>
        </div>
        <div className="quote-total-block">
          <span>Quote total</span>
          <strong>{currency.format(draft?.grand_total ?? 0)}</strong>
        </div>
      </header>

      <div className="quote-scroll-region">
        {loading ? (
          <QuoteSkeleton />
        ) : (
          <>
            <div className="quote-overview">
              {showCommercialSummary && (
                <section className="quote-facts" aria-label="Quote summary">
                  {customerSavings > 0 && (
                    <>
                      <Metric
                        label="List value"
                        value={currency.format(listValue)}
                        detail={`${equipmentCount} product${equipmentCount === 1 ? "" : "s"}${protectCount ? ` · ${protectCount} care` : ""}`}
                      />
                      <Metric
                        label="Savings"
                        value={currency.format(customerSavings)}
                        detail={`${savingsRate.toFixed(1)}% from list`}
                        tone="success"
                      />
                    </>
                  )}
                  {approvalRequired && (
                    <Metric
                      label="Approval"
                      value={approvalValue}
                      detail={approvalDetail}
                      tone="warning"
                    />
                  )}
                </section>
              )}
              <p className="source-note">
                <Clock3 aria-hidden="true" />
                <span>Pricing source · {sourceNote}</span>
              </p>
            </div>

            <section className="quote-lines-section" aria-labelledby="quote-lines-title">
              <div className="section-heading">
                <div>
                  <h3 id="quote-lines-title">Products ({groups.length})</h3>
                </div>
                {groups.length > 0 && (
                  <Button variant="outline" onClick={onOpenProducts} disabled={busy || !draft || locked}>
                    <Plus aria-hidden="true" /> Add product
                  </Button>
                )}
              </div>

              {groups.length === 0 ? (
                <Empty className="quote-empty">
                  <EmptyHeader>
                    <EmptyMedia variant="icon"><ShoppingCart aria-hidden="true" /></EmptyMedia>
                    <EmptyTitle>Start this quote</EmptyTitle>
                    <EmptyDescription>Add products manually, or ask Genie to build it from your goal.</EmptyDescription>
                  </EmptyHeader>
                  <EmptyContent>
                    <Button onClick={onOpenProducts} disabled={busy || !draft || locked}>
                      <Plus aria-hidden="true" /> Add product
                    </Button>
                  </EmptyContent>
                </Empty>
              ) : (
                <>
                  <div className="quote-lines-toolbar" role="search">
                    <InputGroup className="quote-line-search">
                      <InputGroupAddon><Search aria-hidden="true" /></InputGroupAddon>
                      <InputGroupInput
                        aria-label="Filter quote lines"
                        placeholder="Filter products or SKUs…"
                        value={lineFilter}
                        onChange={(event) => setLineFilter(event.target.value)}
                      />
                    </InputGroup>
                    {visibleGroups.length !== groups.length && (
                      <span className="quote-result-count" role="status">{visibleGroups.length} of {groups.length}</span>
                    )}
                    {approvalCount > 0 && (
                      <Button
                        variant="outline"
                        size="sm"
                        aria-pressed={approvalsOnly}
                        onClick={() => setApprovalsOnly((current) => !current)}
                      >
                        <TriangleAlert aria-hidden="true" /> Approvals {approvalCount}
                      </Button>
                    )}
                  </div>
                  {visibleGroups.length === 0 ? (
                    <Empty className="quote-filter-empty">
                      <EmptyHeader>
                        <EmptyTitle>No matching quote lines</EmptyTitle>
                        <EmptyDescription>Clear the filter to see the full quote.</EmptyDescription>
                      </EmptyHeader>
                      <EmptyContent>
                        <Button variant="outline" onClick={() => { setLineFilter(""); setApprovalsOnly(false); }}>Clear filter</Button>
                      </EmptyContent>
                    </Empty>
                  ) : (
                    <div className="quote-table-shell">
                  <Table className="quote-lines-table">
                    <TableCaption className="sr-only">Products, care plans, quantities, and pricing for this quote.</TableCaption>
                    <TableHeader className="quote-table-header">
                      <TableRow>
                        <TableHead className="quote-col-product">Product</TableHead>
                        <TableHead className="quote-col-quantity">Qty</TableHead>
                        <TableHead className="quote-col-list table-number">List</TableHead>
                        <TableHead className="quote-col-discount table-number">Discount</TableHead>
                        <TableHead className="quote-col-net table-number">Net unit</TableHead>
                        <TableHead className="quote-col-total table-number">Line total</TableHead>
                        <TableHead className="quote-col-actions"><span className="sr-only">Actions</span></TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {categoryGroups.map((category) => (
                        <Fragment key={category.key}>
                          {categoryGroups.length > 1 && (
                            <TableRow className="quote-category-row">
                              <TableCell colSpan={7}>
                                <span><strong>{category.label}</strong><small>{category.groups.length} item{category.groups.length === 1 ? "" : "s"}</small></span>
                                <span><small>{pageCount > 1 ? "Page subtotal" : "Subtotal"}</small><strong>{currency.format(category.subtotal)}</strong></span>
                              </TableCell>
                            </TableRow>
                          )}
                          {category.groups.map(({ parent, children }) => (
                            <QuoteLineRows
                              key={lineKey(parent)}
                              parent={parent}
                              children={children}
                              role={role}
                              canEditNetPrice={canEditNetPrice}
                              busy={busy || locked}
                              onQuantity={onQuantity}
                              onSetPrice={onSetPrice}
                              onRemove={onRemove}
                            />
                          ))}
                        </Fragment>
                      ))}
                    </TableBody>
                  </Table>
                    </div>
                  )}
                  {visibleGroups.length > QUOTE_PAGE_SIZE && (
                    <nav className="quote-line-pagination" aria-label="Quote line pagination">
                      <span>
                        {pageStart + 1}–{Math.min(pageStart + QUOTE_PAGE_SIZE, visibleGroups.length)} of {visibleGroups.length} products
                      </span>
                      <div>
                        <Button
                          variant="outline"
                          size="sm"
                          aria-label="Previous quote line page"
                          disabled={activePage === 1}
                          onClick={() => setPage((current) => Math.max(1, current - 1))}
                        >
                          <ChevronLeft aria-hidden="true" /> Previous
                        </Button>
                        <strong aria-live="polite">Page {activePage} of {pageCount}</strong>
                        <Button
                          variant="outline"
                          size="sm"
                          aria-label="Next quote line page"
                          disabled={activePage === pageCount}
                          onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
                        >
                          Next <ChevronRight aria-hidden="true" />
                        </Button>
                      </div>
                    </nav>
                  )}
                </>
              )}
            </section>
          </>
        )}
      </div>

      <footer className={`quote-action-bar${approvalRequired && !quoteSent ? " has-action-alert" : ""}`}>
        {approvalRequired && !quoteSent && (
          <p className="quote-action-alert" role="status">
            <TriangleAlert aria-hidden="true" /> Approval required before generating a PDF.
          </p>
        )}
        <div className={`quote-action-buttons${quoteSent ? " generated-quote-actions" : ""}`}>
          {quoteSent ? (
            <>
              <Button variant="outline" size="sm" asChild>
                <a
                  href={quotePdfUrl(draft.draft_order_id, role)}
                  target="_blank"
                  rel="noreferrer"
                >
                  <Eye aria-hidden="true" /> View PDF
                </a>
              </Button>
              <Button variant="outline" size="sm" asChild>
                <a href={quotePdfUrl(draft.draft_order_id, role, true)} download>
                  <Download aria-hidden="true" /> Download PDF
                </a>
              </Button>
              <Button size="sm" onClick={() => void onCreateRevision()} disabled={busy || !draft}>
                <CopyPlus aria-hidden="true" /> Create new version
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={() => void onSave()} disabled={busy || !draft || lines.length === 0 || (!dirty && draft.status === "saved")}>
                <Save aria-hidden="true" /> Save changes
              </Button>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    tabIndex={approvalRequired ? 0 : undefined}
                    aria-label={approvalRequired ? "Generate quote PDF unavailable: clear quote approvals first." : undefined}
                  >
                    <Button onClick={() => void onSend()} disabled={busy || !draft || lines.length === 0 || approvalRequired}>
                      <FileDown aria-hidden="true" /> Generate PDF
                    </Button>
                  </span>
                </TooltipTrigger>
                {approvalRequired && <TooltipContent>Clear quote approvals before generating the PDF.</TooltipContent>}
              </Tooltip>
            </>
          )}
        </div>
      </footer>
    </section>
  );
}

interface QuoteLineGroupProps {
  parent: DraftLineItem;
  children: DraftLineItem[];
  role: ViewRole;
  canEditNetPrice: boolean;
  busy?: boolean;
  onQuantity: (line: DraftLineItem, quantity: number) => Promise<void>;
  onSetPrice: (line: DraftLineItem, unitPrice: number) => Promise<void>;
  onRemove: (line: DraftLineItem) => Promise<void>;
}

function QuoteLineRows({ parent, children, role, canEditNetPrice, busy, onQuantity, onSetPrice, onRemove }: QuoteLineGroupProps) {
  const [price, setPrice] = useState(String(parent.unit_price));
  const [priceError, setPriceError] = useState(false);
  const listPrice = Number(parent.list_price ?? parent.unit_price);
  const discount = listPrice > 0 ? Math.max(0, (1 - Number(parent.unit_price) / listPrice) * 100) : 0;

  useEffect(() => setPrice(String(parent.unit_price)), [parent.unit_price]);

  const commitPrice = async () => {
    const value = Number(price);
    if (Number.isFinite(value) && value >= 0 && value !== parent.unit_price) {
      setPriceError(false);
      try {
        await onSetPrice(parent, value);
      } catch {
        setPrice(String(parent.unit_price));
        setPriceError(true);
      }
    } else {
      setPrice(String(parent.unit_price));
    }
  };

  return (
    <>
      <TableRow className="quote-product-row">
        <TableCell className="quote-product-cell">
          <div className="line-title-row">
            <h4>{parent.title}</h4>
            {parent.approval_required && <Badge className="status-warning" variant="outline">Approval required</Badge>}
          </div>
          <p>{parent.sku} · {humanize(parent.category)}</p>
          <span className="mobile-line-total">{currency.format(lineTotal(parent))} total</span>
        </TableCell>
        <TableCell className="quote-col-quantity">
          <div className="quantity-stepper" aria-label={`Quantity for ${parent.title}`}>
            <Button className="quote-line-control" size="icon-sm" variant="ghost" disabled={busy || parent.quantity <= 1} onClick={() => void onQuantity(parent, parent.quantity - 1)} aria-label={`Decrease ${parent.title} quantity`}>
              <Minus aria-hidden="true" />
            </Button>
            <strong aria-live="polite">{parent.quantity}</strong>
            <Button className="quote-line-control" size="icon-sm" variant="ghost" disabled={busy} onClick={() => void onQuantity(parent, parent.quantity + 1)} aria-label={`Increase ${parent.title} quantity`}>
              <Plus aria-hidden="true" />
            </Button>
          </div>
        </TableCell>
        <TableCell className="quote-col-list table-number">{currency.format(listPrice)}</TableCell>
        <TableCell className="quote-col-discount table-number">{discount > 0.05 ? `${discount.toFixed(1)}%` : "—"}</TableCell>
        <TableCell className="quote-col-net">
          <InputGroup className="table-price-input">
            <InputGroupAddon><InputGroupText>$</InputGroupText></InputGroupAddon>
            <InputGroupInput
              aria-label={`Net unit price for ${parent.title}`}
              inputMode="decimal"
              value={price}
              disabled={busy || !canEditNetPrice}
              title={!canEditNetPrice ? "Net price editing is limited to managers." : undefined}
              aria-invalid={priceError || undefined}
              onChange={(event) => { setPrice(event.target.value); setPriceError(false); }}
              onBlur={() => void commitPrice()}
              onKeyDown={(event) => {
                if (event.key === "Enter") event.currentTarget.blur();
                if (event.key === "Escape") {
                  setPrice(String(parent.unit_price));
                  event.currentTarget.blur();
                }
              }}
            />
          </InputGroup>
        </TableCell>
        <TableCell className="quote-col-total table-number line-total">{currency.format(lineTotal(parent))}</TableCell>
        <TableCell className="quote-actions-cell">
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="ghost" size="icon-sm" className="remove-line quote-line-control" disabled={busy} aria-label={`Remove ${parent.title}`}>
                <Trash2 aria-hidden="true" />
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Remove {parent.title}?</AlertDialogTitle>
                <AlertDialogDescription>
                  This removes the product{children.length ? ` and ${children.length} attached care plan${children.length === 1 ? "" : "s"}` : ""} from the live draft.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Keep product</AlertDialogCancel>
                <AlertDialogAction onClick={() => void onRemove(parent)}>Remove from quote</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </TableCell>
      </TableRow>

      {(parent.approval_reason || (role === "manager" && parent.gross_margin_pct != null)) && (
        <TableRow className="line-insights-row">
          <TableCell colSpan={7}>
            <div className="line-insights">
            {parent.approval_reason && <span className="status-warning"><TriangleAlert aria-hidden="true" /> {parent.approval_reason}</span>}
            {role === "manager" && parent.gross_margin_pct != null && <span>{Number(parent.gross_margin_pct).toFixed(1)}% gross margin</span>}
            </div>
          </TableCell>
        </TableRow>
      )}

      {children.map((child) => {
        const childListPrice = Number(child.list_price ?? child.unit_price);
        const childDiscount = childListPrice > 0 ? Math.max(0, (1 - Number(child.unit_price) / childListPrice) * 100) : 0;
        return (
          <TableRow className="care-plan-row" key={lineKey(child)}>
            <TableCell className="care-plan-product">
              <div className="care-plan-product-content">
                <div className="care-plan-copy">
                  <span className="care-plan-title"><strong>{child.title}</strong></span>
                  <span className="care-plan-meta">{child.sku} · Covers {parent.sku}</span>
                  <span className="mobile-line-total">{currency.format(lineTotal(child))} total</span>
                </div>
              </div>
            </TableCell>
            <TableCell className="quote-col-quantity table-number">{child.quantity}</TableCell>
            <TableCell className="quote-col-list table-number">{currency.format(childListPrice)}</TableCell>
            <TableCell className="quote-col-discount table-number">{childDiscount > 0.05 ? `${childDiscount.toFixed(1)}%` : "—"}</TableCell>
            <TableCell className="quote-col-net table-number">{currency.format(Number(child.unit_price))}</TableCell>
            <TableCell className="quote-col-total table-number line-total">{currency.format(lineTotal(child))}</TableCell>
            <TableCell className="quote-actions-cell">
              <Button className="quote-line-control" variant="ghost" size="icon-sm" disabled={busy} onClick={() => void onRemove(child)} aria-label={`Remove ${child.title}`}>
                <Trash2 aria-hidden="true" />
              </Button>
            </TableCell>
          </TableRow>
        );
      })}
    </>
  );
}

function Metric({ label, value, detail, tone = "neutral" }: { label: string; value: string; detail?: string; tone?: "neutral" | "success" | "warning" }) {
  return (
    <div className={`quote-fact metric-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </div>
  );
}

function QuoteSkeleton() {
  return (
    <div className="quote-skeleton" aria-label="Loading quote">
      <div className="quote-facts">
        {[0, 1, 2, 3].map((item) => <Skeleton className="metric-skeleton" key={item} />)}
      </div>
      <Skeleton className="line-skeleton" />
      <Skeleton className="line-skeleton" />
    </div>
  );
}

function humanize(value: string): string {
  return value.replaceAll("-", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function quoteStatus(value: string): string {
  if (value === "quote-created") return "Generated";
  if (value === "saved") return "Saved";
  return "Draft";
}

function shortId(value: string): string {
  return (value.split("-").at(-1) || value).slice(0, 8);
}

function groupByCategory(groups: ReturnType<typeof groupQuoteLines>) {
  const categories = new Map<string, { key: string; label: string; groups: ReturnType<typeof groupQuoteLines>; subtotal: number }>();
  for (const group of groups) {
    const key = (group.parent.category || "other").trim().toLowerCase();
    const existing = categories.get(key) ?? { key, label: humanize(key), groups: [], subtotal: 0 };
    existing.groups.push(group);
    existing.subtotal += lineTotal(group.parent) + group.children.reduce((total, child) => total + lineTotal(child), 0);
    categories.set(key, existing);
  }
  return [...categories.values()];
}
