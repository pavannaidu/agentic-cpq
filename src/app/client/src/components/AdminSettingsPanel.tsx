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
  Button,
  Input,
  Label,
  ScrollArea,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  Skeleton,
  Spinner,
  Switch,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
} from "@databricks/appkit-ui/react";
import { CheckCircle2, ExternalLink, RotateCcw, Save, TriangleAlert } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { api } from "../api";
import type { AdminSettings, QuoteBehaviorSettings, QuotePdfSettings } from "../types";

interface AdminSettingsPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved?: (settings: AdminSettings) => void;
}

type SaveState = "idle" | "saving" | "saved";
type SettingsTab = "pdf" | "rules";

export function AdminSettingsPanel({ open, onOpenChange, onSaved }: AdminSettingsPanelProps) {
  const [savedSettings, setSavedSettings] = useState<AdminSettings | null>(null);
  const [draft, setDraft] = useState<AdminSettings | null>(null);
  const [loading, setLoading] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [previewing, setPreviewing] = useState(false);
  const [confirmDiscardOpen, setConfirmDiscardOpen] = useState(false);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<SettingsTab>("pdf");
  const [loadAttempt, setLoadAttempt] = useState(0);
  const lastDiscountLimit = useRef(20);

  useEffect(() => {
    if (!open) return;
    let active = true;
    setLoading(true);
    setSavedSettings(null);
    setDraft(null);
    setError("");
    setSaveState("idle");
    setPreviewing(false);
    setConfirmDiscardOpen(false);
    setActiveTab("pdf");
    void api.getAdminSettings()
      .then((settings) => {
        if (!active) return;
        if (settings.behavior.max_seller_discount_pct < 100) {
          lastDiscountLimit.current = settings.behavior.max_seller_discount_pct;
        }
        setSavedSettings(cloneSettings(settings));
        setDraft(cloneSettings(settings));
      })
      .catch((cause) => {
        if (active) setError(publicError(cause, "Settings could not be loaded."));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [loadAttempt, open]);

  const pdfValidationError = useMemo(() => validatePdfSettings(draft?.pdf ?? null), [draft?.pdf]);
  const rulesValidationError = useMemo(() => validateBehaviorSettings(draft?.behavior ?? null), [draft?.behavior]);
  const validationError = pdfValidationError || rulesValidationError;
  const dirty = Boolean(draft && savedSettings && !settingsEqual(draft, savedSettings));

  useEffect(() => {
    if (!open || !dirty) return;
    const preventAccidentalExit = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", preventAccidentalExit);
    return () => window.removeEventListener("beforeunload", preventAccidentalExit);
  }, [dirty, open]);

  const updatePdf = <Key extends keyof QuotePdfSettings>(key: Key, value: QuotePdfSettings[Key]) => {
    setDraft((current) => current ? { ...current, pdf: { ...current.pdf, [key]: value } } : current);
    setSaveState("idle");
    setError("");
  };

  const updateBehavior = <Key extends keyof QuoteBehaviorSettings>(key: Key, value: QuoteBehaviorSettings[Key]) => {
    setDraft((current) => current ? { ...current, behavior: { ...current.behavior, [key]: value } } : current);
    setSaveState("idle");
    setError("");
  };

  const discardChanges = () => {
    if (!savedSettings) return;
    setDraft(cloneSettings(savedSettings));
    setSaveState("idle");
    setError("");
  };

  const requestOpenChange = (nextOpen: boolean) => {
    if (!nextOpen && dirty) {
      setConfirmDiscardOpen(true);
      return;
    }
    onOpenChange(nextOpen);
  };

  const discardAndClose = () => {
    discardChanges();
    setConfirmDiscardOpen(false);
    onOpenChange(false);
  };

  const save = async () => {
    if (!draft || validationError || saveState === "saving") return;
    setSaveState("saving");
    setError("");
    try {
      const result = await api.updateAdminSettings(normalizeSettings(draft));
      setSavedSettings(cloneSettings(result));
      setDraft(cloneSettings(result));
      setSaveState("saved");
      onSaved?.(result);
    } catch (cause) {
      setError(publicError(cause, "Settings could not be saved."));
      setSaveState("idle");
    }
  };

  const openPdfPreview = async () => {
    if (!draft || pdfValidationError || previewing || saveState === "saving") return;
    const previewWindow = window.open("about:blank", "_blank");
    if (previewWindow) previewWindow.opener = null;
    setPreviewing(true);
    setError("");
    try {
      const blob = await api.previewAdminPdf(normalizeSettings(draft).pdf);
      openPdfBlob(blob, previewWindow);
    } catch (cause) {
      previewWindow?.close();
      setError(publicError(cause, "The sample PDF could not be generated."));
    } finally {
      setPreviewing(false);
    }
  };

  return (
    <Sheet open={open} onOpenChange={requestOpenChange}>
      <SheetContent side="right" className="admin-settings-sheet">
        <SheetHeader className="admin-settings-header">
          <SheetTitle>Workspace settings</SheetTitle>
          <SheetDescription>Manage document defaults and the rules applied when quotes are priced or generated.</SheetDescription>
        </SheetHeader>

        {loading ? (
          <AdminSettingsSkeleton />
        ) : draft ? (
          <Tabs
            value={activeTab}
            onValueChange={(value) => setActiveTab(value as SettingsTab)}
            className="admin-settings-tabs"
          >
            <div className="admin-settings-nav">
              <TabsList className="admin-settings-tab-list" aria-label="Workspace settings sections">
                <TabsTrigger value="pdf">Quote PDF</TabsTrigger>
                <TabsTrigger value="rules">Quote rules</TabsTrigger>
              </TabsList>
              {activeTab === "pdf" && (
                <PdfPreviewAction
                  disabled={Boolean(pdfValidationError) || saveState === "saving"}
                  previewing={previewing}
                  onOpen={() => void openPdfPreview()}
                />
              )}
            </div>
            <ScrollArea className="admin-settings-scroll">
              <TabsContent value="pdf" className="admin-settings-tab">
                <fieldset className="admin-settings-edit-scope" disabled={saveState === "saving"}>
                  <div className="admin-settings-form">
                    <SettingsSection title="Document identity" description="Brand and format the customer-facing quote.">
                      <div className="admin-field-grid">
                        <SettingsField id="admin-brand-name" label="Brand name">
                          <Input
                            id="admin-brand-name"
                            value={draft.pdf.brand_name}
                            maxLength={80}
                            aria-invalid={!draft.pdf.brand_name.trim() || undefined}
                            onChange={(event) => updatePdf("brand_name", event.target.value)}
                          />
                        </SettingsField>
                        <SettingsField id="admin-document-title" label="Document title">
                          <Input
                            id="admin-document-title"
                            value={draft.pdf.document_title}
                            maxLength={100}
                            aria-invalid={!draft.pdf.document_title.trim() || undefined}
                            onChange={(event) => updatePdf("document_title", event.target.value)}
                          />
                        </SettingsField>
                        <SettingsField id="admin-accent-color" label="Accent color" hint="Six-digit hex">
                          <div className="admin-color-field">
                            <span
                              className="admin-color-swatch"
                              aria-hidden="true"
                              style={{ "--admin-accent": previewAccent(draft.pdf.accent_color) } as CSSProperties}
                            />
                            <Input
                              id="admin-accent-color"
                              value={draft.pdf.accent_color}
                              maxLength={7}
                              spellCheck={false}
                              aria-describedby="admin-accent-color-hint"
                              aria-invalid={!isHexColor(draft.pdf.accent_color)}
                              onChange={(event) => updatePdf("accent_color", event.target.value)}
                            />
                          </div>
                        </SettingsField>
                        <SettingsField id="admin-validity-days" label="Valid for" hint="Days">
                          <Input
                            id="admin-validity-days"
                            type="number"
                            min={1}
                            max={365}
                            step={1}
                            value={draft.pdf.validity_days}
                            aria-describedby="admin-validity-days-hint"
                            aria-invalid={!validValidityDays(draft.pdf.validity_days) || undefined}
                            onChange={(event) => updatePdf("validity_days", Number(event.target.value))}
                          />
                        </SettingsField>
                        <SettingsField id="admin-pdf-layout" label="Layout">
                          <Select value={draft.pdf.layout} onValueChange={(value) => updatePdf("layout", value as QuotePdfSettings["layout"])}>
                            <SelectTrigger id="admin-pdf-layout" aria-label="PDF layout">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="classic">Classic</SelectItem>
                              <SelectItem value="compact">Compact</SelectItem>
                            </SelectContent>
                          </Select>
                        </SettingsField>
                      </div>
                      <SettingsField id="admin-footer-text" label="Footer text">
                        <Input
                          id="admin-footer-text"
                          value={draft.pdf.footer_text}
                          maxLength={180}
                          aria-invalid={!draft.pdf.footer_text.trim() || undefined}
                          onChange={(event) => updatePdf("footer_text", event.target.value)}
                        />
                      </SettingsField>
                      <SettingsField id="admin-terms-text" label="Terms">
                        <Textarea
                          id="admin-terms-text"
                          value={draft.pdf.terms_text}
                          maxLength={4000}
                          rows={5}
                          aria-invalid={!draft.pdf.terms_text.trim() || undefined}
                          onChange={(event) => updatePdf("terms_text", event.target.value)}
                        />
                      </SettingsField>
                    </SettingsSection>

                    <SettingsSection title="Pricing details" description="Choose which commercial details customers can see.">
                      <SwitchField
                        id="admin-show-list-prices"
                        label="Show list prices"
                        description="Include list price beside the negotiated price."
                        checked={draft.pdf.show_list_prices}
                        onCheckedChange={(checked) => updatePdf("show_list_prices", checked)}
                      />
                      <SwitchField
                        id="admin-show-savings"
                        label="Show savings"
                        description="Summarize customer savings in the PDF."
                        checked={draft.pdf.show_savings}
                        onCheckedChange={(checked) => updatePdf("show_savings", checked)}
                      />
                    </SettingsSection>
                  </div>
                </fieldset>
              </TabsContent>

              <TabsContent value="rules" className="admin-settings-tab">
                <fieldset className="admin-settings-edit-scope" disabled={saveState === "saving"}>
                  <div className="admin-settings-form admin-rules-form">
                    <SettingsSection title="Approval rules" description="Hold quotes that exceed a configured pricing threshold.">
                      <div className="admin-field-grid">
                        <SettingsField id="admin-approval-threshold" label="Quote total review threshold" hint="USD">
                          <Input
                            id="admin-approval-threshold"
                            type="number"
                            min={1}
                            max={100000000}
                            step={1000}
                            value={draft.behavior.approval_threshold}
                            aria-describedby="admin-approval-threshold-hint"
                            aria-invalid={!validApprovalThreshold(draft.behavior.approval_threshold) || undefined}
                            onChange={(event) => updateBehavior("approval_threshold", Number(event.target.value))}
                          />
                        </SettingsField>
                        {draft.behavior.max_seller_discount_pct < 100 && (
                          <SettingsField id="admin-max-discount" label="Discount review threshold" hint="Percent">
                            <Input
                              id="admin-max-discount"
                              type="number"
                              min={0}
                              max={99.9}
                              step={0.1}
                              value={draft.behavior.max_seller_discount_pct}
                              aria-describedby="admin-max-discount-hint"
                              aria-invalid={!validDiscountThreshold(draft.behavior.max_seller_discount_pct) || undefined}
                              onChange={(event) => {
                                const value = Number(event.target.value);
                                lastDiscountLimit.current = value;
                                updateBehavior("max_seller_discount_pct", value);
                              }}
                            />
                          </SettingsField>
                        )}
                      </div>
                      <SwitchField
                        id="admin-limit-seller-discounts"
                        label="Review deep discounts"
                        description="Require approval when a net price exceeds the discount threshold."
                        checked={draft.behavior.max_seller_discount_pct < 100}
                        onCheckedChange={(checked) => {
                          if (!checked && draft.behavior.max_seller_discount_pct < 100) {
                            lastDiscountLimit.current = draft.behavior.max_seller_discount_pct;
                          }
                          updateBehavior(
                            "max_seller_discount_pct",
                            checked ? Math.min(lastDiscountLimit.current, 99.9) : 100,
                          );
                        }}
                      />
                    </SettingsSection>

                    <SettingsSection title="Seller controls">
                      <SwitchField
                        id="admin-allow-seller-price-edits"
                        label="Edit net prices"
                        description="Allow sellers to change catalog pricing on a quote."
                        checked={draft.behavior.allow_seller_price_edits}
                        onCheckedChange={(checked) => updateBehavior("allow_seller_price_edits", checked)}
                      />
                    </SettingsSection>

                    <SettingsSection title="Automatic additions">
                      <SwitchField
                        id="admin-auto-care-plan"
                        label="Attach eligible care plans"
                        description="Include Equipment Care when quoted equipment is eligible."
                        checked={draft.behavior.auto_attach_care_plan}
                        onCheckedChange={(checked) => updateBehavior("auto_attach_care_plan", checked)}
                      />
                    </SettingsSection>
                  </div>
                </fieldset>
              </TabsContent>
            </ScrollArea>
          </Tabs>
        ) : (
          <div className="admin-settings-empty">
            {error && (
              <Alert variant="destructive" role="alert">
                <TriangleAlert aria-hidden="true" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <p>Settings could not be loaded.</p>
            <div className="admin-empty-actions">
              <Button onClick={() => setLoadAttempt((current) => current + 1)}>Retry</Button>
              <Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
            </div>
          </div>
        )}

        {!loading && draft && (
          <SheetFooter className="admin-settings-footer">
            <div className="admin-save-feedback" aria-live="polite">
              {error ? (
                <Alert variant="destructive" role="alert">
                  <TriangleAlert aria-hidden="true" />
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              ) : validationError ? (
                <span>{validationError}</span>
              ) : saveState === "saved" ? (
                <span className="admin-save-success"><CheckCircle2 aria-hidden="true" /> Saved</span>
              ) : dirty ? (
                <span>Unsaved changes</span>
              ) : null}
            </div>
            <div className="admin-settings-actions">
              <Button type="button" variant="ghost" onClick={discardChanges} disabled={!dirty || saveState === "saving"}>
                <RotateCcw aria-hidden="true" /> Discard changes
              </Button>
              <Button type="button" onClick={() => void save()} disabled={!dirty || Boolean(validationError) || saveState === "saving"}>
                {saveState === "saving" ? <Spinner aria-hidden="true" /> : <Save aria-hidden="true" />}
                {saveState === "saving" ? "Saving" : "Save changes"}
              </Button>
            </div>
          </SheetFooter>
        )}
      </SheetContent>
      <AlertDialog open={confirmDiscardOpen} onOpenChange={setConfirmDiscardOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Discard unsaved changes?</AlertDialogTitle>
            <AlertDialogDescription>
              Your document and quote-rule edits have not been saved.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Continue editing</AlertDialogCancel>
            <AlertDialogAction onClick={discardAndClose}>Discard changes</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Sheet>
  );
}

function SettingsSection({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <section className="admin-settings-section">
      <header className="admin-section-header">
        <h3>{title}</h3>
        {description && <p>{description}</p>}
      </header>
      <div className="admin-settings-section-content">{children}</div>
    </section>
  );
}

function SettingsField({ id, label, hint, children }: { id: string; label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="admin-settings-field">
      <div className="admin-field-label">
        <Label htmlFor={id}>{label}</Label>
        {hint && <span id={`${id}-hint`}>{hint}</span>}
      </div>
      {children}
    </div>
  );
}

function SwitchField({ id, label, description, checked, onCheckedChange }: {
  id: string;
  label: string;
  description: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <div className="admin-switch-field">
      <div>
        <Label htmlFor={id}>{label}</Label>
        <p id={`${id}-description`}>{description}</p>
      </div>
      <Switch id={id} aria-describedby={`${id}-description`} checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  );
}

function PdfPreviewAction({ disabled, previewing, onOpen }: {
  disabled: boolean;
  previewing: boolean;
  onOpen: () => void;
}) {
  return (
    <Button className="admin-preview-action" type="button" variant="outline" size="sm" onClick={onOpen} disabled={disabled || previewing}>
      {previewing ? <Spinner aria-hidden="true" /> : <ExternalLink aria-hidden="true" />}
      {previewing ? "Opening" : "Preview PDF"}
    </Button>
  );
}

function AdminSettingsSkeleton() {
  return (
    <div className="admin-settings-skeleton" role="status" aria-label="Loading workspace settings">
      <Skeleton />
      <Skeleton />
      <Skeleton />
      <Skeleton />
      <span className="sr-only">Loading workspace settings</span>
    </div>
  );
}

function validatePdfSettings(settings: QuotePdfSettings | null): string {
  if (!settings) return "";
  if (!settings.brand_name.trim()) return "Enter a brand name.";
  if (!settings.document_title.trim()) return "Enter a document title.";
  if (!isHexColor(settings.accent_color)) return "Use a six-digit hex color, such as #FF3621.";
  if (!settings.footer_text.trim()) return "Enter footer text.";
  if (!settings.terms_text.trim()) return "Enter quote terms.";
  if (!validValidityDays(settings.validity_days)) return "Validity must be between 1 and 365 days.";
  return "";
}

function validateBehaviorSettings(settings: QuoteBehaviorSettings | null): string {
  if (!settings) return "";
  if (!validApprovalThreshold(settings.approval_threshold)) return "Quote total review threshold must be greater than zero.";
  if (!validDiscountThreshold(settings.max_seller_discount_pct)) return "Discount review threshold must be between 0 and 100%.";
  return "";
}

function validValidityDays(value: number): boolean {
  return Number.isInteger(value) && value >= 1 && value <= 365;
}

function validApprovalThreshold(value: number): boolean {
  return Number.isFinite(value) && value > 0 && value <= 100_000_000;
}

function validDiscountThreshold(value: number): boolean {
  return Number.isFinite(value) && value >= 0 && value <= 100;
}

function normalizeSettings(settings: AdminSettings): AdminSettings {
  return {
    pdf: {
      ...settings.pdf,
      brand_name: settings.pdf.brand_name.trim(),
      document_title: settings.pdf.document_title.trim(),
      accent_color: settings.pdf.accent_color.toUpperCase(),
      footer_text: settings.pdf.footer_text.trim(),
      terms_text: settings.pdf.terms_text.trim(),
    },
    behavior: { ...settings.behavior },
  };
}

function cloneSettings(settings: AdminSettings): AdminSettings {
  return { pdf: { ...settings.pdf }, behavior: { ...settings.behavior } };
}

function settingsEqual(left: AdminSettings, right: AdminSettings): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function isHexColor(value: string): boolean {
  return /^#[0-9A-Fa-f]{6}$/.test(value);
}

function previewAccent(value: string): string {
  return isHexColor(value) ? value : "var(--primary)";
}

function openPdfBlob(blob: Blob, previewWindow: Window | null): void {
  const url = URL.createObjectURL(blob);
  if (previewWindow) {
    previewWindow.location.replace(url);
  } else {
    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    document.body.appendChild(link);
    link.click();
    link.remove();
  }
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

function publicError(cause: unknown, fallback: string): string {
  return cause instanceof Error && cause.message ? cause.message : fallback;
}
