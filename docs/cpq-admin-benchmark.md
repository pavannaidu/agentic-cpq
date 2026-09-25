# CPQ Admin Benchmark

## Executive takeaway

Salesforce, Oracle, Conga, and DealHub converge on the same administrative backbone: configurable quote documents, condition-driven pricing and product behavior, approval guardrails, localization, and governed history. The mature products differ mainly in depth—complex approval graphs, broad rule languages, multilingual authoring, and field-level audit—not in the basic control categories.

For this seller demo, the right target is a **lite admin** that makes the common controls safe and visible without reproducing an enterprise CPQ rule engine. The minimum useful product is a versioned, admin-only configuration workspace with live quote preview, reusable terms, simple commercial and product rules, locale settings, and draft/publish/rollback governance.

> **Evidence boundary:** This comparison uses selected first-party product documentation accessed September 10, 2026. “Not established” means the capability was not verified in the selected sources; it does not mean the vendor lacks it.

## Feature matrix

| Capability | Salesforce CPQ | Oracle CPQ | Conga CPQ | DealHub |
|---|---|---|---|---|
| **Quote and document design** | Reusable template-content library; admins set section order, margins, page breaks, styling, and conditional printing.[^1][^2] | Drag-and-drop templates can conditionally show transaction content and control page orientation, columns, margins, backgrounds, headers, footers, and output format.[^9][^10] | Admins govern output formats and choose default or query-filtered proposal templates.[^18] | An API Playbook is associated with an output-document template; version-specific exports include proposal-document and synchronization metadata.[^21][^22] |
| **Terms and conditional content** | Term Conditions support all/any/custom Boolean logic. Locked terms cannot be edited by sellers; changing an unlocked term creates a quote-specific copy.[^3] | Conditional document content and translated elements are supported; locked reusable term blocks were not established in the selected sources.[^9][^11] | Centrally configured templates are supported; locked reusable term blocks were not established in the selected source.[^18] | API Playbook template association and version-specific configuration exports are supported; locked reusable term blocks were not established in the selected sources.[^21][^22] |
| **Approval routing** | Salesforce Advanced Approvals combines quote/product conditions with approvers, supports serial and parallel paths, and can require unanimous approval from a group.[^4] | Approval reasons can trigger serial, parallel, or combined multi-tier sequences, including delegated approvers.[^12] | Approvals can run at header, line, or both levels, with sequential/parallel dependencies and unanimous, majority, percentage, or quorum decisions.[^16] | A Version contains approval workflows alongside pricing and discount policy, so the workflow travels with governed configuration.[^19] |
| **Pricing controls** | Price Conditions form the IF test and Price Actions update quote, group, or line fields.[^5] | Pricing rules support always-on, customer-specific, simple, and advanced conditions, with status/effectivity and multi-currency price models.[^14] | The selected evidence establishes detailed pricing-change audit, not the full authoring model.[^17] | Ordered pricing rules run sequentially; pricing rules and discount policies are governed within a Version.[^19][^20] |
| **Product and configuration rules** | Alert, Validation, Selection, and Filter rules can block invalid combinations or automatically add, remove, or hide products.[^6] | Rules can recommend items, hide attributes, prevent incompatible selections, and execute prioritized configuration actions.[^13] | Not established in the selected source set. | Assignment rules can add products automatically from conditions and set factors such as quantity or duration.[^20] |
| **Localization** | Admins can translate quote-template variables and select the document language at generation time.[^8] | One-template-per-language and multilingual-template models are supported, with translated-element fallback and configurable date/currency formatting.[^10][^11] | Not established in the selected source set. | Not established in the selected source set. |
| **Governance, versioning, and audit** | Generated Quote Document records preserve generation time, version number, and viewable prior proposal versions; configuration rollback was not established.[^7] | Pricing changes can record who changed values and retain audit history for SOX-oriented controls.[^15] | Field Change History records prior/new value, actor, and timestamp across pricing and quote objects and exports to CSV or Excel.[^17] | Draft configuration is editable, only one Active version is read-only, Deactivated versions remain retrievable, and Playbooks can be exported for a specific Version.[^19][^21] |

## What the benchmark implies

The shared baseline is not a free-form page builder. It is **governed configuration**: administrators define reusable presentation and commercial policies, sellers consume the active version, and generated quotes retain enough context to explain what happened later.

The enterprise products then add depth in four places:

- richer approval graphs, including parallel paths, delegation, and quorum decisions;
- broader condition/action languages for pricing and configuration;
- sophisticated multilingual document authoring; and
- granular, exportable change history across many business objects.

Those are credible expansion paths, but they are not prerequisites for a useful first admin experience.

## Recommended lite-admin MVP

| Admin area | Ship in the MVP | Deliberate boundary |
|---|---|---|
| **Quote design** | Logo, brand colors, page size, section order and visibility, pricing-column toggles, and a live preview using representative quote data. | One base layout; no unrestricted HTML, CSS, or WYSIWYG authoring. |
| **Terms** | Reusable term blocks, seller-edit lock, simple field/operator/value inclusion conditions, effective dates, and locale variants. | No nested clause hierarchy or arbitrary Boolean expression builder. |
| **Commercial controls** | Permission to edit net price, discount thresholds, approval reason, and a basic serial approval chain. | No parallel paths, delegation, quorum rules, or account/product-specific approval matrices. |
| **Product rules** | Requires, excludes, and auto-add relationships; minimum/maximum quantity; default care-plan attachment. | No arbitrary rule DSL, scripting, or full bill-of-materials configurator. |
| **Localization** | Quote currency and locale, date/number formats, and locale-specific template and term text. | No translation workflow, translation memory, or per-market template inheritance. |
| **Governance** | Admin-only access; draft, preview, publish, actor/timestamp audit, immutable published versions, and rollback. | Audit published snapshots rather than every keystroke; keep one active configuration. |

### Required behavior

1. **Preview and output use the same renderer.** The admin preview must match the generated quote PDF for the same sample data.
2. **Publishing is atomic.** Sellers see either the old complete version or the new complete version, never a partially saved configuration.
3. **Every generated quote records its configuration version.** Historical output remains explainable after settings change.
4. **Rules are typed and validated.** The UI offers a finite set of supported fields, operators, and actions, rejects circular product dependencies, and shows rule priority.
5. **Rollback creates a new governed version.** It restores a prior snapshot without erasing the audit trail.

### Build order

1. Versioned configuration shell, roles, publish flow, and audit metadata.
2. Quote design, terms, and preview because they make the admin surface immediately demonstrable.
3. Pricing permissions, discount approval, and the finite product-rule set.
4. Locale variants after the underlying template and term models are stable.

## Sources

[^1]: Salesforce, “[Structure a Customized Quote Template](https://trailhead.salesforce.com/content/learn/modules/quote-templates-in-salesforce-cpq/structure-a-customized-quote-template).” Trailhead. Undated; accessed September 10, 2026.
[^2]: Salesforce, “[Add Conditions to Template Sections](https://trailhead.salesforce.com/content/learn/modules/quote-templates-in-salesforce-cpq/add-conditions-to-template-sections).” Trailhead. Undated; accessed September 10, 2026.
[^3]: Salesforce, “[Show Dynamic Quote Terms](https://trailhead.salesforce.com/content/learn/modules/quote-templates-in-salesforce-cpq/show-dynamic-quote-terms).” Trailhead. Undated; accessed September 10, 2026.
[^4]: Salesforce, “[Discover Advanced Approvals](https://trailhead.salesforce.com/content/learn/modules/advanced-approvals-for-admins/discover-advanced-approvals).” Trailhead. Undated; accessed September 10, 2026.
[^5]: Salesforce, “[Get Started with Salesforce CPQ Price Rules](https://trailhead.salesforce.com/content/learn/modules/price-rules-in-salesforce-cpq/get-started-with-salesforce-cpq-price-rules).” Trailhead. Undated; accessed September 10, 2026.
[^6]: Salesforce, “[Get Started with Product Rules](https://trailhead.salesforce.com/content/learn/modules/product-rules-in-salesforce-cpq/get-started-with-product-rules).” Trailhead. Undated; accessed September 10, 2026.
[^7]: Salesforce, “[Get Started with Quote Templates in Salesforce CPQ](https://trailhead.salesforce.com/content/learn/modules/quote-templates-in-salesforce-cpq/get-started-with-quote-templates-in-salesforce-cpq).” Trailhead. Undated; accessed September 10, 2026.
[^8]: Salesforce, “[Translate CPQ Quote Template Content](https://help.salesforce.com/s/articleView?id=sales.cpq_translate_template_content.htm&language=en_US&type=5).” Salesforce Help. Undated; accessed September 10, 2026.
[^9]: Oracle, “[Document Designer Overview](https://help-cxsales.oraclecloud.com/cpq/Content/DocumentDesigner/Document_Designer_Overview.htm).” Oracle CPQ Online Help. No page date; accessed September 10, 2026.
[^10]: Oracle, “[Document Designer Layouts](https://help-cxsales.oraclecloud.com/cpq/Content/DocumentDesigner/Document_Designer_Layouts.htm).” Oracle CPQ Online Help. No page date; accessed September 10, 2026.
[^11]: Oracle, “[Document Designer Languages and Translations](https://help-cxsales.oraclecloud.com/cpq/Content/DocumentDesigner/Document_Designer_Languages.htm).” Oracle CPQ Online Help. No page date; accessed September 10, 2026.
[^12]: Oracle, “[Approval Sequences Overview](https://help-cxsales.oraclecloud.com/cpq/Content/Approval_Sequences/Approval_Sequences_Overview.htm).” Oracle CPQ Online Help. No page date; accessed September 10, 2026.
[^13]: Oracle, “[Configuration Rule Overview](https://help-cxsales.oraclecloud.com/cpq/Content/Configuration/Rules/ConfigurationRules.htm).” Oracle CPQ Online Help. No page date; accessed September 10, 2026.
[^14]: Oracle, “[Pricing Rules](https://help-cxsales.oraclecloud.com/cpq/Content/Manage_Pricing/pricingRules.htm).” Oracle CPQ Online Help. No page date; accessed September 10, 2026.
[^15]: Oracle, “[Sarbanes–Oxley Data Compliance in CPQ Pricing](https://docs.oracle.com/en/cloud/saas/readiness/sales/24c/scpq-24c/24C-cpq-wn-F33832.htm).” Oracle Configure, Price, Quote Cloud 24C What’s New. August 28, 2024; accessed September 10, 2026.
[^16]: Conga, “[Approval Process Overview](https://documentation.conga.com/en/cpq-for-advantage-platform/current/cpq-for-advantage-platform-implementers-guide/approval-process-overview).” Updated September 8, 2026; accessed September 10, 2026.
[^17]: Conga, “[Conducting an End-to-End Pricing Audit Using Field Change History](https://documentation.conga.com/en/cpq-for-advantage-platform/current/cpq-for-users/viewing-quote-details/conducting-an-end-to-end-pricing-audit-using-field-change-history).” Updated September 8, 2026; accessed September 10, 2026.
[^18]: Conga, “[Configuring Document Generation for Quote](https://documentation.conga.com/en/cpq-for-salesforce/current/cpq-for-administrators/managing-quotes-or-proposals/configuring-document-generation-for-quote).” Updated May 29, 2026; accessed September 10, 2026.
[^19]: DealHub, “[Version API Overview](https://developers.dealhub.io/docs/version-api-overview).” Updated June 11, 2026; accessed September 10, 2026.
[^20]: DealHub, “[Update the Product Catalog](https://developers.dealhub.io/docs/updating-the-product-catalog).” Updated March 6, 2026; accessed September 10, 2026.
[^21]: DealHub, “[Export Playbook Data](https://developers.dealhub.io/docs/exporting-playbook-data).” Updated June 11, 2026; accessed September 10, 2026.
[^22]: DealHub, “[Creating an API Playbook](https://developers.dealhub.io/docs/creating-an-api-playbook).” Updated January 19, 2026; accessed September 10, 2026.
