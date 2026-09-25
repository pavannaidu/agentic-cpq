# Agentic CPQ Demo

An agentic Configure-Price-Quote demo for dental equipment sales, built on Databricks. It turns a seller's goal into a reviewable quote, applies pricing and approval rules, and keeps the seller in control of changes.

## What it does

- **Intelligent quoting** — natural language prompts build equipment quotes (e.g., "2-operatory expansion under $80K") through an in-process OpenAI Agents SDK agent using one Genie Agent for structured data and cited seller guidance
- **Bundle recommendations** — curated operatory expansion, imaging upgrade, and reorder bundles with margin analysis
- **Reviewable plans** — the agent proposes multi-step quote changes for confirmation before applying them
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
  volumes.yml               # Legacy managed volume retained for migration safety
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
    setup_lakebase.py       # Create the Postgres database in an existing instance
    create_genie_guidance_docs.py  # Generate DOCX from reviewed Markdown
    documents/              # Human-reviewable Markdown guidance sources
    genie_guidance_docs/    # Generated DOCX files indexed by Genie
tests/                      # pytest unit tests
```

## Deployment

### Prerequisites

- Databricks CLI 1.x and an authenticated profile for the target workspace.
- An existing Unity Catalog catalog, a SQL warehouse, a Genie Agent, a managed guidance Volume, and a Lakebase Provisioned instance with the target Postgres database.
- The Unity Catalog source tables referenced by `resources/synced_tables.yml` must already exist for the first bundle deployment. The seed job refreshes them after deployment; this bundle does not bootstrap an empty workspace in one pass.
- Access to the two configured Model Serving endpoints. Change their bundle variables if those endpoints are unavailable in your workspace.
- A Databricks secret scope with two keys: one containing a stable random plan confirmation secret, and one containing the Lakebase Provisioned instance name. The deploying identity needs MANAGE on the secret scope to bind both keys to the app.

The app can use an in-memory store during local development without Lakebase. The full bundle declares Lakebase and synced-table resources, so Lakebase is required for deployment.

### Generate local artifacts

The public source includes the guidance Markdown and React source. Generate the five DOCX files and the static web build before running tests or deploying:

```bash
python -m pip install -r src/app/requirements.txt python-docx pytest
python src/bootstrap/create_genie_guidance_docs.py
npm ci --prefix src/app/client
npm run build --prefix src/app/client
python -m pytest tests/ -v
```

Both generated directories are excluded from Git. `databricks.yml` uses `sync.include` to add `src/app/static/**` and `src/bootstrap/genie_guidance_docs/*.docx` to the deployment upload after they are generated; it does not build them. Run the commands above before `bundle deploy`, or the app assets and Genie guidance documents will be missing from the deployed files.

### Configure `databricks.yml`

| Variable | Default | Description |
|---|---|---|
| `catalog` | Required | Existing Unity Catalog name |
| `schema` | `agentic_cpq_demo_dev` or `agentic_cpq_demo_prod` by target | Schema for demo tables |
| `warehouse_id` | Required | SQL warehouse ID for Genie |
| `genie_space_id` | Required | Existing Genie Agent ID used by the app, grants, and smoke tests |
| `genie_guidance_volume` | `agentic_cpq_guidance` | Existing managed Volume attached to the Genie Agent |
| `lakebase_instance` | Required | Lakebase Provisioned instance name |
| `lakebase_database` | `agentic_cpq` | Existing Postgres database inside Lakebase |
| `plan_confirmation_secret_scope` | Required | Existing Databricks secret scope holding both app runtime keys |
| `plan_confirmation_secret_key` | Required | Key containing the stable plan confirmation secret |
| `lakebase_instance_secret_key` | Required | Key whose value is exactly `lakebase_instance` |
| `quote_model_endpoint` | `databricks-gpt-5-6-terra` | Quote agent endpoint |
| `followup_model_endpoint` | `databricks-gpt-5-6-luna` | Follow-up endpoint |
| `agent_prefix` | `agentic-cpq` | Prefix for the Genie Agent title |
| `app_name_prefix` | `agentic-cpq-demo` | Prefix for the Databricks App name |
| `docs_volume` | `cpq_docs` | Legacy bundle-managed Volume retained to avoid deleting existing data |
| `jobs_spark_version`, `jobs_cluster_node_type` | `15.4.x-scala2.12`, `i3.xlarge` | Bootstrap job compute; override for your workspace |

### Deploy

Set the required bundle variables to resources in your target workspace. The value stored under `lakebase_instance_secret_key` must exactly match `lakebase_instance`; a mismatch prevents the app from minting a Postgres credential. The Genie Agent should have the title `agentic-cpq-genie-dev` for the default prefix and dev target, so the bootstrap job updates the same Agent that the app uses.

```bash
export BUNDLE_VAR_catalog="<catalog>"
export BUNDLE_VAR_warehouse_id="<warehouse-id>"
export BUNDLE_VAR_genie_space_id="<existing-genie-agent-id>"
export BUNDLE_VAR_lakebase_instance="<lakebase-instance>"
export BUNDLE_VAR_plan_confirmation_secret_scope="<secret-scope>"
export BUNDLE_VAR_plan_confirmation_secret_key="<secret-key>"
export BUNDLE_VAR_lakebase_instance_secret_key="<instance-name-secret-key>"

databricks bundle validate -t dev -p "<profile>"
databricks bundle deploy -t dev -p "<profile>"
databricks bundle run seed_demo_data -t dev -p "<profile>"
databricks bundle run bootstrap_agent_bricks -t dev -p "<profile>"
databricks bundle run grant_app_access -t dev -p "<profile>"
databricks bundle run smoke_test_stack -t dev -p "<profile>"
databricks bundle run seller_demo_app -t dev -p "<profile>"
```

For production, use `-t prod`, set a production `genie_space_id`, and set `BUNDLE_VAR_run_as_service_principal` to the production workflow principal before validating or deploying. If the Genie bootstrap job creates a new Agent instead of updating the bound one, use its returned ID as `genie_space_id` and redeploy before running the grant and smoke-test jobs.

## Local development

```bash
cd src/app
python app.py                    # FastAPI at http://localhost:8000
```

The generated web build in `src/app/static` is served by the same FastAPI app. For client-only work, run `npm test --prefix src/app/client` and `npm run typecheck --prefix src/app/client`.

Without Databricks credentials, local UI and in-memory state remain available, but live agent and Genie calls require workspace authentication.
If connecting a local run to Lakebase, set `PGDATABASE` explicitly; the setup
script likewise requires an explicit `--database` argument.

## App configuration (`src/app/app.yaml`)

| Env var | Default | Description |
|---|---|---|
| `AGENTIC_CPQ_AGENT_PREFIX` | `agentic-cpq` | Genie Agent title prefix |
| `AGENTIC_CPQ_AGENT_MODEL` | Bound to `quote_model_endpoint` | Model used by the in-process Agents SDK runner |
| `AGENTIC_CPQ_AGENT_TIMEOUT_SECONDS` | `110` | Maximum agent run time, below the Apps 120-second request limit |
| `AGENTIC_CPQ_DEFAULT_ACCOUNT_ID` | `acct-riverfront` | Prefill account in UI |
| `AGENTIC_CPQ_MANAGER_EMAILS` | Empty | Optional comma-separated allowlist for manager-only fields and views |
| `AGENTIC_CPQ_FOLLOWUP_ENDPOINT` | Bound to `followup_model_endpoint` | Model for follow-up suggestions |
| `AGENTIC_CPQ_FOLLOWUPS_ENABLED` | `true` | Enable follow-up suggestions |
| `AGENTIC_CPQ_PLANS_ENABLED` | `true` | Enable plan confirmation workflow; requires the secret binding |
| `AGENTIC_CPQ_PLAN_CONFIRMATION_SECRET` | Bound to `plan_confirmation_secret_key` | Stable secret required to confirm quote plans in the deployed app |
| `AGENTIC_CPQ_GENIE_ENABLED` | `true` | Enable Genie SQL agent |
| `AGENTIC_CPQ_GENIE_SPACE_ID` | Bound to `genie_space_id` | Genie Agent resource binding |
| `AGENTIC_CPQ_LAKEBASE_INSTANCE` | Bound to `lakebase_instance_secret_key` | Provisioned instance name used to mint Postgres credentials |
| `PGHOST`, `PGUSER`, `PGDATABASE`, `PGPORT`, `PGSSLMODE` | Injected by the app database resource | Postgres connection details; the app mints a short-lived password |

## Notes

- `src/shared/agentic_cpq_demo/` is the source of truth for mock logic and demo data. `src/app/agentic_cpq_demo/` is a local copy for deployment; keep them in sync.
- The quote ID is a SHA1 hash of order ID + serialized line items, making it deterministic across re-renders.
- The Genie Agent title is computed from prefix and target; no separate agent app is deployed.
- The guidance Volume must exist before the app resource is deployed. The seed job copies exactly five generated DOCX files into its root.
- The `docs_volume` declaration remains to protect a legacy bundle-managed Volume from deployment cleanup. The running app does not use it.
- Neither target has a default `genie_space_id`; provide an Agent ID for each workspace.
- Demo accounts, prices, and order figures are synthetic; product and manufacturer names do not imply endorsed pricing.
- Native Agents SDK tracing is disabled so sensitive quote inputs are not exported; application metadata remains available through the app's normal logs and response metadata.
- Bootstrap jobs use a small single-node cluster by default; override `jobs_spark_version` and `jobs_cluster_node_type` per workspace if needed.
