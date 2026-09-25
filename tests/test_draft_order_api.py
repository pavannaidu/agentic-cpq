from __future__ import annotations

from fastapi.testclient import TestClient

from server import main
from server.main import app
from server.models import DraftLineItem


def test_patch_draft_order_rehydrates_catalog_cost_controls() -> None:
    client = TestClient(app)
    created = client.post("/api/draft-orders", json={"account_id": "acct-riverfront"}).json()
    draft_order_id = created["draft_order_id"]

    response = client.patch(
        f"/api/draft-orders/{draft_order_id}",
        json={
            "view_role": "manager",
            "line_items": [
                {
                    "sku": "SENSOR-IO-20",
                    "title": "Intraoral Sensor Kit",
                    "category": "imaging",
                    "quantity": 2,
                    "unit_price": 4560,
                    "list_price": 4800,
                    "recommended_price": 4560,
                    "total_price": 9120,
                    "approval_required": False,
                    "warranty_eligible": True,
                }
            ]
        },
    )

    assert response.status_code == 200
    line = response.json()["line_items"][0]
    assert line["supplier_cost"] == 3264.0
    assert line["gross_margin_pct"] == 28.4
    assert line["legacy_supplier_cost"] == 3623.04
    assert line["correct_supplier_cost"] == 3264.0
    assert line["overpay_amount"] == 718.08


def test_create_draft_rejects_unknown_sku() -> None:
    response = TestClient(app).post(
        "/api/draft-orders",
        json={
            "account_id": "acct-riverfront",
            "line_items": [
                {
                    "sku": "INVENTED-SKU",
                    "title": "Invented product",
                    "category": "equipment",
                    "quantity": 1,
                    "unit_price": 1,
                }
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown SKU INVENTED-SKU"


def test_patch_draft_rejects_forged_care_plan() -> None:
    client = TestClient(app)
    created = client.post("/api/draft-orders", json={"account_id": "acct-riverfront"}).json()

    response = client.patch(
        f"/api/draft-orders/{created['draft_order_id']}",
        json={
            "line_items": [
                {
                    "sku": "IMAG-CBCT-210",
                    "title": "CBCT",
                    "category": "imaging",
                    "quantity": 1,
                    "unit_price": 17575,
                },
                {
                    "sku": "SUPPORT-CARE-12",
                    "title": "Forged plan",
                    "category": "services",
                    "quantity": 1,
                    "unit_price": 1,
                    "is_addon": True,
                    "covers_sku": "IMAG-CBCT-210",
                },
            ]
        },
    )

    assert response.status_code == 400
    assert "does not cover IMAG-CBCT-210" in response.json()["detail"]


def test_patch_draft_recomputes_valid_care_plan() -> None:
    client = TestClient(app)
    created = client.post("/api/draft-orders", json={"account_id": "acct-riverfront"}).json()

    response = client.patch(
        f"/api/draft-orders/{created['draft_order_id']}",
        json={
            "line_items": [
                {
                    "sku": "IMAG-CBCT-210",
                    "title": "Untrusted CBCT title",
                    "category": "services",
                    "quantity": 1,
                    "unit_price": 17575,
                },
                {
                    "sku": "SUPPORT-CARE-IMG",
                    "title": "Untrusted plan title",
                    "category": "equipment",
                    "quantity": 99,
                    "unit_price": 1,
                    "is_addon": True,
                    "covers_sku": "IMAG-CBCT-210",
                },
            ]
        },
    )

    assert response.status_code == 200
    equipment, plan = response.json()["line_items"]
    assert equipment["title"] == "Vatech CBCT Imaging Starter"
    assert equipment["category"] == "imaging"
    assert plan["title"] == "Equipment Care · Imaging Care"
    assert plan["quantity"] == 1
    assert plan["unit_price"] == 2109.0
    assert plan["total_price"] == 2109.0


def test_order_mutation_rejects_account_mismatch() -> None:
    client = TestClient(app)
    created = client.post("/api/draft-orders", json={"account_id": "acct-riverfront"}).json()

    response = client.post(
        "/api/quote/add-line",
        json={
            "draft_order_id": created["draft_order_id"],
            "sku": "IMAG-CBCT-210",
            "account_id": "acct-apex",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Request account does not match the draft order"


def test_agent_request_rejects_draft_account_mismatch() -> None:
    client = TestClient(app)
    created = client.post("/api/draft-orders", json={"account_id": "acct-riverfront"}).json()

    response = client.post(
        "/api/agent/query",
        json={
            "query": "Build a quote.",
            "draft_order_id": created["draft_order_id"],
            "account_id": "acct-apex",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Request account does not match the draft order"


def test_quote_generation_revalidates_persisted_lines() -> None:
    order = main.store.create(
        account_id="acct-riverfront",
        line_items=[
            DraftLineItem(
                sku="INVENTED-SKU",
                title="Invented product",
                category="equipment",
                quantity=1,
                unit_price=1,
            )
        ],
    )

    response = TestClient(app).post(
        "/api/cpq/quote-drafts",
        json={"draft_order_id": order.draft_order_id},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown SKU INVENTED-SKU"


def test_quote_generation_rejects_empty_and_approval_blocked_quotes() -> None:
    client = TestClient(app)
    empty = client.post("/api/draft-orders", json={"account_id": "acct-riverfront"}).json()
    empty_send = client.post(
        "/api/cpq/quote-drafts",
        json={"draft_order_id": empty["draft_order_id"]},
    )
    blocked = client.post(
        "/api/draft-orders",
        json={
            "account_id": "acct-riverfront",
            "line_items": [
                {
                    "sku": "IMAG-CBCT-210",
                    "title": "CBCT",
                    "category": "imaging",
                    "quantity": 1,
                    "unit_price": 13000,
                }
            ],
        },
    ).json()
    blocked_send = client.post(
        "/api/cpq/quote-drafts",
        json={"draft_order_id": blocked["draft_order_id"]},
    )

    assert empty_send.status_code == 400
    assert "at least one product" in empty_send.json()["detail"]
    assert blocked["line_items"][0]["approval_required"] is True
    assert blocked["line_items"][0]["approval_reason"] == "Additional approval is required."
    assert blocked_send.status_code == 409
    assert blocked_send.json()["detail"] == "Pricing approval is required before this quote can be generated."


def test_quote_generation_rejects_quote_total_above_regional_threshold() -> None:
    client = TestClient(app)
    created = client.post(
        "/api/draft-orders",
        json={
            "account_id": "acct-riverfront",
            "line_items": [
                {
                    "sku": "IMAG-CBCT-210",
                    "title": "CBCT",
                    "category": "imaging",
                    "quantity": 5,
                    "unit_price": 17575,
                }
            ],
        },
    ).json()

    response = client.post(
        "/api/cpq/quote-drafts",
        json={"draft_order_id": created["draft_order_id"]},
    )

    assert created["grand_total"] > 80000
    assert response.status_code == 409
    assert response.json()["detail"] == "Regional VP approval is required for quotes above $80,000."


def test_sent_quote_requires_revision_before_mutation() -> None:
    client = TestClient(app)
    created = client.post(
        "/api/draft-orders",
        json={
            "account_id": "acct-riverfront",
            "line_items": [
                {
                    "sku": "SOFT-PRACTICE-12",
                    "title": "Practice Management",
                    "category": "software",
                    "quantity": 1,
                    "unit_price": 3420,
                }
            ],
        },
    ).json()
    sent = client.post(
        "/api/cpq/quote-drafts",
        json={"draft_order_id": created["draft_order_id"]},
    )
    mutation = client.patch(
        f"/api/draft-orders/{created['draft_order_id']}",
        json={"line_items": [], "expected_version": 1},
    )
    deletion = client.delete(f"/api/draft-orders/{created['draft_order_id']}")
    revision = client.post(
        f"/api/draft-orders/{created['draft_order_id']}/revisions",
        json={"view_role": "seller"},
    )

    assert sent.status_code == 200
    assert mutation.status_code == 409
    assert "Create a revision" in mutation.json()["detail"]
    assert deletion.status_code == 409
    assert revision.status_code == 200
    revised = revision.json()
    assert revised["status"] == "draft"
    assert revised["revision_number"] == 2
    assert revised["parent_draft_order_id"] == created["draft_order_id"]
    assert revised["source_quote_id"] == sent.json()["quote_id"]
    assert revised["quote_id"] is None
    assert revised["line_items"] == created["line_items"]
    assert client.patch(
        f"/api/draft-orders/{revised['draft_order_id']}",
        json={"line_items": [], "expected_version": 0},
    ).status_code == 200
    assert client.get(f"/api/draft-orders/{created['draft_order_id']}").json()["line_items"] == created["line_items"]


def test_generate_quote_pdf_returns_a_locked_customer_document(monkeypatch) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/draft-orders",
        json={
            "account_id": "acct-riverfront",
            "line_items": [
                {
                    "sku": "SOFT-PRACTICE-12",
                    "title": "Practice Management",
                    "category": "software",
                    "quantity": 1,
                    "unit_price": 3420,
                }
            ],
        },
    ).json()

    response = client.post(f"/api/draft-orders/{created['draft_order_id']}/quote.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith('attachment; filename="quote-')
    assert response.content.startswith(b"%PDF-")
    generated = client.get(f"/api/draft-orders/{created['draft_order_id']}").json()
    assert generated["status"] == "quote-created"
    assert generated["quote_id"]

    saved_payload = main.store.get_quote(generated["quote_id"])
    rendered: list[dict] = []

    def capture_existing_quote(**kwargs):
        rendered.append(kwargs)
        return b"%PDF-existing-quote"

    monkeypatch.setattr(main, "build_quote_pdf", capture_existing_quote)
    before = client.get(f"/api/draft-orders/{created['draft_order_id']}").json()

    inline = client.get(f"/api/draft-orders/{created['draft_order_id']}/quote.pdf")
    download = client.get(
        f"/api/draft-orders/{created['draft_order_id']}/quote.pdf",
        params={"download": "true"},
    )
    after = client.get(f"/api/draft-orders/{created['draft_order_id']}").json()

    assert inline.status_code == 200
    assert inline.headers["content-type"] == "application/pdf"
    assert inline.headers["content-disposition"].startswith(
        f'inline; filename="quote-{generated["quote_id"]}-'
    )
    assert inline.content == b"%PDF-existing-quote"
    assert download.status_code == 200
    assert download.headers["content-disposition"].startswith(
        f'attachment; filename="quote-{generated["quote_id"]}-'
    )
    assert before == after
    assert len(rendered) == 2
    assert all(call["quote_id"] == generated["quote_id"] for call in rendered)
    assert all(
        call["generated_at"].isoformat() == saved_payload["created_at"]
        for call in rendered
    )


def test_existing_quote_pdf_rejects_an_uncreated_draft() -> None:
    client = TestClient(app)
    created = client.post("/api/draft-orders", json={"account_id": "acct-riverfront"}).json()

    response = client.get(f"/api/draft-orders/{created['draft_order_id']}/quote.pdf")

    assert response.status_code == 409
    assert response.json()["detail"] == "Generate this quote before viewing its PDF."


def test_create_blank_draft_for_same_account_starts_a_new_root_quote() -> None:
    client = TestClient(app)
    existing_response = client.post(
        "/api/draft-orders",
        json={
            "account_id": "acct-riverfront",
            "line_items": [
                {
                    "sku": "SOFT-PRACTICE-12",
                    "title": "Practice Management",
                    "category": "software",
                    "quantity": 1,
                    "unit_price": 3420,
                }
            ],
        },
    )
    assert existing_response.status_code == 200
    existing = existing_response.json()
    quote_response = client.post(
        "/api/cpq/quote-drafts",
        json={"draft_order_id": existing["draft_order_id"]},
    )
    assert quote_response.status_code == 200

    response = client.post(
        "/api/draft-orders",
        json={"account_id": "acct-riverfront"},
    )

    assert response.status_code == 200
    created = response.json()
    assert created["draft_order_id"] != existing["draft_order_id"]
    assert created["account_id"] == existing["account_id"]
    assert created["status"] == "draft"
    assert created["line_items"] == []
    assert created["revision_number"] == 1
    assert created["parent_draft_order_id"] is None
    assert created["source_quote_id"] is None
    assert created["quote_id"] is None


def test_resume_returns_latest_working_quote_without_creating_an_empty_draft() -> None:
    client = TestClient(app)
    created = client.post(
        "/api/draft-orders",
        json={
            "account_id": "acct-lakeside",
            "line_items": [
                {
                    "sku": "SOFT-PRACTICE-12",
                    "title": "Practice Management",
                    "category": "software",
                    "quantity": 1,
                    "unit_price": 3420,
                }
            ],
        },
    ).json()
    client.post("/api/draft-orders", json={"account_id": "acct-lakeside"})

    response = client.get(
        "/api/draft-orders/resume",
        params={"account_id": "acct-lakeside", "view_role": "seller"},
    )

    assert response.status_code == 200
    assert response.json()["draft"]["draft_order_id"] == created["draft_order_id"]


def test_patch_draft_uses_optimistic_version() -> None:
    client = TestClient(app)
    created = client.post("/api/draft-orders", json={"account_id": "acct-riverfront"}).json()

    first = client.patch(
        f"/api/draft-orders/{created['draft_order_id']}",
        json={"line_items": [], "expected_version": 0},
    )
    stale = client.patch(
        f"/api/draft-orders/{created['draft_order_id']}",
        json={"line_items": [], "expected_version": 0},
    )

    assert first.status_code == 200
    assert first.json()["version"] == 1
    assert stale.status_code == 409


def test_recommendation_apply_is_server_side_and_idempotent() -> None:
    client = TestClient(app)
    created = client.post("/api/draft-orders", json={"account_id": "acct-riverfront"}).json()
    line = main.build_catalog_line(
        "SOFT-PRACTICE-12",
        quantity=1,
        account_id="acct-riverfront",
    )
    recommendation = main.store.set_latest_recommendation(
        created["draft_order_id"],
        {"summary": "Software", "items": [line], "evidence": []},
    )
    body = {
        "recommendation_id": recommendation["recommendation_id"],
        "expected_revision": recommendation["revision"],
        "mode": "add",
    }

    first = client.post(
        f"/api/draft-orders/{created['draft_order_id']}/recommendations/apply",
        json=body,
    )
    changed = client.patch(
        f"/api/draft-orders/{created['draft_order_id']}",
        json={"line_items": [], "expected_version": 1},
    )
    repeated = client.post(
        f"/api/draft-orders/{created['draft_order_id']}/recommendations/apply",
        json=body,
    )
    mismatched_revision = client.post(
        f"/api/draft-orders/{created['draft_order_id']}/recommendations/apply",
        json={**body, "expected_revision": recommendation["revision"] + 1},
    )
    mismatched_mode = client.post(
        f"/api/draft-orders/{created['draft_order_id']}/recommendations/apply",
        json={**body, "mode": "replace"},
    )

    assert first.status_code == 200
    assert first.json()["already_applied"] is False
    assert first.json()["order"]["version"] == 1
    assert changed.status_code == 200
    assert repeated.status_code == 200
    assert repeated.json()["already_applied"] is True
    assert repeated.json()["order"]["version"] == 2
    assert repeated.json()["order"]["line_items"] == []
    assert mismatched_revision.status_code == 409
    assert mismatched_mode.status_code == 409


def test_recommendation_apply_rejects_draft_changed_since_generation() -> None:
    client = TestClient(app)
    created = client.post("/api/draft-orders", json={"account_id": "acct-riverfront"}).json()
    line = main.build_catalog_line(
        "SOFT-PRACTICE-12",
        quantity=1,
        account_id="acct-riverfront",
    )
    recommendation = main.store.set_latest_recommendation(
        created["draft_order_id"],
        {"summary": "Software", "items": [line]},
    )
    changed = client.patch(
        f"/api/draft-orders/{created['draft_order_id']}",
        json={"line_items": [], "expected_version": 0},
    )

    response = client.post(
        f"/api/draft-orders/{created['draft_order_id']}/recommendations/apply",
        json={
            "recommendation_id": recommendation["recommendation_id"],
            "expected_revision": recommendation["revision"],
            "mode": "replace",
        },
    )

    assert changed.status_code == 200
    assert response.status_code == 409
