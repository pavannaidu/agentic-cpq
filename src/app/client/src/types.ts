export type ViewRole = "seller" | "manager";
export type AgentIntent = "auto" | "research" | "build";

export interface Account {
  account_id: string;
  name: string;
  city?: string;
  state?: string;
  specialty?: string;
  segment?: string;
  account_record_type?: "synthetic_demo_account" | "public_demo_prospect" | string;
  relationship_status?: string;
  provenance_url?: string | null;
  chair_count?: number;
  num_locations?: number;
  location_count?: number;
  annual_spend?: number;
  [key: string]: unknown;
}

export interface Product {
  sku: string;
  title: string;
  category: string;
  unit_price?: number;
  list_price?: number;
  description?: string;
  warranty_eligible?: boolean;
  [key: string]: unknown;
}

export interface SourceFreshness {
  source: string;
  status: string;
  detail: string;
}

export interface SourceEvidence {
  source: string;
  title: string;
  detail: string;
  url?: string;
}

export interface ControlSignal {
  label: string;
  status: string;
  detail?: string;
}

export interface BootstrapState {
  app_name?: string;
  environment?: string;
  default_account_id: string;
  accounts: Account[];
  source_freshness: SourceFreshness[];
  product_snapshot: Product[];
  agent_names?: Record<string, string>;
  quote_policy?: QuoteBehaviorSettings;
  use_mock_fallback?: boolean;
}

export interface CurrentUser {
  email?: string;
  username?: string;
  authenticated?: boolean;
  can_manage?: boolean;
  default_view?: ViewRole;
  allowed_views?: ViewRole[];
  execution_identity?: "service_principal" | "on_behalf_of" | string;
}

export interface QuotePdfSettings {
  layout: "classic" | "compact";
  show_list_prices: boolean;
  show_savings: boolean;
  brand_name: string;
  document_title: string;
  accent_color: string;
  footer_text: string;
  terms_text: string;
  validity_days: number;
}

export interface QuoteBehaviorSettings {
  approval_threshold: number;
  max_seller_discount_pct: number;
  auto_attach_care_plan: boolean;
  allow_seller_price_edits: boolean;
}

export interface AdminSettings {
  pdf: QuotePdfSettings;
  behavior: QuoteBehaviorSettings;
}

export interface DraftLineItem {
  sku: string;
  title: string;
  category: string;
  quantity: number;
  unit_price: number;
  list_price?: number | null;
  recommended_price?: number | null;
  supplier_cost?: number | null;
  gross_margin_pct?: number | null;
  approval_required?: boolean;
  approval_reason?: string;
  warranty_eligible?: boolean;
  total_price?: number | null;
  overpay_amount?: number;
  legacy_supplier_cost?: number | null;
  correct_supplier_cost?: number | null;
  is_addon?: boolean;
  covers_sku?: string | null;
  rationale?: string;
  confidence?: string;
  line_insights?: ControlSignal[];
  insights?: SourceEvidence[];
  citations?: SourceEvidence[];
}

export interface DraftOrder {
  draft_order_id: string;
  account_id: string;
  status: string;
  line_items: DraftLineItem[];
  subtotal: number;
  grand_total: number;
  quote_id?: string | null;
  version?: number;
  revision_number?: number;
  parent_draft_order_id?: string | null;
  source_quote_id?: string | null;
}

export interface Recommendation {
  mode?: string;
  summary: string;
  bundle_rationale?: string;
  items: DraftLineItem[];
  pricing_controls?: ControlSignal[];
  approval_path?: ControlSignal[];
  business_impact?: ControlSignal[];
  quote_readiness?: ControlSignal[];
  requirements_coverage?: ControlSignal[];
  source_lineage?: ControlSignal[];
  source_freshness?: SourceFreshness[];
  intelligence_signals?: ControlSignal[];
  manager_insights?: ControlSignal[];
  warnings?: string[];
  next_steps?: string[];
  agent_path?: string[];
  metadata?: Record<string, unknown>;
  citations?: SourceEvidence[];
  sql?: string;
  columns?: string[];
  rows?: unknown[][];
  truncated?: boolean;
  win_probability?: number | null;
  follow_up_action?: string;
  conversion_risk?: string;
  equipment_care_prompt?: string;
  pdf_ready?: boolean;
  overpay_prevented_total?: number;
  apply_mode?: "add" | "replace";
  recommendation_id?: string;
  revision?: number;
  draft_version?: number | null;
  evidence?: GenieEvidenceEnvelope[];
}

export type QuotePlanStatus =
  | "planning"
  | "needs_input"
  | "ready"
  | "applying"
  | "awaiting_approval"
  | "ready_for_pdf"
  | "completed"
  | "stale"
  | "failed"
  | "cancelled";

export interface PlanStep {
  step_id: string;
  title: string;
  status: "pending" | "in_progress" | "needs_input" | "completed" | "blocked" | "skipped" | "failed";
  detail?: string;
  sequence?: number;
  requires_confirmation?: boolean;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface QuoteScenario {
  scenario_id: string;
  title: string;
  summary?: string;
  rationale?: string;
  recommendation?: Recommendation | null;
  recommendation_id?: string | null;
  recommendation_revision?: number | null;
  estimated_total?: number | null;
  total_delta?: number | null;
  requires_approval?: boolean;
  is_recommended?: boolean;
  metadata?: Record<string, unknown>;
}

export interface ConfirmationTokenMetadata {
  token: string;
  token_id: string;
  idempotency_key: string;
  expires_at: string;
}

export interface ActionProposal {
  proposal_id: string;
  action_type: string;
  summary: string;
  scenario_id?: string | null;
  recommendation_id?: string | null;
  recommendation_revision?: number | null;
  draft_version: number;
  plan_revision: number;
  idempotency_key: string;
  confirmation?: ConfirmationTokenMetadata | null;
  payload?: Record<string, unknown>;
}

export interface QuotePlanMetadata extends Record<string, unknown> {
  clarifying_question?: string;
  summary?: string;
  message?: string;
}

export interface QuotePlan {
  plan_id: string;
  account_id: string;
  draft_order_id: string;
  base_draft_version: number;
  revision: number;
  goal: string;
  status: QuotePlanStatus;
  steps?: PlanStep[];
  scenarios?: QuoteScenario[];
  selected_scenario_id?: string | null;
  action_proposal?: ActionProposal | null;
  created_by?: string;
  error_message?: string;
  metadata?: QuotePlanMetadata;
  created_at?: string;
  updated_at?: string;
}

export interface Evidence {
  citations: SourceEvidence[];
  sql: string;
  columns: string[];
  rows: unknown[][];
  checks: ControlSignal[];
  freshness: SourceFreshness[];
  tools: string[];
  truncated: boolean;
  executionIdentity?: string;
  partial?: boolean;
}

export type ConversationMessage =
  | { id: string; role: "user"; kind: "text"; content: string }
  | { id: string; role: "assistant"; kind: "answer"; content: string; evidence: Evidence; error?: boolean }
  | { id: string; role: "assistant"; kind: "recommendation"; recommendation: Recommendation; evidence: Evidence; applied?: boolean }
  | { id: string; role: "assistant"; kind: "error"; content: string; retryPrompt?: string };

export interface AgentStage {
  key: string;
  label: string;
  status: "active" | "done";
}

export interface HistoryItem {
  draft_order_id: string;
  status: string;
  grand_total: number;
  quote_id?: string | null;
  line_count: number;
  updated_at?: string;
  version?: number | string;
  revision_number?: number;
  parent_draft_order_id?: string | null;
  source_quote_id?: string | null;
}

export interface HistoryResponse {
  items: HistoryItem[];
}

export interface FollowupSuggestionsResponse {
  suggestions: string[];
}

export interface GenieResponse {
  conversation_id?: string;
  message_id?: string;
  text?: string;
  answer?: string;
  sql?: string;
  description?: string;
  columns?: string[];
  rows?: unknown[][];
  truncated?: boolean;
  error?: boolean;
  citations?: Array<SourceEvidence | GenieCitation>;
  checks?: ControlSignal[];
  source_freshness?: SourceFreshness[];
  execution_identity?: string;
  status?: string;
  source?: string;
  freshness?: { retrieved_at?: string; status?: string; detail?: string };
  sql_attachments?: GenieSqlAttachment[];
  knowledge_fallback?: { used?: boolean; source?: string; reason?: string; answer?: string };
  evidence?: GenieEvidenceEnvelope[];
  genie_conversation_id?: string | null;
  knowledge_fallback_used?: boolean;
  metadata?: Record<string, unknown> & { execution_identity?: string; view_role?: string };
}

export interface GenieCitation {
  citation_id?: string;
  title?: string;
  uri?: string;
  snippet?: string;
  source?: string;
}

export interface GenieSqlAttachment {
  attachment_id?: string;
  sql?: string;
  description?: string;
  columns?: string[];
  rows?: unknown[][];
  truncated?: boolean;
  error_code?: string | null;
}

export interface GenieEvidenceEnvelope extends GenieResponse {
  answer?: string;
}

export type AgentStreamEvent =
  | { event: "stage"; data: Partial<AgentStage> & { key: string } }
  | { event: "plan"; data: QuotePlan }
  | { event: "recommendation"; data: Recommendation }
  | { event: "conversation"; data: Record<string, unknown> & { answer?: string } }
  | { event: "error"; data: { detail?: string } }
  | { event: "done"; data: Record<string, never> };

export interface QuoteDiff {
  added: DraftLineItem[];
  removed: DraftLineItem[];
  changed: Array<{ before: DraftLineItem; after: DraftLineItem }>;
  currentTotal: number;
  proposedTotal: number;
  delta: number;
  currentApproval: boolean;
  proposedApproval: boolean;
  protectionTotal: number;
  resultLines: DraftLineItem[];
}
