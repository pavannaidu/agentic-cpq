# Project Zero-Friction Equipment Quoting

The future-state quoting flow replaces the legacy CPQ user experience. ERP remains the customer and product master, OMS remains the equipment order and availability system, and legacy quotes are used only as historical pricing and conversion context.

Seller recommendations should be concise and action-oriented. Each quote should show recommended equipment, segment-adjusted pricing, gross margin status, approval needs, Equipment Care eligibility, and whether the customer-ready PDF can be generated.

Agentic CPQ generates the customer-ready PDF and locks the generated revision. After customer acceptance, the Salesforce equipment order link continues the existing order intake and procurement process.

When a line item is eligible for Equipment Care, sellers should keep the warranty prompt visible through quote acceptance. Services, onboarding, and warranty coverage should not be removed casually because they reduce implementation risk and post-sale friction.

Approval routing should be based on margin floors, equipment category, and quote size. If a quote crosses a threshold, the seller should see a direct approval status instead of searching through separate systems.

The demo should surface quote-readiness as compact signals: dynamic segment pricing, supplier cost check, approval path, Equipment Care attach, PDF readiness, revision control, open-quote visibility, autosave, and SSO-ready access controls.

Legacy CPQ risks should be framed as current-state problems solved by the future workflow: manual source processing, key-person dependency, standalone access without SSO, quote loss from missing autosave, and disconnected document and order processing.

Seller quoting should be presented as tier-controlled rather than unrestricted. If a seller prices equipment below a defined threshold, the quote should move to the next-level approval path before customer acceptance.

Pipeline visibility starts when the quote is created, not only after the order is committed in OMS. Generated quotes should remain visible for follow-up, conversion tracking, inventory planning, and Salesforce order-link handoff after customer acceptance.
