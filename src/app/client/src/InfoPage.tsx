import { Button } from "@databricks/appkit-ui/react";
import {
  ArrowDown,
  ArrowLeft,
  ArrowLeftRight,
  ArrowRight,
  BookOpenCheck,
  Bot,
  BrainCircuit,
  Database,
  FileCheck2,
  Globe2,
  Layers3,
  Search,
  ShieldCheck,
  TableProperties,
  Zap,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

type ValueItem = {
  title: string;
  description: string;
  icon: LucideIcon;
  tone: "primary" | "success" | "warning";
};

const VALUE_ITEMS: ValueItem[] = [
  {
    title: "Build with context",
    description: "Use the selected account, product catalog, installed base, order history, and reviewed seller guidance.",
    icon: Zap,
    tone: "primary",
  },
  {
    title: "Protect commercial truth",
    description: "Reconcile segment pricing, supplier cost, margin, Equipment Care, discounts, and approval requirements.",
    icon: ShieldCheck,
    tone: "success",
  },
  {
    title: "Finish in one workflow",
    description: "Carry the draft through role-aware review, quote history, revision control, and a customer-ready PDF.",
    icon: FileCheck2,
    tone: "warning",
  },
];

export function InfoPage() {
  return (
    <div className="info-page">
      <a className="info-skip-link" href="#info-content">Skip to content</a>

      <header className="info-header">
        <a className="info-brand" href="/" aria-label="Agentic CPQ workspace">
          <span className="info-brand-mark" aria-hidden="true"><Bot /></span>
          <span className="info-brand-copy">
            <strong>Agentic CPQ</strong>
            <small>on Databricks</small>
          </span>
        </a>
        <Button variant="outline" size="sm" asChild>
          <a href="/"><ArrowLeft aria-hidden="true" /> Quote workspace</a>
        </Button>
      </header>

      <main id="info-content">
        <section className="info-intro" aria-labelledby="info-title">
          <div className="info-hero-copy">
            <p className="info-kicker">How it works</p>
            <h1 id="info-title">Agentic CPQ on Databricks</h1>
            <p className="info-lede">From a natural-language brief to a governed, review-ready quote in one seller workspace.</p>
            <p className="info-thesis">
              The agent proposes SKUs, quantities, and rationale. Governed data and server-side rules stay authoritative for pricing, margin, Equipment Care, discounts, and approvals.
            </p>
          </div>

          <div className="info-value-rail" aria-label="Business value">
            {VALUE_ITEMS.map(({ title, description, icon: Icon, tone }) => (
              <article className="info-value-item" data-tone={tone} key={title}>
                <span className="info-value-icon" aria-hidden="true"><Icon /></span>
                <div>
                  <h2>{title}</h2>
                  <p>{description}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="info-architecture" aria-labelledby="architecture-title">
          <div className="info-section-inner">
            <div className="info-section-heading">
              <p className="info-kicker">System architecture</p>
              <h2 id="architecture-title">How the components work together</h2>
              <p>The agent coordinates governed commercial facts, cited public research, deterministic CPQ controls, and durable workflow state.</p>
            </div>

            <figure className="info-system-map" aria-label="Agentic CPQ connected system graph">
              <figcaption className="info-map-caption">
                <div>
                  <span>Quote control plane</span>
                  <strong>Connected system graph</strong>
                </div>
                <div className="info-map-legend" aria-label="Architecture data boundaries">
                  <span data-kind="governed"><i aria-hidden="true" />Governed truth</span>
                  <span data-kind="public"><i aria-hidden="true" />Public research</span>
                  <span data-kind="state"><i aria-hidden="true" />Workflow state</span>
                </div>
              </figcaption>

              <div className="info-core-flow" aria-label="Primary quote path">
                <article className="info-core-node" data-kind="workspace">
                  <span className="info-core-icon" aria-hidden="true"><Layers3 /></span>
                  <div>
                    <h3>Seller workspace</h3>
                    <p>Account, brief, and live draft</p>
                    <small>React + Databricks AppKit</small>
                  </div>
                </article>

                <div className="info-core-edge" aria-label="Prompt + current draft">
                  <span>Prompt + draft</span>
                  <ArrowRight aria-hidden="true" />
                </div>

                <article className="info-core-node info-core-agent" data-kind="agent">
                  <span className="info-core-icon" aria-hidden="true"><Bot /></span>
                  <div>
                    <h3>Agent runtime</h3>
                    <p>Plans, reasons, and calls tools</p>
                    <small>OpenAI Agents SDK + Model Serving</small>
                  </div>
                </article>

                <div className="info-core-edge" aria-label="Proposed SKUs + quantities">
                  <span>Proposed configuration</span>
                  <ArrowRight aria-hidden="true" />
                </div>

                <article className="info-core-node" data-kind="control">
                  <span className="info-core-icon" aria-hidden="true"><ShieldCheck /></span>
                  <div>
                    <h3>CPQ validation</h3>
                    <p>Reconciles quote economics</p>
                    <small>SKU · price · margin · care · approvals</small>
                  </div>
                </article>

                <div className="info-core-edge" aria-label="Validated quote update">
                  <span>Validated quote</span>
                  <ArrowRight aria-hidden="true" />
                </div>

                <article className="info-core-node" data-kind="output">
                  <span className="info-core-icon" aria-hidden="true"><FileCheck2 /></span>
                  <div>
                    <h3>Review-ready quote</h3>
                    <p>Returns evidence and status</p>
                    <small>Role-aware review · PDF · history</small>
                  </div>
                </article>
              </div>

              <div className="info-return-path">
                <ArrowLeft aria-hidden="true" />
                <span>Draft, evidence, and approval status return to the seller workspace</span>
              </div>

              <section className="info-service-plane" aria-labelledby="agent-connections-title">
                <div className="info-service-plane-heading">
                  <strong id="agent-connections-title">Connected services</strong>
                  <span>The runtime calls the right boundary for each job.</span>
                </div>

                <div className="info-service-rail" aria-hidden="true">
                  <span />
                  <i className="info-validation-state-link" />
                </div>

                <div className="info-service-grid">
                  <section className="info-service-branch" data-kind="governed" aria-labelledby="genie-branch-title">
                    <div className="info-service-port" aria-label="Agent runtime to Genie Agent">
                      <ArrowDown aria-hidden="true" />
                      <span>Agent ↔ governed facts</span>
                    </div>
                    <div className="info-service-heading">
                      <span className="info-service-icon" aria-hidden="true"><BrainCircuit /></span>
                      <div><p>Governed retrieval</p><h3 id="genie-branch-title">Genie Agent</h3></div>
                    </div>
                    <p className="info-service-summary">Resolves account, catalog, and CPQ questions against approved data.</p>
                    <div className="info-service-exchange" aria-label="Genie Agent to governed sources">
                      <ArrowLeftRight aria-hidden="true" />
                      <span>SQL + retrieval · cited evidence</span>
                    </div>
                    <div className="info-service-resources" aria-label="Governed sources">
                      <div className="info-resource-row">
                        <TableProperties aria-hidden="true" />
                        <span><strong>Unity Catalog</strong><small>Accounts, products, pricing, and rules</small></span>
                      </div>
                      <div className="info-resource-row">
                        <BookOpenCheck aria-hidden="true" />
                        <span><strong>cpq_guidance Volume</strong><small>Cited seller playbooks</small></span>
                      </div>
                    </div>
                  </section>

                  <section className="info-service-branch" data-kind="public" aria-labelledby="web-branch-title">
                    <div className="info-service-port" aria-label="Agent runtime to Web Search">
                      <ArrowDown aria-hidden="true" />
                      <span>Agent ↔ open research</span>
                    </div>
                    <div className="info-service-heading">
                      <span className="info-service-icon" aria-hidden="true"><Search /></span>
                      <div><p>Research tool</p><h3 id="web-branch-title">Web Search</h3></div>
                    </div>
                    <p className="info-service-summary">Explores current markets, competitors, and trends through system.ai.web_search.</p>
                    <div className="info-service-exchange" aria-label="Web Search to public web sources">
                      <ArrowLeftRight aria-hidden="true" />
                      <span>Search queries · bounded citations</span>
                    </div>
                    <div className="info-service-resources">
                      <div className="info-resource-row">
                        <Globe2 aria-hidden="true" />
                        <span><strong role="heading" aria-level={4}>Cited public web</strong><small>Fresh context for rationale and discovery</small></span>
                      </div>
                      <div className="info-advisory-boundary">
                        <ShieldCheck aria-hidden="true" />
                        <span><strong>Advisory only</strong><small>Cannot authorize pricing, SKUs, accounts, or approvals</small></span>
                      </div>
                    </div>
                  </section>

                  <section className="info-service-branch" data-kind="state" aria-labelledby="lakebase-branch-title">
                    <div className="info-service-port" aria-label="Agent runtime and CPQ validation to Lakebase">
                      <ArrowDown aria-hidden="true" />
                      <span>Agent + validation ↔ state</span>
                    </div>
                    <div className="info-service-heading">
                      <span className="info-service-icon" aria-hidden="true"><Database /></span>
                      <div><p>Managed Postgres</p><h3 id="lakebase-branch-title">Lakebase</h3></div>
                    </div>
                    <p className="info-service-summary">Keeps the conversation and quote lifecycle continuous across every turn.</p>
                    <div className="info-service-exchange" aria-label="Lakebase persisted quote lifecycle">
                      <ArrowLeftRight aria-hidden="true" />
                      <span>Persist · retrieve</span>
                    </div>
                    <div className="info-service-resources info-state-resources" aria-label="Persisted quote lifecycle">
                      <span>Draft</span><span>Conversation</span><span>Recommendation</span><span>Quote</span>
                    </div>
                  </section>
                </div>
              </section>

              <div className="info-trust-strip">
                <ShieldCheck aria-hidden="true" />
                <span><strong>Commercial truth stays governed.</strong> Only approved data and server-side validation can set quote economics or approvals.</span>
              </div>
            </figure>
          </div>
        </section>

        <section className="info-principle" aria-label="System trust model">
          <div className="info-principle-statement">
            <span>Agent proposes.</span>
            <span>Governed data prices.</span>
            <span>Server validates.</span>
          </div>
          <p>Failures surface explicitly, and role-aware controls keep sensitive economics in authorized views.</p>
        </section>
      </main>

      <footer className="info-footer">Powered by <strong>Databricks</strong></footer>
    </div>
  );
}
