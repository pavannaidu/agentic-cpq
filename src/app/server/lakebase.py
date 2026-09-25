"""Lakebase (managed Postgres) data-access layer.

Persists draft orders, conversations, recommendations, and final quote payloads,
and backs product search. When Lakebase is not configured (no PG* env vars), the
app falls back to the in-memory DraftOrderStore so local dev and tests still work.

Auth: the app's service principal is granted a Postgres role (named after its
client id) via the App's database resource. We mint a short-lived OAuth token at
runtime through the SDK and use it as the Postgres password (token TTL ~1h).
"""

from __future__ import annotations

import copy
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .agent_plans import (
    ACTIVE_PLAN_STATUSES,
    AgentActionRecord,
    PlanStatus,
    QuotePlan,
    apply_plan_changes,
)
from .models import CPQAdminSettings, ConversationTurn, DraftLineItem, DraftOrder
from .state import DraftConflict

# Columns persisted for each draft line, in a stable order shared by insert/select.
_LINE_COLUMNS = (
    "sku",
    "title",
    "category",
    "quantity",
    "unit_price",
    "list_price",
    "recommended_price",
    "supplier_cost",
    "gross_margin_pct",
    "approval_required",
    "approval_reason",
    "warranty_eligible",
    "total_price",
    "overpay_amount",
    "legacy_supplier_cost",
    "correct_supplier_cost",
    "is_addon",
    "covers_sku",
)

_MAX_CONVERSATION_TURNS = 12
_ACTIVE_PLAN_STATUS_SQL = ", ".join(
    f"'{status.value}'" for status in sorted(ACTIVE_PLAN_STATUSES, key=lambda value: value.value)
)

# The app's service principal has CREATE on the database but not on the locked-down
# `public` schema (Postgres 15+). Use a dedicated schema the SP creates and owns.
_APP_SCHEMA = "cpq"


def lakebase_configured() -> bool:
    """True when the App injected Lakebase connection env vars."""
    configured = bool(os.environ.get("PGHOST") and os.environ.get("PGUSER"))
    if configured:
        _database_name()
    return configured


def _database_name() -> str:
    database = os.environ.get("PGDATABASE", "").strip()
    if not database:
        raise RuntimeError(
            "PGDATABASE is required when Lakebase is configured; "
            "set it to the database bound to this app."
        )
    return database


def _instance_name() -> str:
    # The database resource doesn't expose the instance name directly, so we set
    # it explicitly via app.yaml env. Fall back to deriving nothing (caller errors).
    return os.environ.get("AGENTIC_CPQ_LAKEBASE_INSTANCE", "")


class _TokenCache:
    """Caches the OAuth credential used as the Postgres password."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._token: str | None = None
        self._expires_at: datetime = datetime.min.replace(tzinfo=timezone.utc)

    def get(self) -> str:
        with self._lock:
            now = datetime.now(timezone.utc)
            if self._token and now < self._expires_at - timedelta(minutes=5):
                return self._token
            self._token, self._expires_at = self._mint()
            return self._token

    @staticmethod
    def _mint() -> tuple[str, datetime]:
        from databricks.sdk import WorkspaceClient

        instance = _instance_name()
        if not instance:
            raise RuntimeError("AGENTIC_CPQ_LAKEBASE_INSTANCE is not set; cannot mint a Lakebase credential.")
        cred = WorkspaceClient().database.generate_database_credential(
            request_id=str(uuid.uuid4()),
            instance_names=[instance],
        )
        expires = _parse_expiry(cred.expiration_time)
        return cred.token, expires


def _parse_expiry(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    # Conservative default if the API omits/changes the field.
    return datetime.now(timezone.utc) + timedelta(minutes=50)


_token_cache = _TokenCache()


def _connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ["PGHOST"],
        port=os.environ.get("PGPORT", "5432"),
        dbname=_database_name(),
        user=os.environ["PGUSER"],
        password=_token_cache.get(),
        sslmode=os.environ.get("PGSSLMODE", "require"),
        application_name=os.environ.get("PGAPPNAME", "agentic-cpq-app"),
        # Resolve unqualified table names to the app's own schema.
        options=f"-c search_path={_APP_SCHEMA},public",
        autocommit=True,
        row_factory=dict_row,
    )


# --------------------------------------------------------------------------- #
# Schema + seeding
# --------------------------------------------------------------------------- #

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS draft_orders (
    draft_order_id TEXT PRIMARY KEY,
    account_id     TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'draft',
    subtotal       NUMERIC NOT NULL DEFAULT 0,
    grand_total    NUMERIC NOT NULL DEFAULT 0,
    quote_id       TEXT,
    owner_email    TEXT NOT NULL DEFAULT '',
    version        BIGINT NOT NULL DEFAULT 0,
    revision_number BIGINT NOT NULL DEFAULT 1,
    parent_draft_order_id TEXT,
    source_quote_id TEXT,
    genie_conversation_id TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS draft_line_items (
    id                  BIGSERIAL PRIMARY KEY,
    draft_order_id      TEXT NOT NULL REFERENCES draft_orders(draft_order_id) ON DELETE CASCADE,
    position            INTEGER NOT NULL,
    sku                 TEXT NOT NULL,
    title               TEXT,
    category            TEXT,
    quantity            INTEGER NOT NULL DEFAULT 1,
    unit_price          NUMERIC,
    list_price          NUMERIC,
    recommended_price   NUMERIC,
    supplier_cost       NUMERIC,
    gross_margin_pct    NUMERIC,
    approval_required   BOOLEAN DEFAULT FALSE,
    approval_reason     TEXT NOT NULL DEFAULT '',
    warranty_eligible   BOOLEAN DEFAULT FALSE,
    total_price         NUMERIC,
    overpay_amount      NUMERIC DEFAULT 0,
    legacy_supplier_cost NUMERIC,
    correct_supplier_cost NUMERIC,
    is_addon            BOOLEAN DEFAULT FALSE,
    covers_sku          TEXT
);

CREATE TABLE IF NOT EXISTS conversations (
    id             BIGSERIAL PRIMARY KEY,
    draft_order_id TEXT NOT NULL REFERENCES draft_orders(draft_order_id) ON DELETE CASCADE,
    role           TEXT NOT NULL,
    content        TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recommendations (
    draft_order_id TEXT PRIMARY KEY REFERENCES draft_orders(draft_order_id) ON DELETE CASCADE,
    payload        JSONB NOT NULL,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recommendation_revisions (
    recommendation_id TEXT PRIMARY KEY,
    draft_order_id     TEXT NOT NULL REFERENCES draft_orders(draft_order_id) ON DELETE CASCADE,
    revision           BIGINT NOT NULL,
    draft_version      BIGINT NOT NULL,
    payload            JSONB NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (draft_order_id, revision)
);

CREATE TABLE IF NOT EXISTS recommendation_applications (
    recommendation_id TEXT PRIMARY KEY REFERENCES recommendation_revisions(recommendation_id) ON DELETE CASCADE,
    draft_order_id     TEXT NOT NULL REFERENCES draft_orders(draft_order_id) ON DELETE CASCADE,
    revision           BIGINT NOT NULL,
    mode               TEXT NOT NULL,
    result             JSONB NOT NULL,
    applied_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS quotes (
    quote_id       TEXT PRIMARY KEY,
    draft_order_id TEXT,
    account_id     TEXT,
    payload        JSONB NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS admin_settings (
    settings_key TEXT PRIMARY KEY,
    payload      JSONB NOT NULL,
    updated_by   TEXT NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_plans (
    plan_id             TEXT PRIMARY KEY,
    draft_order_id      TEXT NOT NULL REFERENCES draft_orders(draft_order_id) ON DELETE CASCADE,
    account_id          TEXT NOT NULL,
    base_draft_version  BIGINT NOT NULL,
    revision            BIGINT NOT NULL,
    status              TEXT NOT NULL,
    created_by          TEXT NOT NULL,
    payload             JSONB NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS agent_plans_one_active_per_draft
ON agent_plans (draft_order_id)
WHERE status IN (
    'planning', 'needs_input', 'ready', 'applying',
    'awaiting_approval', 'ready_for_pdf'
);

CREATE TABLE IF NOT EXISTS agent_actions (
    action_id              TEXT PRIMARY KEY,
    plan_id                TEXT NOT NULL REFERENCES agent_plans(plan_id) ON DELETE CASCADE,
    draft_order_id         TEXT NOT NULL,
    account_id             TEXT NOT NULL,
    action_type            TEXT NOT NULL,
    actor_email            TEXT NOT NULL,
    plan_revision          BIGINT NOT NULL,
    draft_version          BIGINT NOT NULL,
    idempotency_key        TEXT,
    confirmation_token_id  TEXT,
    payload                JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS agent_actions_plan_idempotency
ON agent_actions (plan_id, idempotency_key)
WHERE idempotency_key IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS agent_actions_confirmation_once
ON agent_actions (confirmation_token_id)
WHERE confirmation_token_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS agent_actions_plan_created
ON agent_actions (plan_id, created_at, action_id);

-- Idempotent migrations for tables that predate a column (CREATE TABLE IF NOT
-- EXISTS won't alter an existing table). Equipment Care care-plan lines carry these.
ALTER TABLE draft_line_items ADD COLUMN IF NOT EXISTS is_addon BOOLEAN DEFAULT FALSE;
ALTER TABLE draft_line_items ADD COLUMN IF NOT EXISTS covers_sku TEXT;
ALTER TABLE draft_orders ADD COLUMN IF NOT EXISTS owner_email TEXT NOT NULL DEFAULT '';
ALTER TABLE draft_orders ADD COLUMN IF NOT EXISTS version BIGINT NOT NULL DEFAULT 0;
ALTER TABLE draft_orders ADD COLUMN IF NOT EXISTS revision_number BIGINT NOT NULL DEFAULT 1;
ALTER TABLE draft_orders ADD COLUMN IF NOT EXISTS parent_draft_order_id TEXT;
ALTER TABLE draft_orders ADD COLUMN IF NOT EXISTS source_quote_id TEXT;
ALTER TABLE draft_orders ADD COLUMN IF NOT EXISTS genie_conversation_id TEXT;
ALTER TABLE draft_line_items ADD COLUMN IF NOT EXISTS approval_reason TEXT NOT NULL DEFAULT '';
"""


def init_schema() -> None:
    with _connect() as conn, conn.cursor() as cur:
        # Create + own a dedicated schema (search_path already points here).
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {_APP_SCHEMA}")
        cur.execute(_SCHEMA_SQL)


# --------------------------------------------------------------------------- #
# Reference data (read-only, UC -> Lakebase synced tables in the `*cpq_ref` schema)
# --------------------------------------------------------------------------- #

# The synced schema is `cpq_ref` in prod but dev-mode name-mangling makes it
# `dev_<user>_cpq_ref` in dev, so we resolve it at runtime (once) by finding the
# `%cpq_ref` schema that actually contains the reference tables.
_ref_schema_cache: str | None = None
_ref_lock = threading.Lock()

# Small TTL cache for reference reads — this data is slow-moving.
_REF_TTL = timedelta(minutes=5)
_ref_data_cache: dict[str, tuple[datetime, Any]] = {}


def _ref_schema() -> str:
    global _ref_schema_cache
    with _ref_lock:
        if _ref_schema_cache:
            return _ref_schema_cache
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT table_schema FROM information_schema.tables "
                "WHERE table_name = 'products' AND table_schema LIKE '%%cpq_ref' "
                "ORDER BY length(table_schema) DESC LIMIT 1"
            )
            row = cur.fetchone()
        if not row:
            raise RuntimeError("No synced reference schema (*cpq_ref with a products table) found.")
        _ref_schema_cache = row["table_schema"]
        return _ref_schema_cache


def _ref_query(sql_template: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    """Run a read against the resolved reference schema. `sql_template` uses {ref}."""
    sql = sql_template.format(ref=f'"{_ref_schema()}"')
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params or [])
        return [_floatify(r) for r in cur.fetchall()]


def _cached(key: str, loader) -> Any:
    now = datetime.now(timezone.utc)
    hit = _ref_data_cache.get(key)
    if hit and now - hit[0] < _REF_TTL:
        return hit[1]
    value = loader()
    _ref_data_cache[key] = (now, value)
    return value


def get_accounts() -> list[dict[str, Any]]:
    def _load() -> list[dict[str, Any]]:
        rows = _ref_query("SELECT * FROM {ref}.accounts ORDER BY name")
        for r in rows:
            r.pop("id", None)
            r["installed_base"] = r.get("installed_base") or []
        return rows
    return _cached("accounts", _load)


def get_account(account_id: str) -> dict[str, Any] | None:
    return next((a for a in get_accounts() if a.get("account_id") == account_id), None)


def get_products() -> list[dict[str, Any]]:
    """Product snapshot shape used by the UI and catalog reconciliation."""
    def _load() -> list[dict[str, Any]]:
        rows = _ref_query(
            "SELECT sku, title, category, description, unit_price, financing_eligible, "
            "default_quantity, bundle_tags, doc_source FROM {ref}.products ORDER BY category, title"
        )
        for r in rows:
            r["bundle_tags"] = r.get("bundle_tags") or []
        return rows
    return _cached("products", _load)


def get_product(sku: str) -> dict[str, Any] | None:
    return next((p for p in get_products() if p.get("sku") == sku), None)


def get_segment_pricing() -> list[dict[str, Any]]:
    return _cached("segment_pricing", lambda: _ref_query("SELECT * FROM {ref}.supplier_segment_pricing"))


def get_price_book() -> list[dict[str, Any]]:
    return _cached("price_book", lambda: _ref_query("SELECT * FROM {ref}.supplier_price_book"))


def get_sample_prompts() -> list[str]:
    return _cached(
        "sample_prompts",
        lambda: [r["prompt"] for r in _ref_query("SELECT prompt FROM {ref}.sample_prompts ORDER BY id")],
    )


def get_source_freshness() -> list[dict[str, Any]]:
    def _load() -> list[dict[str, Any]]:
        rows = _ref_query("SELECT source, status, detail FROM {ref}.source_freshness ORDER BY id")
        return rows
    return _cached("source_freshness", _load)


def get_warranty_eligibility() -> list[dict[str, Any]]:
    """Equipment Care eligibility, per-SKU warranty code, plan name, and rate.

    The app reads this at request time so the specific code, price rate, and
    which SKUs are covered are all editable in data (no redeploy). Raises if the
    synced table lacks the newer columns; the caller falls back to the seed."""
    return _cached(
        "warranty_eligibility",
        lambda: _ref_query(
            "SELECT sku, eligible, warranty_sku, warranty_title, care_plan_pct, attach_prompt "
            "FROM {ref}.warranty_eligibility"
        ),
    )


def overpay_runrate() -> dict[str, Any]:
    """Annualized supplier-overpayment projection from the synced price book."""
    def _load() -> dict[str, Any]:
        rows = _ref_query(
            "SELECT sku, category, overpay_per_unit, annual_order_velocity, "
            "legacy_wholesale_cost, negotiated_cost FROM {ref}.supplier_price_book"
        )
        annual = 0.0
        by_sku: list[dict[str, Any]] = []
        for r in rows:
            per = float(r.get("overpay_per_unit") or 0.0)
            vel = float(r.get("annual_order_velocity") or 0.0)
            if per <= 0 or vel <= 0:
                continue
            annualized = round(per * vel, 2)
            annual += annualized
            by_sku.append(
                {
                    "sku": r["sku"],
                    "overpay_per_unit": per,
                    "annual_order_velocity": vel,
                    "annualized_overpay_prevented": annualized,
                }
            )
        by_sku.sort(key=lambda x: x["annualized_overpay_prevented"], reverse=True)
        return {
            "annualized_overpay_prevented": round(annual, 2),
            "basis": "Per-unit price-check delta applied to synthetic annual equipment order velocity.",
            "is_projection": True,
            "by_sku": by_sku,
        }
    return _cached("overpay_runrate", _load)


def search_products(query: str | None, category: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    ref = f'"{_ref_schema()}"'
    clauses: list[str] = []
    params: list[Any] = []
    if query:
        like = f"%{query}%"
        clauses.append("(sku ILIKE %s OR title ILIKE %s OR category ILIKE %s)")
        params.extend([like, like, like])
    if category:
        clauses.append("category = %s")
        params.append(category)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    sql = (
        "SELECT sku, title, category, unit_price, bundle_tags, financing_eligible "
        f"FROM {ref}.products {where} ORDER BY category, title LIMIT %s"
    )
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    for row in rows:
        row["unit_price"] = float(row["unit_price"]) if row["unit_price"] is not None else None
        row["bundle_tags"] = row.get("bundle_tags") or []
    return rows


# --------------------------------------------------------------------------- #
# Draft-order store (mirrors DraftOrderStore in state.py)
# --------------------------------------------------------------------------- #


class LakebaseDraftOrderStore:
    """Durable equivalent of state.DraftOrderStore, backed by Lakebase Postgres."""

    def create(
        self,
        account_id: str,
        line_items: list[DraftLineItem] | None = None,
        owner_email: str = "",
    ) -> DraftOrder:
        draft_order_id = f"draft-{uuid.uuid4().hex[:12]}"
        order = DraftOrder(
            draft_order_id=draft_order_id,
            account_id=account_id,
            line_items=line_items or [],
            owner_email=owner_email.strip().casefold(),
            version=0,
        )
        self._recalculate(order)
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO draft_orders "
                "(draft_order_id, account_id, status, subtotal, grand_total, owner_email, version) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    order.draft_order_id,
                    order.account_id,
                    order.status,
                    order.subtotal,
                    order.grand_total,
                    order.owner_email,
                    order.version,
                ),
            )
            self._write_lines(cur, draft_order_id, order.line_items)
        return order

    def create_revision(
        self,
        source_draft_order_id: str,
        owner_email: str = "",
    ) -> DraftOrder:
        draft_order_id = f"draft-{uuid.uuid4().hex[:12]}"
        with _connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    "SELECT draft_order_id, account_id, status, subtotal, grand_total, quote_id, "
                    "owner_email, version, revision_number, parent_draft_order_id, source_quote_id "
                    "FROM draft_orders WHERE draft_order_id = %s FOR UPDATE",
                    (source_draft_order_id,),
                )
                header = cur.fetchone()
                if header is None:
                    raise KeyError(source_draft_order_id)
                if header["status"] != "quote-created" or not header.get("quote_id"):
                    raise DraftConflict("Only a sent quote can be revised.")
                cur.execute(
                    f"SELECT {', '.join(_LINE_COLUMNS)} FROM draft_line_items "
                    "WHERE draft_order_id = %s ORDER BY position",
                    (source_draft_order_id,),
                )
                source = self._to_order(header, cur.fetchall())
                order = DraftOrder(
                    draft_order_id=draft_order_id,
                    account_id=source.account_id,
                    line_items=[line.model_copy(deep=True) for line in source.line_items],
                    owner_email=(owner_email or source.owner_email).strip().casefold(),
                    revision_number=source.revision_number + 1,
                    parent_draft_order_id=source.draft_order_id,
                    source_quote_id=source.quote_id,
                    version=0,
                )
                self._recalculate(order)
                cur.execute(
                    "INSERT INTO draft_orders "
                    "(draft_order_id, account_id, status, subtotal, grand_total, owner_email, version, "
                    "revision_number, parent_draft_order_id, source_quote_id) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        order.draft_order_id,
                        order.account_id,
                        order.status,
                        order.subtotal,
                        order.grand_total,
                        order.owner_email,
                        order.version,
                        order.revision_number,
                        order.parent_draft_order_id,
                        order.source_quote_id,
                    ),
                )
                self._write_lines(cur, draft_order_id, order.line_items)
        return order

    def get(self, draft_order_id: str) -> DraftOrder:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT draft_order_id, account_id, status, subtotal, grand_total, quote_id, "
                "owner_email, version, revision_number, parent_draft_order_id, source_quote_id "
                "FROM draft_orders WHERE draft_order_id = %s",
                (draft_order_id,),
            )
            header = cur.fetchone()
            if header is None:
                raise KeyError(draft_order_id)
            cur.execute(
                f"SELECT {', '.join(_LINE_COLUMNS)} FROM draft_line_items "
                "WHERE draft_order_id = %s ORDER BY position",
                (draft_order_id,),
            )
            lines = cur.fetchall()
        return self._to_order(header, lines)

    def find_resumable(
        self,
        account_id: str,
        owner_email: str,
    ) -> DraftOrder | None:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT draft_order_id, account_id, status, subtotal, grand_total, quote_id, "
                "owner_email, version, revision_number, parent_draft_order_id, source_quote_id "
                "FROM draft_orders d WHERE account_id = %s AND owner_email = %s "
                "AND status IN ('draft', 'saved') "
                "AND (status = 'saved' OR EXISTS ("
                "  SELECT 1 FROM draft_line_items l WHERE l.draft_order_id = d.draft_order_id"
                ")) ORDER BY updated_at DESC LIMIT 1",
                (account_id, owner_email.strip().casefold()),
            )
            header = cur.fetchone()
            if header is None:
                return None
            cur.execute(
                f"SELECT {', '.join(_LINE_COLUMNS)} FROM draft_line_items "
                "WHERE draft_order_id = %s ORDER BY position",
                (header["draft_order_id"],),
            )
            lines = cur.fetchall()
        return self._to_order(header, lines)

    def get_agent_snapshot(
        self,
        draft_order_id: str,
        expected_revision: int | None = None,
    ) -> tuple[DraftOrder, str | None]:
        """Capture lines, version, and the server-owned Genie ID in one transaction."""

        with _connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    "SELECT draft_order_id, account_id, status, subtotal, grand_total, quote_id, "
                    "owner_email, version, revision_number, parent_draft_order_id, source_quote_id, "
                    "genie_conversation_id "
                    "FROM draft_orders WHERE draft_order_id = %s FOR SHARE",
                    (draft_order_id,),
                )
                header = cur.fetchone()
                if header is None:
                    raise KeyError(draft_order_id)
                current_version = int(header.get("version") or 0)
                if expected_revision is not None and current_version != expected_revision:
                    raise DraftConflict(
                        f"Draft version {expected_revision} is stale; current version is {current_version}."
                    )
                cur.execute(
                    f"SELECT {', '.join(_LINE_COLUMNS)} FROM draft_line_items "
                    "WHERE draft_order_id = %s ORDER BY position",
                    (draft_order_id,),
                )
                lines = cur.fetchall()
        conversation_id = str(header.get("genie_conversation_id") or "").strip() or None
        return self._to_order(header, lines), conversation_id

    def get_genie_conversation_id(self, draft_order_id: str) -> str | None:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT genie_conversation_id FROM draft_orders WHERE draft_order_id = %s",
                (draft_order_id,),
            )
            row = cur.fetchone()
        if row is None:
            raise KeyError(draft_order_id)
        return str(row.get("genie_conversation_id") or "").strip() or None

    def set_genie_conversation_id(
        self,
        draft_order_id: str,
        conversation_id: str,
    ) -> str:
        trusted_id = conversation_id.strip()
        if not trusted_id:
            raise ValueError("Genie conversation ID cannot be empty.")
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE draft_orders SET genie_conversation_id = %s, updated_at = now() "
                "WHERE draft_order_id = %s",
                (trusted_id, draft_order_id),
            )
            if cur.rowcount == 0:
                raise KeyError(draft_order_id)
        return trusted_id

    def claim_owner(self, draft_order_id: str, owner_email: str) -> DraftOrder:
        owner = owner_email.strip().casefold()
        if not owner:
            raise ValueError("Draft owner is required.")
        with _connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    "SELECT owner_email FROM draft_orders WHERE draft_order_id = %s FOR UPDATE",
                    (draft_order_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise KeyError(draft_order_id)
                current = str(row.get("owner_email") or "").casefold()
                if current and current != owner:
                    raise DraftConflict("Draft order already has a different owner.")
                if not current:
                    cur.execute(
                        "UPDATE draft_orders SET owner_email = %s, updated_at = now() "
                        "WHERE draft_order_id = %s",
                        (owner, draft_order_id),
                    )
        return self.get(draft_order_id)

    def update_lines(
        self,
        draft_order_id: str,
        line_items: list[DraftLineItem],
        expected_version: int | None = None,
    ) -> DraftOrder:
        with _connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    "SELECT version, status FROM draft_orders WHERE draft_order_id = %s FOR UPDATE",
                    (draft_order_id,),
                )
                header = cur.fetchone()
                if header is None:
                    raise KeyError(draft_order_id)
                if header["status"] == "quote-created":
                    raise DraftConflict(
                        "Sent quotes are immutable. Create a revision before making changes."
                    )
                current_version = int(header.get("version") or 0)
                if expected_version is not None and current_version != expected_version:
                    raise DraftConflict(
                        f"Draft version {expected_version} is stale; current version is {current_version}."
                    )
                cur.execute("DELETE FROM draft_line_items WHERE draft_order_id = %s", (draft_order_id,))
                self._write_lines(cur, draft_order_id, line_items)
                subtotal = round(sum((line.total_price or 0.0) for line in line_items), 2)
                cur.execute(
                    "UPDATE draft_orders SET subtotal = %s, grand_total = %s, "
                    "version = version + 1, updated_at = now() WHERE draft_order_id = %s",
                    (subtotal, subtotal, draft_order_id),
                )
        return self.get(draft_order_id)

    def attach_quote(self, draft_order_id: str, quote_id: str) -> DraftOrder:
        with _connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    "SELECT status FROM draft_orders WHERE draft_order_id = %s FOR UPDATE",
                    (draft_order_id,),
                )
                header = cur.fetchone()
                if header is None:
                    raise KeyError(draft_order_id)
                if header["status"] == "quote-created":
                    raise DraftConflict(
                        "Sent quotes are immutable. Create a revision before making changes."
                    )
                cur.execute(
                    "UPDATE draft_orders SET quote_id = %s, status = 'quote-created', updated_at = now() "
                    "WHERE draft_order_id = %s",
                    (quote_id, draft_order_id),
                )
        return self.get(draft_order_id)

    def get_conversation(self, draft_order_id: str) -> list[ConversationTurn]:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM draft_orders WHERE draft_order_id = %s", (draft_order_id,))
            if cur.fetchone() is None:
                raise KeyError(draft_order_id)
            cur.execute(
                "SELECT role, content FROM conversations WHERE draft_order_id = %s ORDER BY id",
                (draft_order_id,),
            )
            rows = cur.fetchall()
        return [ConversationTurn(role=r["role"], content=r["content"]) for r in rows]

    def append_conversation_turns(
        self, draft_order_id: str, turns: list[ConversationTurn]
    ) -> list[ConversationTurn]:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM draft_orders WHERE draft_order_id = %s", (draft_order_id,))
            if cur.fetchone() is None:
                raise KeyError(draft_order_id)
            for turn in turns:
                if turn.content.strip():
                    cur.execute(
                        "INSERT INTO conversations (draft_order_id, role, content) VALUES (%s, %s, %s)",
                        (draft_order_id, turn.role, turn.content),
                    )
            # Trim to the most recent N turns to mirror the in-memory store.
            cur.execute(
                "DELETE FROM conversations WHERE draft_order_id = %s AND id NOT IN "
                "(SELECT id FROM conversations WHERE draft_order_id = %s ORDER BY id DESC LIMIT %s)",
                (draft_order_id, draft_order_id, _MAX_CONVERSATION_TURNS),
            )
        return self.get_conversation(draft_order_id)

    def set_latest_recommendation(
        self,
        draft_order_id: str,
        recommendation: dict[str, Any],
        draft_version: int | None = None,
    ) -> dict[str, Any]:
        with _connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    "SELECT version FROM draft_orders WHERE draft_order_id = %s FOR UPDATE",
                    (draft_order_id,),
                )
                order = cur.fetchone()
                if order is None:
                    raise KeyError(draft_order_id)
                captured_draft_version = (
                    int(order.get("version") or 0)
                    if draft_version is None
                    else draft_version
                )
                if captured_draft_version < 0:
                    raise ValueError("Draft version cannot be negative.")
                cur.execute(
                    "SELECT COALESCE(max(revision), 0) AS revision "
                    "FROM recommendation_revisions WHERE draft_order_id = %s",
                    (draft_order_id,),
                )
                previous = cur.fetchone()
                payload = dict(recommendation)
                recommendation_id = str(payload.get("recommendation_id") or "").strip()
                if not recommendation_id:
                    recommendation_id = f"rec-{uuid.uuid4().hex}"
                payload.update(
                    {
                        "recommendation_id": recommendation_id,
                        "revision": int(previous.get("revision") or 0) + 1,
                        "draft_version": captured_draft_version,
                    }
                )
                try:
                    cur.execute(
                        "INSERT INTO recommendation_revisions "
                        "(recommendation_id, draft_order_id, revision, draft_version, payload) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (
                            recommendation_id,
                            draft_order_id,
                            payload["revision"],
                            payload["draft_version"],
                            Jsonb(payload),
                        ),
                    )
                except psycopg.errors.UniqueViolation as exc:
                    raise DraftConflict("Recommendation ID or revision is already in use.") from exc
                cur.execute(
                    "INSERT INTO recommendations (draft_order_id, payload, updated_at) "
                    "VALUES (%s, %s, now()) ON CONFLICT (draft_order_id) "
                    "DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()",
                    (draft_order_id, Jsonb(payload)),
                )
        return payload

    def get_recommendation(
        self,
        draft_order_id: str,
        recommendation_id: str,
    ) -> dict[str, Any]:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM recommendation_revisions "
                "WHERE draft_order_id = %s AND recommendation_id = %s",
                (draft_order_id, recommendation_id),
            )
            row = cur.fetchone()
        if row is None:
            raise KeyError(recommendation_id)
        return dict(row["payload"])

    def get_latest_recommendation(self, draft_order_id: str) -> dict[str, Any]:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM draft_orders WHERE draft_order_id = %s", (draft_order_id,))
            if cur.fetchone() is None:
                raise KeyError(draft_order_id)
            cur.execute(
                "SELECT payload FROM recommendation_revisions WHERE draft_order_id = %s "
                "ORDER BY revision DESC LIMIT 1",
                (draft_order_id,),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    "SELECT payload FROM recommendations WHERE draft_order_id = %s",
                    (draft_order_id,),
                )
                row = cur.fetchone()
        return dict(row["payload"]) if row and row["payload"] else {}

    def get_applied_recommendation(
        self,
        draft_order_id: str,
        recommendation_id: str,
        expected_revision: int,
        mode: str,
    ) -> dict[str, Any] | None:
        """Return an exact retry using the draft's current rows, never stored result JSON."""

        if mode not in {"add", "replace"}:
            raise ValueError("Recommendation apply mode must be add or replace.")
        with _connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    "SELECT draft_order_id, revision, mode FROM recommendation_applications "
                    "WHERE recommendation_id = %s AND draft_order_id = %s",
                    (recommendation_id, draft_order_id),
                )
                applied = cur.fetchone()
                if applied is None:
                    return None
                if (
                    int(applied["revision"]) != expected_revision
                    or applied["mode"] != mode
                ):
                    raise DraftConflict(
                        "Recommendation retry does not match the original application."
                    )
                cur.execute(
                    "SELECT draft_order_id, account_id, status, subtotal, grand_total, quote_id, "
                    "owner_email, version, revision_number, parent_draft_order_id, source_quote_id "
                    "FROM draft_orders "
                    "WHERE draft_order_id = %s FOR SHARE",
                    (draft_order_id,),
                )
                header = cur.fetchone()
                if header is None:
                    raise KeyError(draft_order_id)
                cur.execute(
                    f"SELECT {', '.join(_LINE_COLUMNS)} FROM draft_line_items "
                    "WHERE draft_order_id = %s ORDER BY position",
                    (draft_order_id,),
                )
                order = self._to_order(header, cur.fetchall())
        return {
            "order": order.model_dump(mode="json"),
            "recommendation_id": recommendation_id,
            "revision": expected_revision,
            "mode": mode,
            "already_applied": True,
        }

    def apply_recommendation(
        self,
        draft_order_id: str,
        recommendation_id: str,
        expected_revision: int,
        mode: str,
        line_items: list[DraftLineItem],
    ) -> dict[str, Any]:
        if mode not in {"add", "replace"}:
            raise ValueError("Recommendation apply mode must be add or replace.")
        with _connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    "SELECT revision, draft_version, payload FROM recommendation_revisions "
                    "WHERE recommendation_id = %s AND draft_order_id = %s FOR UPDATE",
                    (recommendation_id, draft_order_id),
                )
                recommendation = cur.fetchone()
                if recommendation is None:
                    raise KeyError(recommendation_id)
                cur.execute(
                    "SELECT draft_order_id, revision, mode FROM recommendation_applications "
                    "WHERE recommendation_id = %s",
                    (recommendation_id,),
                )
                applied = cur.fetchone()
                if applied is not None:
                    if (
                        applied["draft_order_id"] != draft_order_id
                        or int(applied["revision"]) != expected_revision
                        or applied["mode"] != mode
                    ):
                        raise DraftConflict(
                            "Recommendation retry does not match the original application."
                        )
                    cur.execute(
                        "SELECT draft_order_id, account_id, status, subtotal, grand_total, quote_id, "
                        "owner_email, version, revision_number, parent_draft_order_id, source_quote_id "
                        "FROM draft_orders "
                        "WHERE draft_order_id = %s FOR SHARE",
                        (draft_order_id,),
                    )
                    current_header = cur.fetchone()
                    if current_header is None:
                        raise KeyError(draft_order_id)
                    cur.execute(
                        f"SELECT {', '.join(_LINE_COLUMNS)} FROM draft_line_items "
                        "WHERE draft_order_id = %s ORDER BY position",
                        (draft_order_id,),
                    )
                    current_order = self._to_order(current_header, cur.fetchall())
                    return {
                        "order": current_order.model_dump(mode="json"),
                        "recommendation_id": recommendation_id,
                        "revision": expected_revision,
                        "mode": mode,
                        "already_applied": True,
                    }
                if int(recommendation["revision"]) != expected_revision:
                    raise DraftConflict("Recommendation revision is stale.")
                recommendation_payload = dict(recommendation.get("payload") or {})
                recommendation_mode = str(
                    recommendation_payload.get("apply_mode") or ""
                ).strip()
                if recommendation_mode in {"add", "replace"} and recommendation_mode != mode:
                    raise DraftConflict("Recommendation apply mode does not match.")
                cur.execute(
                    "SELECT draft_order_id, account_id, status, subtotal, grand_total, quote_id, "
                    "owner_email, version, revision_number, parent_draft_order_id, source_quote_id "
                    "FROM draft_orders "
                    "WHERE draft_order_id = %s FOR UPDATE",
                    (draft_order_id,),
                )
                header = cur.fetchone()
                if header is None:
                    raise KeyError(draft_order_id)
                if header["status"] == "quote-created":
                    raise DraftConflict(
                        "Sent quotes are immutable. Create a revision before making changes."
                    )
                current_version = int(header.get("version") or 0)
                if int(recommendation["draft_version"]) != current_version:
                    raise DraftConflict("Draft changed after this recommendation was generated.")

                cur.execute("DELETE FROM draft_line_items WHERE draft_order_id = %s", (draft_order_id,))
                self._write_lines(cur, draft_order_id, line_items)
                subtotal = round(sum((line.total_price or 0.0) for line in line_items), 2)
                cur.execute(
                    "UPDATE draft_orders SET subtotal = %s, grand_total = %s, "
                    "version = version + 1, updated_at = now() WHERE draft_order_id = %s",
                    (subtotal, subtotal, draft_order_id),
                )
                result_order = DraftOrder(
                    draft_order_id=draft_order_id,
                    account_id=header["account_id"],
                    status=header["status"],
                    line_items=line_items,
                    subtotal=subtotal,
                    grand_total=subtotal,
                    quote_id=header["quote_id"],
                    owner_email=header.get("owner_email") or "",
                    version=current_version + 1,
                    revision_number=int(header.get("revision_number") or 1),
                    parent_draft_order_id=header.get("parent_draft_order_id"),
                    source_quote_id=header.get("source_quote_id"),
                )
                result = {
                    "order": result_order.model_dump(mode="json"),
                    "recommendation_id": recommendation_id,
                    "revision": expected_revision,
                    "mode": mode,
                    "already_applied": False,
                }
                cur.execute(
                    "INSERT INTO recommendation_applications "
                    "(recommendation_id, draft_order_id, revision, mode, result) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (
                        recommendation_id,
                        draft_order_id,
                        expected_revision,
                        mode,
                        Jsonb({"applied": True}),
                    ),
                )
        return result

    # -- durable agent plans -------------------------------------------- #

    def create_plan(self, plan: QuotePlan, actor_email: str) -> QuotePlan:
        actor = actor_email.strip().casefold()
        if not actor:
            raise ValueError("Plan creator is required.")
        candidate = QuotePlan.model_validate(plan.model_dump(mode="python"))
        if candidate.revision != 1:
            raise DraftConflict("A new plan must start at revision 1.")
        if candidate.status not in ACTIVE_PLAN_STATUSES:
            raise DraftConflict("A new plan must start in an active status.")
        now = datetime.now(timezone.utc)
        candidate = candidate.model_copy(
            update={"created_by": actor, "created_at": now, "updated_at": now},
            deep=True,
        )
        try:
            with _connect() as conn:
                with conn.transaction(), conn.cursor() as cur:
                    cur.execute(
                        "SELECT account_id, version FROM draft_orders "
                        "WHERE draft_order_id = %s FOR SHARE",
                        (candidate.draft_order_id,),
                    )
                    order = cur.fetchone()
                    if order is None:
                        raise KeyError(candidate.draft_order_id)
                    if candidate.account_id != order["account_id"]:
                        raise DraftConflict("Plan account does not match its draft order.")
                    current_version = int(order.get("version") or 0)
                    if candidate.base_draft_version != current_version:
                        raise DraftConflict(
                            f"Draft version {candidate.base_draft_version} is stale; "
                            f"current version is {current_version}."
                        )
                    cur.execute(
                        "SELECT plan_id FROM agent_plans WHERE draft_order_id = %s "
                        f"AND status IN ({_ACTIVE_PLAN_STATUS_SQL}) FOR UPDATE",
                        (candidate.draft_order_id,),
                    )
                    active = cur.fetchone()
                    if active is not None:
                        raise DraftConflict(
                            f"Draft already has active plan {active['plan_id']}; "
                            "resume or cancel it first."
                        )
                    cur.execute(
                        "INSERT INTO agent_plans "
                        "(plan_id, draft_order_id, account_id, base_draft_version, revision, "
                        "status, created_by, payload, created_at, updated_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            candidate.plan_id,
                            candidate.draft_order_id,
                            candidate.account_id,
                            candidate.base_draft_version,
                            candidate.revision,
                            candidate.status.value,
                            candidate.created_by,
                            Jsonb(candidate.model_dump(mode="json")),
                            candidate.created_at,
                            candidate.updated_at,
                        ),
                    )
                    self._insert_plan_action(
                        cur,
                        AgentActionRecord(
                            plan_id=candidate.plan_id,
                            draft_order_id=candidate.draft_order_id,
                            account_id=candidate.account_id,
                            action_type="plan_created",
                            actor_email=actor,
                            plan_revision=candidate.revision,
                            draft_version=candidate.base_draft_version,
                            payload={"goal": candidate.goal},
                        ),
                    )
        except psycopg.errors.UniqueViolation as exc:
            raise DraftConflict(
                "Draft already has an active plan or the plan ID is already in use."
            ) from exc
        return candidate.model_copy(deep=True)

    def get_plan(self, plan_id: str) -> QuotePlan:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT plan_id, draft_order_id, account_id, base_draft_version, revision, "
                "status, created_by, payload, created_at, updated_at "
                "FROM agent_plans WHERE plan_id = %s",
                (plan_id,),
            )
            row = cur.fetchone()
        if row is None:
            raise KeyError(plan_id)
        return _plan_from_row(row)

    def get_active_plan(self, draft_order_id: str) -> QuotePlan | None:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM draft_orders WHERE draft_order_id = %s",
                (draft_order_id,),
            )
            if cur.fetchone() is None:
                raise KeyError(draft_order_id)
            cur.execute(
                "SELECT plan_id, draft_order_id, account_id, base_draft_version, revision, "
                "status, created_by, payload, created_at, updated_at "
                "FROM agent_plans WHERE draft_order_id = %s "
                f"AND status IN ({_ACTIVE_PLAN_STATUS_SQL}) "
                "ORDER BY updated_at DESC LIMIT 1",
                (draft_order_id,),
            )
            row = cur.fetchone()
        return _plan_from_row(row) if row is not None else None

    def update_plan(
        self,
        plan_id: str,
        expected_revision: int,
        **changes: Any,
    ) -> QuotePlan:
        with _connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    "SELECT plan_id, draft_order_id, account_id, base_draft_version, revision, "
                    "status, created_by, payload, created_at, updated_at "
                    "FROM agent_plans WHERE plan_id = %s FOR UPDATE",
                    (plan_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise KeyError(plan_id)
                try:
                    updated = apply_plan_changes(
                        _plan_from_row(row),
                        expected_revision=expected_revision,
                        **changes,
                    )
                except ValueError as exc:
                    raise DraftConflict(str(exc)) from exc
                cur.execute(
                    "UPDATE agent_plans SET revision = %s, status = %s, payload = %s, "
                    "updated_at = %s WHERE plan_id = %s AND revision = %s",
                    (
                        updated.revision,
                        updated.status.value,
                        Jsonb(updated.model_dump(mode="json")),
                        updated.updated_at,
                        plan_id,
                        expected_revision,
                    ),
                )
                if cur.rowcount != 1:
                    raise DraftConflict("Plan changed while it was being updated.")
        return updated.model_copy(deep=True)

    def append_plan_action(
        self,
        plan_id: str,
        action_type: str,
        actor_email: str,
        *,
        plan_revision: int | None = None,
        draft_version: int | None = None,
        idempotency_key: str | None = None,
        confirmation_token_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AgentActionRecord:
        normalized_idempotency = str(idempotency_key or "").strip() or None
        normalized_token_id = str(confirmation_token_id or "").strip() or None
        try:
            with _connect() as conn:
                with conn.transaction(), conn.cursor() as cur:
                    cur.execute(
                        "SELECT plan_id, draft_order_id, account_id, base_draft_version, revision, "
                        "status, created_by, payload, created_at, updated_at "
                        "FROM agent_plans WHERE plan_id = %s FOR SHARE",
                        (plan_id,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        raise KeyError(plan_id)
                    plan = _plan_from_row(row)
                    if normalized_idempotency:
                        cur.execute(
                            "SELECT action_id, plan_id, draft_order_id, account_id, action_type, "
                            "actor_email, plan_revision, draft_version, idempotency_key, "
                            "confirmation_token_id, payload, created_at FROM agent_actions "
                            "WHERE plan_id = %s AND idempotency_key = %s",
                            (plan_id, normalized_idempotency),
                        )
                        previous_row = cur.fetchone()
                        if previous_row is not None:
                            previous = _action_from_row(previous_row)
                            if (
                                previous.action_type != action_type.strip()
                                or previous.actor_email != actor_email.strip().casefold()
                                or previous.confirmation_token_id != normalized_token_id
                                or (
                                    draft_version is not None
                                    and previous.draft_version != draft_version
                                )
                            ):
                                raise DraftConflict(
                                    "Plan action retry does not match the original action."
                                )
                            return previous
                    if normalized_token_id:
                        cur.execute(
                            "SELECT action_id FROM agent_actions "
                            "WHERE confirmation_token_id = %s",
                            (normalized_token_id,),
                        )
                        if cur.fetchone() is not None:
                            raise DraftConflict("Confirmation token has already been used.")
                    trusted_revision = (
                        plan.revision if plan_revision is None else plan_revision
                    )
                    if trusted_revision != plan.revision:
                        raise DraftConflict(
                            f"Plan revision {trusted_revision} is stale; "
                            f"current revision is {plan.revision}."
                        )
                    action = AgentActionRecord(
                        plan_id=plan.plan_id,
                        draft_order_id=plan.draft_order_id,
                        account_id=plan.account_id,
                        action_type=action_type,
                        actor_email=actor_email,
                        plan_revision=trusted_revision,
                        draft_version=(
                            plan.base_draft_version
                            if draft_version is None
                            else draft_version
                        ),
                        idempotency_key=normalized_idempotency,
                        confirmation_token_id=normalized_token_id,
                        payload=copy.deepcopy(payload or {}),
                    )
                    self._insert_plan_action(cur, action)
        except psycopg.errors.UniqueViolation as exc:
            raise DraftConflict(
                "Plan action idempotency key or confirmation token is already in use."
            ) from exc
        return action.model_copy(deep=True)

    def apply_confirmed_plan_scenario(
        self,
        plan_id: str,
        *,
        expected_plan_revision: int,
        expected_draft_version: int,
        scenario_id: str,
        recommendation_id: str,
        recommendation_revision: int,
        mode: str,
        line_items: list[DraftLineItem],
        actor_email: str,
        idempotency_key: str,
        confirmation_token_id: str,
        confirmation_token: str,
        next_plan_changes: dict[str, Any],
        action_payload: dict[str, Any] | None = None,
    ) -> tuple[DraftOrder, QuotePlan, AgentActionRecord]:
        """Atomically CAS the plan and draft for a signed scenario application."""

        if mode not in {"add", "replace"}:
            raise ValueError("Recommendation apply mode must be add or replace.")
        actor = actor_email.strip().casefold()
        normalized_idempotency = idempotency_key.strip()
        normalized_token_id = confirmation_token_id.strip()
        if not actor or not normalized_idempotency or not normalized_token_id:
            raise ValueError("Confirmed plan action identity is required.")
        try:
            with _connect() as conn:
                with conn.transaction(), conn.cursor() as cur:
                    cur.execute(
                        "SELECT plan_id, draft_order_id, account_id, base_draft_version, revision, "
                        "status, created_by, payload, created_at, updated_at "
                        "FROM agent_plans WHERE plan_id = %s FOR UPDATE",
                        (plan_id,),
                    )
                    plan_row = cur.fetchone()
                    if plan_row is None:
                        raise KeyError(plan_id)
                    current = _plan_from_row(plan_row)
                    cur.execute(
                        "SELECT action_id, plan_id, draft_order_id, account_id, action_type, "
                        "actor_email, plan_revision, draft_version, idempotency_key, "
                        "confirmation_token_id, payload, created_at FROM agent_actions "
                        "WHERE plan_id = %s AND idempotency_key = %s",
                        (plan_id, normalized_idempotency),
                    )
                    previous_row = cur.fetchone()
                    if previous_row is not None:
                        previous = _action_from_row(previous_row)
                        if (
                            previous.action_type != "scenario_applied"
                            or previous.actor_email != actor
                            or previous.confirmation_token_id != normalized_token_id
                            or previous.draft_version != expected_draft_version
                        ):
                            raise DraftConflict(
                                "Plan action retry does not match the original action."
                            )
                        result_payload = previous.payload.get("result_order")
                        if not isinstance(result_payload, dict):
                            raise DraftConflict(
                                "The original plan application result is unavailable."
                            )
                        return (
                            DraftOrder.model_validate(result_payload),
                            current.model_copy(deep=True),
                            previous,
                        )
                    cur.execute(
                        "SELECT action_id FROM agent_actions WHERE confirmation_token_id = %s",
                        (normalized_token_id,),
                    )
                    if cur.fetchone() is not None:
                        raise DraftConflict("Confirmation token has already been used.")
                    if current.status != PlanStatus.READY:
                        raise DraftConflict(
                            "Only a ready quote plan can be confirmed and applied."
                        )
                    if current.revision != expected_plan_revision:
                        raise DraftConflict(
                            f"Plan revision {expected_plan_revision} is stale; "
                            f"current revision is {current.revision}."
                        )
                    if current.selected_scenario_id != scenario_id:
                        raise DraftConflict(
                            "The selected quote scenario changed before confirmation."
                        )
                    scenario = next(
                        (
                            item
                            for item in current.scenarios
                            if item.scenario_id == scenario_id
                        ),
                        None,
                    )
                    if (
                        scenario is None
                        or scenario.recommendation_id != recommendation_id
                        or scenario.recommendation_revision != recommendation_revision
                    ):
                        raise DraftConflict(
                            "The selected recommendation changed before confirmation."
                        )
                    proposal = current.action_proposal
                    if (
                        proposal is None
                        or proposal.action_type != "apply_scenario"
                        or proposal.scenario_id != scenario_id
                        or proposal.recommendation_id != recommendation_id
                        or proposal.recommendation_revision != recommendation_revision
                        or proposal.plan_revision != expected_plan_revision
                        or proposal.draft_version != expected_draft_version
                        or proposal.idempotency_key != normalized_idempotency
                        or proposal.confirmation is None
                        or proposal.confirmation.token_id != normalized_token_id
                        or proposal.confirmation.token != confirmation_token.strip()
                    ):
                        raise DraftConflict(
                            "Confirmation no longer matches the selected quote scenario."
                        )
                    cur.execute(
                        "SELECT revision, draft_version, payload "
                        "FROM recommendation_revisions "
                        "WHERE recommendation_id = %s AND draft_order_id = %s FOR SHARE",
                        (recommendation_id, current.draft_order_id),
                    )
                    recommendation = cur.fetchone()
                    if recommendation is None:
                        raise KeyError(recommendation_id)
                    recommendation_payload = dict(recommendation.get("payload") or {})
                    if (
                        int(recommendation["revision"]) != recommendation_revision
                        or int(recommendation["draft_version"])
                        != expected_draft_version
                        or str(recommendation_payload.get("apply_mode") or "add")
                        != mode
                    ):
                        raise DraftConflict(
                            "Stored plan recommendation is stale or does not match."
                        )
                    cur.execute(
                        "SELECT 1 FROM recommendation_applications "
                        "WHERE recommendation_id = %s",
                        (recommendation_id,),
                    )
                    if cur.fetchone() is not None:
                        raise DraftConflict(
                            "The plan recommendation has already been applied."
                        )
                    cur.execute(
                        "SELECT draft_order_id, account_id, status, subtotal, grand_total, quote_id, "
                        "owner_email, version, revision_number, parent_draft_order_id, source_quote_id "
                        "FROM draft_orders WHERE draft_order_id = %s FOR UPDATE",
                        (current.draft_order_id,),
                    )
                    header = cur.fetchone()
                    if header is None:
                        raise KeyError(current.draft_order_id)
                    if header["status"] == "quote-created":
                        raise DraftConflict(
                            "Generated quotes are immutable. Create a revision before making changes."
                        )
                    current_version = int(header.get("version") or 0)
                    if current_version != expected_draft_version:
                        raise DraftConflict(
                            f"Draft version {expected_draft_version} is stale; "
                            f"current version is {current_version}."
                        )
                    try:
                        updated_plan = apply_plan_changes(
                            current,
                            expected_revision=expected_plan_revision,
                            **next_plan_changes,
                        )
                    except ValueError as exc:
                        raise DraftConflict(str(exc)) from exc

                    cur.execute(
                        "DELETE FROM draft_line_items WHERE draft_order_id = %s",
                        (current.draft_order_id,),
                    )
                    self._write_lines(cur, current.draft_order_id, line_items)
                    subtotal = round(
                        sum((line.total_price or 0.0) for line in line_items),
                        2,
                    )
                    cur.execute(
                        "UPDATE draft_orders SET subtotal = %s, grand_total = %s, "
                        "version = version + 1, updated_at = now() "
                        "WHERE draft_order_id = %s AND version = %s AND status <> 'quote-created'",
                        (
                            subtotal,
                            subtotal,
                            current.draft_order_id,
                            expected_draft_version,
                        ),
                    )
                    if cur.rowcount != 1:
                        raise DraftConflict(
                            "Draft changed while the plan scenario was being applied."
                        )
                    result_order = DraftOrder(
                        draft_order_id=current.draft_order_id,
                        account_id=header["account_id"],
                        status=header["status"],
                        line_items=line_items,
                        subtotal=subtotal,
                        grand_total=subtotal,
                        quote_id=header["quote_id"],
                        owner_email=header.get("owner_email") or "",
                        version=expected_draft_version + 1,
                        revision_number=int(header.get("revision_number") or 1),
                        parent_draft_order_id=header.get("parent_draft_order_id"),
                        source_quote_id=header.get("source_quote_id"),
                    )
                    payload = copy.deepcopy(action_payload or {})
                    payload["result_order"] = result_order.model_dump(mode="json")
                    action = AgentActionRecord(
                        plan_id=current.plan_id,
                        draft_order_id=current.draft_order_id,
                        account_id=current.account_id,
                        action_type="scenario_applied",
                        actor_email=actor,
                        plan_revision=updated_plan.revision,
                        draft_version=expected_draft_version,
                        idempotency_key=normalized_idempotency,
                        confirmation_token_id=normalized_token_id,
                        payload=payload,
                    )
                    cur.execute(
                        "INSERT INTO recommendation_applications "
                        "(recommendation_id, draft_order_id, revision, mode, result) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (
                            recommendation_id,
                            current.draft_order_id,
                            recommendation_revision,
                            mode,
                            Jsonb(
                                {
                                    "result_draft_version": result_order.version,
                                    "action_id": action.action_id,
                                }
                            ),
                        ),
                    )
                    cur.execute(
                        "UPDATE agent_plans SET revision = %s, status = %s, payload = %s, "
                        "updated_at = %s WHERE plan_id = %s AND revision = %s",
                        (
                            updated_plan.revision,
                            updated_plan.status.value,
                            Jsonb(updated_plan.model_dump(mode="json")),
                            updated_plan.updated_at,
                            current.plan_id,
                            expected_plan_revision,
                        ),
                    )
                    if cur.rowcount != 1:
                        raise DraftConflict(
                            "Plan changed while its scenario was being applied."
                        )
                    self._insert_plan_action(cur, action)
        except psycopg.errors.UniqueViolation as exc:
            raise DraftConflict(
                "Plan action, confirmation token, or recommendation was already applied."
            ) from exc
        return (
            result_order.model_copy(deep=True),
            updated_plan.model_copy(deep=True),
            action.model_copy(deep=True),
        )

    def list_plan_actions(self, plan_id: str) -> list[AgentActionRecord]:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM agent_plans WHERE plan_id = %s", (plan_id,))
            if cur.fetchone() is None:
                raise KeyError(plan_id)
            cur.execute(
                "SELECT action_id, plan_id, draft_order_id, account_id, action_type, "
                "actor_email, plan_revision, draft_version, idempotency_key, "
                "confirmation_token_id, payload, created_at FROM agent_actions "
                "WHERE plan_id = %s ORDER BY created_at, action_id",
                (plan_id,),
            )
            rows = cur.fetchall()
        return [_action_from_row(row) for row in rows]

    def cancel_plan(
        self,
        plan_id: str,
        expected_revision: int,
        actor_email: str,
        reason: str = "",
    ) -> QuotePlan:
        with _connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    "SELECT plan_id, draft_order_id, account_id, base_draft_version, revision, "
                    "status, created_by, payload, created_at, updated_at "
                    "FROM agent_plans WHERE plan_id = %s FOR UPDATE",
                    (plan_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise KeyError(plan_id)
                current = _plan_from_row(row)
                if current.status == PlanStatus.CANCELLED:
                    return current
                metadata = copy.deepcopy(current.metadata)
                if reason.strip():
                    metadata["cancellation_reason"] = reason.strip()
                try:
                    updated = apply_plan_changes(
                        current,
                        expected_revision=expected_revision,
                        status=PlanStatus.CANCELLED,
                        metadata=metadata,
                    )
                except ValueError as exc:
                    raise DraftConflict(str(exc)) from exc
                cur.execute(
                    "UPDATE agent_plans SET revision = %s, status = %s, payload = %s, "
                    "updated_at = %s WHERE plan_id = %s AND revision = %s",
                    (
                        updated.revision,
                        updated.status.value,
                        Jsonb(updated.model_dump(mode="json")),
                        updated.updated_at,
                        plan_id,
                        expected_revision,
                    ),
                )
                if cur.rowcount != 1:
                    raise DraftConflict("Plan changed while it was being cancelled.")
                self._insert_plan_action(
                    cur,
                    AgentActionRecord(
                        plan_id=updated.plan_id,
                        draft_order_id=updated.draft_order_id,
                        account_id=updated.account_id,
                        action_type="plan_cancelled",
                        actor_email=actor_email,
                        plan_revision=updated.revision,
                        draft_version=updated.base_draft_version,
                        payload={"reason": reason.strip()},
                    ),
                )
        return updated.model_copy(deep=True)

    @staticmethod
    def _insert_plan_action(cur: psycopg.Cursor, action: AgentActionRecord) -> None:
        cur.execute(
            "INSERT INTO agent_actions "
            "(action_id, plan_id, draft_order_id, account_id, action_type, actor_email, "
            "plan_revision, draft_version, idempotency_key, confirmation_token_id, "
            "payload, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                action.action_id,
                action.plan_id,
                action.draft_order_id,
                action.account_id,
                action.action_type,
                action.actor_email,
                action.plan_revision,
                action.draft_version,
                action.idempotency_key,
                action.confirmation_token_id,
                Jsonb(action.payload),
                action.created_at,
            ),
        )

    def save_quote(self, quote_id: str, draft_order_id: str, account_id: str, payload: dict[str, Any]) -> None:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO quotes (quote_id, draft_order_id, account_id, payload) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (quote_id) DO UPDATE SET payload = EXCLUDED.payload",
                (quote_id, draft_order_id, account_id, Jsonb(payload)),
            )

    def commit_quote(
        self,
        draft_order_id: str,
        payload: dict[str, Any],
        *,
        expected_version: int,
        line_items: list[DraftLineItem],
    ) -> DraftOrder:
        """Persist canonical lines, version, payload, and quote status atomically."""

        quote_id = str(payload.get("quote_id") or "").strip()
        if not quote_id:
            raise ValueError("Quote payload is missing quote_id.")
        with _connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    "SELECT account_id, status, version FROM draft_orders "
                    "WHERE draft_order_id = %s FOR UPDATE",
                    (draft_order_id,),
                )
                header = cur.fetchone()
                if header is None:
                    raise KeyError(draft_order_id)
                if header["status"] == "quote-created":
                    raise DraftConflict(
                        "Generated quotes are immutable. Create a revision before making changes."
                    )
                current_version = int(header.get("version") or 0)
                if current_version != expected_version:
                    raise DraftConflict(
                        f"Draft version {expected_version} is stale; "
                        f"current version is {current_version}."
                    )
                cur.execute(
                    "DELETE FROM draft_line_items WHERE draft_order_id = %s",
                    (draft_order_id,),
                )
                self._write_lines(cur, draft_order_id, line_items)
                subtotal = round(
                    sum((line.total_price or 0.0) for line in line_items),
                    2,
                )
                cur.execute(
                    "INSERT INTO quotes (quote_id, draft_order_id, account_id, payload) "
                    "VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (quote_id) DO UPDATE SET payload = EXCLUDED.payload",
                    (
                        quote_id,
                        draft_order_id,
                        header["account_id"],
                        Jsonb(payload),
                    ),
                )
                cur.execute(
                    "UPDATE draft_orders SET subtotal = %s, grand_total = %s, "
                    "quote_id = %s, status = 'quote-created', version = version + 1, "
                    "updated_at = now() WHERE draft_order_id = %s AND version = %s "
                    "AND status <> 'quote-created'",
                    (
                        subtotal,
                        subtotal,
                        quote_id,
                        draft_order_id,
                        expected_version,
                    ),
                )
                if cur.rowcount != 1:
                    raise DraftConflict(
                        "Draft changed while the quote document was being committed."
                    )
        return self.get(draft_order_id)

    def get_quote(self, quote_id: str) -> dict[str, Any]:
        """Return an isolated copy of a generated quote's immutable payload."""

        with _connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT payload FROM quotes WHERE quote_id = %s", (quote_id,))
            row = cur.fetchone()
        if row is None:
            raise KeyError(quote_id)
        return copy.deepcopy(row["payload"])

    def get_admin_settings(self) -> CPQAdminSettings:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT payload FROM admin_settings WHERE settings_key = %s",
                ("global",),
            )
            row = cur.fetchone()
        if row is None:
            return CPQAdminSettings()
        return CPQAdminSettings.model_validate(copy.deepcopy(row["payload"]))

    def save_admin_settings(
        self,
        settings: CPQAdminSettings,
        *,
        updated_by: str,
    ) -> CPQAdminSettings:
        payload = settings.model_dump(mode="json")
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO admin_settings (settings_key, payload, updated_by) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (settings_key) DO UPDATE SET "
                "payload = EXCLUDED.payload, updated_by = EXCLUDED.updated_by, updated_at = now()",
                ("global", Jsonb(payload), updated_by.strip().casefold()),
            )
        return settings.model_copy(deep=True)

    def mark_saved(self, draft_order_id: str) -> DraftOrder:
        with _connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    "SELECT status FROM draft_orders WHERE draft_order_id = %s FOR UPDATE",
                    (draft_order_id,),
                )
                header = cur.fetchone()
                if header is None:
                    raise KeyError(draft_order_id)
                if header["status"] == "quote-created":
                    raise DraftConflict(
                        "Sent quotes are immutable. Create a revision before making changes."
                    )
                cur.execute(
                    "UPDATE draft_orders SET status = 'saved', updated_at = now() "
                    "WHERE draft_order_id = %s AND status = 'draft'",
                    (draft_order_id,),
                )
        return self.get(draft_order_id)

    def list_history(
        self,
        account_id: str,
        owner_email: str | None = None,
    ) -> list[dict[str, Any]]:
        """One row per cart (saved or quoted), newest first."""
        with _connect() as conn, conn.cursor() as cur:
            owner_clause = " AND d.owner_email = %s" if owner_email else ""
            params: tuple[Any, ...] = (
                (account_id, owner_email.strip().casefold())
                if owner_email
                else (account_id,)
            )
            cur.execute(
                "SELECT d.draft_order_id, d.status, d.grand_total, d.quote_id, d.updated_at, "
                "  d.version, d.revision_number, d.parent_draft_order_id, d.source_quote_id, "
                "  (SELECT count(*) FROM draft_line_items l WHERE l.draft_order_id = d.draft_order_id) AS line_count "
                "FROM draft_orders d "
                "WHERE d.account_id = %s AND d.status IN ('saved', 'quote-created') "
                + owner_clause
                + " ORDER BY d.updated_at DESC LIMIT 50",
                params,
            )
            return [_history_row(r) for r in cur.fetchall()]

    def delete_draft(self, draft_order_id: str) -> None:
        with _connect() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    "SELECT status FROM draft_orders WHERE draft_order_id = %s FOR UPDATE",
                    (draft_order_id,),
                )
                header = cur.fetchone()
                if header is None:
                    raise KeyError(draft_order_id)
                if header["status"] == "quote-created":
                    raise DraftConflict(
                        "Sent quotes are immutable and cannot be deleted."
                    )
                # Draft lines/conversations/recommendations cascade via FK.
                cur.execute("DELETE FROM draft_orders WHERE draft_order_id = %s", (draft_order_id,))

    # -- helpers ----------------------------------------------------------- #

    @staticmethod
    def _write_lines(cur: psycopg.Cursor, draft_order_id: str, line_items: list[DraftLineItem]) -> None:
        for position, line in enumerate(line_items):
            values = [getattr(line, col) for col in _LINE_COLUMNS]
            cur.execute(
                f"INSERT INTO draft_line_items (draft_order_id, position, {', '.join(_LINE_COLUMNS)}) "
                f"VALUES (%s, %s, {', '.join(['%s'] * len(_LINE_COLUMNS))})",
                [draft_order_id, position, *values],
            )

    @staticmethod
    def _to_order(header: dict[str, Any], lines: list[dict[str, Any]]) -> DraftOrder:
        line_items = [DraftLineItem.model_validate(_floatify(row)) for row in lines]
        return DraftOrder(
            draft_order_id=header["draft_order_id"],
            account_id=header["account_id"],
            status=header["status"],
            line_items=line_items,
            subtotal=float(header["subtotal"] or 0.0),
            grand_total=float(header["grand_total"] or 0.0),
            quote_id=header["quote_id"],
            owner_email=header.get("owner_email") or "",
            version=int(header.get("version") or 0),
            revision_number=int(header.get("revision_number") or 1),
            parent_draft_order_id=header.get("parent_draft_order_id"),
            source_quote_id=header.get("source_quote_id"),
        )

    @staticmethod
    def _recalculate(order: DraftOrder) -> None:
        subtotal = round(sum((line.total_price or 0.0) for line in order.line_items), 2)
        order.subtotal = subtotal
        order.grand_total = subtotal


def _floatify(row: dict[str, Any]) -> dict[str, Any]:
    """psycopg returns NUMERIC as Decimal; the Pydantic models expect float."""
    from decimal import Decimal

    return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in row.items()}


def _history_row(row: dict[str, Any]) -> dict[str, Any]:
    """Make a history row JSON-safe: Decimal -> float, datetime -> ISO string."""
    from datetime import datetime
    from decimal import Decimal

    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, Decimal):
            out[k] = float(v)
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _plan_from_row(row: dict[str, Any]) -> QuotePlan:
    """Rehydrate JSON payload while treating indexed columns as authoritative."""

    payload = copy.deepcopy(row.get("payload") or {})
    payload.update(
        {
            "plan_id": row["plan_id"],
            "draft_order_id": row["draft_order_id"],
            "account_id": row["account_id"],
            "base_draft_version": int(row.get("base_draft_version") or 0),
            "revision": int(row.get("revision") or 1),
            "status": row["status"],
            "created_by": row.get("created_by") or "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    )
    return QuotePlan.model_validate(payload)


def _action_from_row(row: dict[str, Any]) -> AgentActionRecord:
    return AgentActionRecord(
        action_id=row["action_id"],
        plan_id=row["plan_id"],
        draft_order_id=row["draft_order_id"],
        account_id=row["account_id"],
        action_type=row["action_type"],
        actor_email=row["actor_email"],
        plan_revision=int(row.get("plan_revision") or 1),
        draft_version=int(row.get("draft_version") or 0),
        idempotency_key=row.get("idempotency_key"),
        confirmation_token_id=row.get("confirmation_token_id"),
        payload=copy.deepcopy(row.get("payload") or {}),
        created_at=row["created_at"],
    )
