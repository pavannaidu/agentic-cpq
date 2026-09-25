# Agentic CPQ Demo

An agentic Configure-Price-Quote demo for dental equipment sales, built on Databricks. It turns a seller's goal into a reviewable quote, applies pricing and approval rules, and keeps the seller in control of changes.

## What it does

- **Intelligent quoting** — natural language prompts build equipment quotes (e.g., "2-operatory expansion under $80K") through an in-process OpenAI Agents SDK agent using one Genie Agent for structured data and cited seller guidance
- **Bundle recommendations** — curated operatory expansion, imaging upgrade, and reorder bundles with margin analysis
- **Cost review** — flags supplier cost differences before a quote is finalized
- **Approval routing** — automatic approval path based on margin floors, equipment category, and quote size
- **Seller/manager views** — role-sensitive UI masks supplier cost and margin from sellers
- **Customer-ready PDF** — generates a branded, paginated quote document and locks the generated revision
- **Persistent state** — Lakebase Provisioned Postgres stores drafts, conversations, and quote payloads; synced reference tables support product and account lookups. Local development can use an in-memory store.

## Architecture

```
Browser (React 19 + Vite + Databricks AppKit)
    └── Single Databricks App: FastAPI (src/app/server/)
            ├── OpenAI Agents SDK agent  (runs in-process)
            │       └── Genie Agent tool
            │               ├── Governed Unity Catalog tables
            │               └── Indexed seller-guidance DOCX files
            └── Lakebase (Postgres)  ← drafts, conversations, quotes, synced reference tables
```

Unity Catalog holds the source data: products, pricebook, supplier segment pricing, account history, installed base, order history, warranty eligibility, approval rules, and bundle components.

The agent loop runs inside the app with `openai-agents` and `AsyncDatabricksOpenAI`. The managed Genie Agent supplies SQL evidence and cited guidance; there is no separate agent app or document agent. The backend reconciles proposed quote changes against governed data and surfaces agent failures instead of fabricating content. Without a Lakebase connection, local development uses an in-memory `DraftOrderStore`.

## Repo layout

```
databricks.yml              # DAB entrypoint — dev/prod targets and variable definitions
resources/
  app.yml                   # Databricks App resource
  jobs.yml                  # Bootstrap workflow jobs
  schema.yml                # Unity Catalog schema
  synced_tables.yml         # UC-to-Lakebase reference-table sync
  volumes.yml               # Retained legacy volume declaration (unused by the app)
src/
  app/                      # Deployed Databricks App
    app.py                  # Uvicorn entry point
    app.yaml                # App env vars (agent model, Lakebase, feature flags)
    requirements.txt
    server/
      main.py               # FastAPI routes
      config.py             # Settings from env vars
      models.py             # Pydantic models
      openai_agent.py       # In-process OpenAI Agents SDK runner and tools
      databricks_api.py     # Governed quote reconciliation and follow-up helpers
      genie.py              # Genie space resolution and SQL execution
      lakebase.py           # Postgres schema and draft order persistence
      agent_plans.py        # Quote plan state and confirmation
      quote_pdf.py          # Customer-ready PDF rendering
      redaction.py          # View-level field masking
      state.py              # In-memory fallback store
    agentic_cpq_demo/       # App-local copy of shared module
    client/                 # React 19/Vite source and UI tests
    static/                 # Generated production bundle from Vite
  shared/
    agentic_cpq_demo/
      mock_engine.py        # Deterministic recommendation logic
      cpq.py                # quote document payload builder
      demo_data.py          # Products, accounts, pricing rules (source of truth)
  bootstrap/
    seed_demo_data.py       # Create UC tables, upload five reviewed guidance DOCX files
    bootstrap_agent_bricks.py  # Create/update Genie Agent with tables + guidance Volume
    grant_app_access.py     # Grant app service principal permissions
    smoke_test_stack.py     # Validate agents, access, and queries
    setup_lakebase.py       # Create database in an existing Lakebase instance
    create_genie_guidance_docs.py  # Generate DOCX from reviewed Markdown
    documents/              # Human-reviewable Markdown guidance sources
    genie_guidance_docs/    # Generated DOCX files indexed by Genie
tests/                      # pytest unit tests
```

## Deployment

### Prerequisites

- Databricks CLI and an authenticated profile for the target workspace. The existing `dev` and `prod` targets are configured for FEVM.
- An existing Unity Catalog catalog, SQL warehouse, Genie Agent, indexed guidance Volume, and Lakebase Provisioned instance/database.
- The Unity Catalog source tables referenced by `resources/synced_tables.yml` must exist before the first bundle deployment; the seed job refreshes them afterward. This bundle does not bootstrap a completely empty workspace in one pass.
- Access to the configured quote and follow-up Model Serving endpoints. The app resource also binds a stable plan-confirmation secret.

The running app can use in-memory state for local development. The deployment bundle declares Lakebase and synced-table resources, so those resources are required for a full deployment.

### Generate local artifacts

The reviewed guidance is stored as Markdown and the React client as source. Generate the DOCX files and static web assets before testing or deploying:

```bash
python -m pip install -r src/app/requirements.txt python-docx pytest
python src/bootstrap/create_genie_guidance_docs.py
npm ci --prefix src/app/client
npm run build --prefix src/app/client
```

These generated directories are intentionally ignored by Git. The bundle's
`sync.include` rules upload the built UI and DOCX files when the bundle is
synced or deployed.

### Configure `databricks.yml`

| Variable | Purpose |
|---|---|
| `catalog`, `schema` | Unity Catalog location of the demo tables; the targets keep their existing FEVM values. |
| `warehouse_id`, `genie_space_id` | Warehouse and existing Genie Agent used by the app, grants, and smoke tests. Set a separate Agent ID for production. |
| `genie_guidance_volume` | Existing managed Volume attached to the Genie Agent. |
| `lakebase_instance`, `lakebase_database` | Existing Provisioned instance and Postgres database backing the app and synced tables. |
| `agent_prefix`, `app_name_prefix` | Existing Genie Agent and app resource names. They are retained for in-place FEVM deployment. |
| `docs_volume` | Legacy bundle-managed Volume retained only to avoid destructive orphan cleanup; not used by the running app. |
| `jobs_spark_version`, `jobs_cluster_node_type` | Compute for bootstrap jobs; adjust for the target workspace. |
| `run_as_service_principal` | Required production workflow principal. |

The exact live bindings are in `databricks.yml`, `resources/app.yml`, and `src/app/app.yaml`. Do not rename their resource identities as part of a branding change: that could create a new app or detach existing resources. The app resource binds the Model Serving endpoints and plan-confirmation secret; `app.yaml` supplies the matching runtime environment variables.

This source cleanup also renames legacy demo table names and some synthetic
product identifiers. Before deploying it over an existing FEVM installation,
refresh the Unity Catalog seed data and update the bound Genie Agent's table
configuration; validate the Lakebase synced-table bindings as well. The
existing deployment is not migrated by a source-only cleanup.

### Deploy

```bash
databricks bundle validate -t dev
databricks bundle deploy -t dev
databricks bundle run seed_demo_data -t dev          # Create UC tables, upload five DOCX files
databricks bundle run bootstrap_agent_bricks -t dev  # Create/update the unified Genie Agent
databricks bundle run grant_app_access -t dev        # Grant app SP permissions
databricks bundle run smoke_test_stack -t dev        # Validate the stack
databricks bundle run seller_demo_app -t dev         # Start the app
```

For production (`-t prod`), configure a production `genie_space_id` and `run_as_service_principal` before validating or deploying. If the Genie bootstrap creates a new Agent instead of updating the bound one, set `genie_space_id` to its returned ID and redeploy before running grants or smoke tests.

## Local development

```bash
python src/app/app.py                  # FastAPI at http://localhost:8000
python -m pytest tests/ -v
npm test --prefix src/app/client
npm run typecheck --prefix src/app/client
```

The Vite build writes hashed assets into `src/app/static`, served by the same FastAPI app. Without Databricks credentials, local UI and in-memory state remain available, but live agent and Genie calls require workspace authentication.
If connecting a local run to Lakebase, set `PGDATABASE` explicitly to the
database bound by the app resource; the setup script also requires an explicit
`--database` argument.

## App configuration (`src/app/app.yaml`)

| Env var | Deployment binding | Description |
|---|---|---|
| `AGENTIC_CPQ_AGENT_PREFIX` | Existing FEVM Agent prefix | Must match the bound Genie Agent title. |
| `AGENTIC_CPQ_AGENT_MODEL` | `quote-agent-model` resource | Model for the in-process Agents SDK runner. |
| `AGENTIC_CPQ_AGENT_TIMEOUT_SECONDS` | `110` | Maximum run time, below the Apps request timeout. |
| `AGENTIC_CPQ_DEFAULT_ACCOUNT_ID` | Synthetic demo account | Initial account in the UI. |
| `AGENTIC_CPQ_MANAGER_EMAILS` | Existing FEVM allowlist | Comma-separated server-side manager authorization. |
| `AGENTIC_CPQ_FOLLOWUP_ENDPOINT` | `followup-model` resource | Model for suggested follow-up questions. |
| `AGENTIC_CPQ_FOLLOWUPS_ENABLED`, `AGENTIC_CPQ_PLANS_ENABLED` | `true` | Enable follow-up suggestions and confirmation-based quote plans. |
| `AGENTIC_CPQ_PLAN_CONFIRMATION_SECRET` | `plan-confirmation-secret` resource | Stable secret required when plans are enabled in the deployed app. |
| `AGENTIC_CPQ_GENIE_ENABLED`, `AGENTIC_CPQ_GENIE_SPACE_ID` | Enabled; bound to `seller-genie-agent` | Governed Genie Agent tool. |
| `AGENTIC_CPQ_LAKEBASE_INSTANCE` | Existing FEVM instance | Required to mint short-lived Postgres credentials. |
| `PGHOST`, `PGUSER`, `PGDATABASE`, `PGPORT`, `PGSSLMODE` | Injected by the app database resource | Connection details; the app mints a short-lived password. |

## Notes

- `src/shared/agentic_cpq_demo/` is the source of truth for mock logic and demo data. `src/app/agentic_cpq_demo/` is a local copy for deployment; keep them in sync.
- The quote ID is a SHA1 hash of order ID + serialized line items, making it deterministic across re-renders.
- The Genie Agent title is computed from prefix and target; no separate agent app is deployed.
- The configured guidance Volume must exist before the app resource is deployed. The seed job copies exactly five generated DOCX files into its root.
- The legacy `docs_volume` declaration remains for migration safety but is not seeded, attached, granted, queried, or used by the running app.
- The `prod` target intentionally has no default `genie_space_id`; configure the production Agent explicitly rather than reusing the development ID.
- Demo accounts, prices, and order figures are synthetic; product and manufacturer names do not imply endorsed pricing.
- Native Agents SDK tracing is disabled so sensitive quote inputs are not exported; application metadata remains available through the app's normal logs and response metadata.
- Bootstrap jobs use a small single-node cluster by default; override `jobs_spark_version` and `jobs_cluster_node_type` per workspace if needed.
