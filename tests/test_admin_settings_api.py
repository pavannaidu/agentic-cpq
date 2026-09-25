from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from server import main
from server.main import app
from server.models import CPQAdminSettings
from server.state import DraftOrderStore


def _deployed_settings(*manager_emails: str) -> SimpleNamespace:
    return SimpleNamespace(
        is_databricks_app=True,
        manager_email_allowlist=frozenset(email.casefold() for email in manager_emails),
        databricks_app_name="agentic-cpq-test",
        environment="test",
        default_account_id="acct-riverfront",
        quote_agent_name="Quote Agent",
        genie_space_title="Test Genie",
        use_mock_fallback=False,
    )


def _headers(email: str) -> dict[str, str]:
    return {
        "x-forwarded-email": email,
        "x-forwarded-preferred-username": email.split("@", 1)[0],
    }


def _custom_settings() -> dict:
    return {
        "pdf": {
            "layout": "compact",
            "show_list_prices": False,
            "show_savings": False,
            "brand_name": "Northstar Dental",
            "document_title": "Equipment proposal",
            "accent_color": "#2457C5",
            "footer_text": "Prepared by Northstar Dental",
            "terms_text": "Net 30. Installation timing is mutually agreed.",
            "validity_days": 45,
        },
        "behavior": {
            "approval_threshold": 50_000,
            "max_seller_discount_pct": 8,
            "allow_seller_price_edits": False,
            "auto_attach_care_plan": False,
        },
    }


def test_admin_settings_are_manager_gated_and_persist_in_memory(monkeypatch) -> None:
    memory_store = DraftOrderStore()
    monkeypatch.setattr(main, "store", memory_store)
    monkeypatch.setattr(main, "settings", _deployed_settings("manager@example.com"))
    client = TestClient(app)

    seller_headers = _headers("seller@example.com")
    manager_headers = _headers("manager@example.com")
    assert client.get("/api/admin/settings", headers=seller_headers).status_code == 403
    assert client.put(
        "/api/admin/settings",
        headers=seller_headers,
        json=_custom_settings(),
    ).status_code == 403

    me = client.get("/api/me", headers=manager_headers).json()
    assert me["can_manage"] is True
    defaults = client.get("/api/admin/settings", headers=manager_headers).json()
    assert defaults == CPQAdminSettings().model_dump(mode="json")
    assert defaults["pdf"]["brand_name"] == "QUOTE WORKSPACE"
    assert defaults["pdf"]["footer_text"] == "Powered by Databricks"
    assert "revision" not in defaults["pdf"]["terms_text"].casefold()
    assert defaults["behavior"]["allow_seller_price_edits"] is True

    saved = client.put(
        "/api/admin/settings",
        headers=manager_headers,
        json=_custom_settings(),
    )
    assert saved.status_code == 200
    assert saved.json() == _custom_settings()
    assert client.get("/api/admin/settings", headers=manager_headers).json() == _custom_settings()


def test_bootstrap_exposes_current_behavior_as_public_quote_policy(monkeypatch) -> None:
    memory_store = DraftOrderStore()
    configured = CPQAdminSettings.model_validate(_custom_settings())
    memory_store.save_admin_settings(configured, updated_by="manager@example.com")
    monkeypatch.setattr(main, "store", memory_store)
    monkeypatch.setattr(main, "settings", _deployed_settings())

    response = TestClient(app).get(
        "/api/bootstrap-state",
        headers=_headers("seller@example.com"),
    )

    assert response.status_code == 200
    assert response.json()["quote_policy"] == configured.behavior.model_dump(mode="json")
    assert response.json()["quote_policy"]["allow_seller_price_edits"] is False


def test_disabled_seller_price_edits_allow_authorized_manager_view(monkeypatch) -> None:
    memory_store = DraftOrderStore()
    memory_store.save_admin_settings(
        CPQAdminSettings.model_validate(
            {"behavior": {"allow_seller_price_edits": False}}
        ),
        updated_by="manager@example.com",
    )
    monkeypatch.setattr(main, "store", memory_store)
    monkeypatch.setattr(main, "settings", _deployed_settings("manager@example.com"))
    client = TestClient(app)
    seller_headers = _headers("seller@example.com")
    manager_headers = _headers("manager@example.com")

    created = client.post(
        "/api/draft-orders",
        headers=seller_headers,
        json={"account_id": "acct-riverfront"},
    ).json()
    added = client.post(
        "/api/quote/add-line",
        headers=seller_headers,
        json={
            "draft_order_id": created["draft_order_id"],
            "sku": "SOFT-PRACTICE-12",
        },
    )
    assert added.status_code == 200
    before_blocked = memory_store.get(created["draft_order_id"])

    blocked = client.post(
        "/api/quote/set-price",
        headers=seller_headers,
        json={
            "draft_order_id": created["draft_order_id"],
            "sku": "SOFT-PRACTICE-12",
            "unit_price": 6_000,
            "view_role": "seller",
        },
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == (
        "Seller price edits are disabled by Workspace Settings; "
        "an authorized manager must edit the price."
    )
    after_blocked = memory_store.get(created["draft_order_id"])
    assert after_blocked.version == before_blocked.version
    assert after_blocked.line_items[0].unit_price == before_blocked.line_items[0].unit_price

    allowed = client.post(
        "/api/quote/set-price",
        headers=manager_headers,
        json={
            "draft_order_id": created["draft_order_id"],
            "sku": "SOFT-PRACTICE-12",
            "unit_price": 6_000,
            "view_role": "manager",
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["line_items"][0]["unit_price"] == 6_000

    memory_store.save_admin_settings(CPQAdminSettings(), updated_by="manager@example.com")
    enabled = client.post(
        "/api/quote/set-price",
        headers=seller_headers,
        json={
            "draft_order_id": created["draft_order_id"],
            "sku": "SOFT-PRACTICE-12",
            "unit_price": 6_100,
            "view_role": "seller",
        },
    )
    assert enabled.status_code == 200
    assert enabled.json()["line_items"][0]["unit_price"] == 6_100


def test_disabled_seller_price_edits_guard_patch_but_allow_quantity_and_removal(
    monkeypatch,
) -> None:
    memory_store = DraftOrderStore()
    memory_store.save_admin_settings(
        CPQAdminSettings.model_validate(
            {"behavior": {"allow_seller_price_edits": False}}
        ),
        updated_by="manager@example.com",
    )
    monkeypatch.setattr(main, "store", memory_store)
    monkeypatch.setattr(main, "settings", _deployed_settings())
    client = TestClient(app)
    seller_headers = _headers("seller@example.com")

    created = client.post(
        "/api/draft-orders",
        headers=seller_headers,
        json={"account_id": "acct-riverfront"},
    ).json()
    added = client.post(
        "/api/quote/add-line",
        headers=seller_headers,
        json={
            "draft_order_id": created["draft_order_id"],
            "sku": "SOFT-PRACTICE-12",
        },
    ).json()
    original_line = added["line_items"][0]
    changed_price = {**original_line, "unit_price": original_line["unit_price"] - 1}

    bypass = client.patch(
        f"/api/draft-orders/{created['draft_order_id']}",
        headers=seller_headers,
        json={
            "line_items": [changed_price],
            "expected_version": added["version"],
            "view_role": "seller",
        },
    )
    assert bypass.status_code == 403
    assert bypass.json()["detail"].endswith(
        "keep the existing unit price for SOFT-PRACTICE-12."
    )

    insertion = client.patch(
        f"/api/draft-orders/{created['draft_order_id']}",
        headers=seller_headers,
        json={
            "line_items": [
                original_line,
                {
                    "sku": "SENSOR-IO-20",
                    "title": "Intraoral Sensor Kit",
                    "category": "imaging",
                    "quantity": 1,
                    "unit_price": 1,
                },
            ],
            "expected_version": added["version"],
            "view_role": "seller",
        },
    )
    assert insertion.status_code == 403
    assert "dedicated add-line flow" in insertion.json()["detail"]

    quantity_update = client.patch(
        f"/api/draft-orders/{created['draft_order_id']}",
        headers=seller_headers,
        json={
            "line_items": [{**original_line, "quantity": 2}],
            "expected_version": added["version"],
            "view_role": "seller",
        },
    )
    assert quantity_update.status_code == 200
    assert quantity_update.json()["line_items"][0]["quantity"] == 2
    assert (
        quantity_update.json()["line_items"][0]["unit_price"]
        == original_line["unit_price"]
    )

    removal = client.patch(
        f"/api/draft-orders/{created['draft_order_id']}",
        headers=seller_headers,
        json={
            "line_items": [],
            "expected_version": quantity_update.json()["version"],
            "view_role": "seller",
        },
    )
    assert removal.status_code == 200
    assert removal.json()["line_items"] == []


def test_admin_settings_validate_document_and_commercial_controls(monkeypatch) -> None:
    monkeypatch.setattr(main, "store", DraftOrderStore())
    client = TestClient(app)
    invalid = _custom_settings()
    invalid["pdf"]["accent_color"] = "blue"
    invalid["behavior"]["max_seller_discount_pct"] = 101

    response = client.put("/api/admin/settings", json=invalid)

    assert response.status_code == 422
    fields = {error["loc"][-1] for error in response.json()["detail"]}
    assert fields == {"accent_color", "max_seller_discount_pct"}


def test_admin_pdf_preview_is_manager_gated_and_returns_inline_pdf(monkeypatch) -> None:
    monkeypatch.setattr(main, "settings", _deployed_settings("manager@example.com"))
    client = TestClient(app)

    seller = client.post(
        "/api/admin/settings/pdf-preview",
        headers=_headers("seller@example.com"),
        json=_custom_settings()["pdf"],
    )
    assert seller.status_code == 403

    preview = client.post(
        "/api/admin/settings/pdf-preview",
        headers=_headers("manager@example.com"),
        json=_custom_settings()["pdf"],
    )
    assert preview.status_code == 200
    assert preview.content.startswith(b"%PDF-")
    assert preview.headers["content-type"] == "application/pdf"
    assert preview.headers["content-disposition"].startswith("inline;")
    assert preview.headers["cache-control"] == "no-store"
    assert preview.headers["x-content-type-options"] == "nosniff"


def test_admin_pdf_preview_uses_unsaved_settings_and_representative_quote(monkeypatch) -> None:
    memory_store = DraftOrderStore()
    monkeypatch.setattr(main, "store", memory_store)
    monkeypatch.setattr(main, "settings", _deployed_settings("manager@example.com"))
    rendered: list[dict] = []

    def capture_pdf(**kwargs):
        rendered.append(kwargs)
        return b"%PDF-preview"

    monkeypatch.setattr(main, "build_quote_pdf", capture_pdf)
    client = TestClient(app)
    custom_pdf = _custom_settings()["pdf"]

    preview = client.post(
        "/api/admin/settings/pdf-preview",
        headers=_headers("manager@example.com"),
        json=custom_pdf,
    )

    assert preview.status_code == 200
    assert rendered[0]["pdf_settings"].model_dump(mode="json") == custom_pdf
    assert rendered[0]["account"] == {
        "name": "Riverfront Dental Group",
        "segment": "mid-market",
        "region": "Northeast",
    }
    assert rendered[0]["seller_email"] == "manager@example.com"
    assert rendered[0]["line_items"][0]["list_price"] > rendered[0]["line_items"][0]["unit_price"]
    assert rendered[0]["line_items"][1]["is_addon"] is True
    assert memory_store.get_admin_settings() == CPQAdminSettings()


def test_quote_payload_receives_active_admin_approval_threshold(monkeypatch) -> None:
    memory_store = DraftOrderStore()
    custom = CPQAdminSettings.model_validate(
        {"behavior": {"approval_threshold": 7_000}}
    )
    memory_store.save_admin_settings(custom, updated_by="manager@example.com")
    monkeypatch.setattr(main, "store", memory_store)
    actual_build_quote_payload = main.build_quote_payload
    captured_thresholds: list[float] = []

    def capture_quote_payload(**kwargs):
        captured_thresholds.append(kwargs["approval_threshold"])
        return actual_build_quote_payload(**kwargs)

    monkeypatch.setattr(main, "build_quote_payload", capture_quote_payload)
    client = TestClient(app)
    draft = client.post(
        "/api/draft-orders",
        json={
            "account_id": "acct-riverfront",
            "line_items": [
                {
                    "sku": "SOFT-PRACTICE-12",
                    "title": "Practice Management",
                    "category": "software",
                    "quantity": 1,
                    "unit_price": 6_240,
                }
            ],
        },
    ).json()

    response = client.post(
        "/api/cpq/quote-drafts",
        json={"draft_order_id": draft["draft_order_id"]},
    )

    assert response.status_code == 200
    assert captured_thresholds == [7_000]
    stored = memory_store.get_quote(response.json()["quote_id"])
    assert stored["quote_document"]["pricing_controls"]["approval_status"] == "clear"


def test_behavior_settings_control_threshold_discount_and_care_plan(monkeypatch) -> None:
    memory_store = DraftOrderStore()
    memory_store.save_admin_settings(
        CPQAdminSettings.model_validate(
            {
                "behavior": {
                    "approval_threshold": 3_000,
                    "max_seller_discount_pct": 5,
                    "auto_attach_care_plan": False,
                }
            }
        ),
        updated_by="manager@example.com",
    )
    monkeypatch.setattr(main, "store", memory_store)
    client = TestClient(app)

    created = client.post(
        "/api/draft-orders",
        json={"account_id": "acct-riverfront"},
    ).json()
    added = client.post(
        "/api/quote/add-line",
        json={
            "draft_order_id": created["draft_order_id"],
            "sku": "IMAG-CBCT-210",
            "view_role": "manager",
        },
    )
    assert added.status_code == 200
    assert [line["sku"] for line in added.json()["line_items"]] == ["IMAG-CBCT-210"]

    repriced = client.post(
        "/api/quote/set-price",
        json={
            "draft_order_id": created["draft_order_id"],
            "sku": "IMAG-CBCT-210",
            "unit_price": 10_000,
            "view_role": "manager",
        },
    )
    assert repriced.status_code == 200
    line = repriced.json()["line_items"][0]
    assert line["approval_required"] is True
    assert "configured 5.0% limit" in line["approval_reason"]

    blocked = client.post(
        f"/api/draft-orders/{created['draft_order_id']}/quote.pdf",
        params={"view_role": "manager"},
    )
    assert blocked.status_code == 409
    assert "configured 5.0% limit" in blocked.json()["detail"]

    threshold_draft = client.post(
        "/api/draft-orders",
        json={
            "account_id": "acct-riverfront",
            "line_items": [
                {
                    "sku": "SOFT-PRACTICE-12",
                    "title": "Practice Management",
                    "category": "software",
                    "quantity": 1,
                    "unit_price": 6_240,
                }
            ],
        },
    ).json()
    threshold_blocked = client.post(
        f"/api/draft-orders/{threshold_draft['draft_order_id']}/quote.pdf",
        params={"view_role": "manager"},
    )
    assert threshold_blocked.status_code == 409
    assert threshold_blocked.json()["detail"].endswith("above $3,000.")


def test_pdf_settings_are_snapshotted_and_passed_to_renderer(monkeypatch) -> None:
    memory_store = DraftOrderStore()
    custom = CPQAdminSettings.model_validate(_custom_settings())
    memory_store.save_admin_settings(custom, updated_by="manager@example.com")
    monkeypatch.setattr(main, "store", memory_store)
    rendered: list[dict] = []

    def capture_pdf(**kwargs):
        rendered.append(kwargs)
        return b"%PDF-admin-settings"

    monkeypatch.setattr(main, "build_quote_pdf", capture_pdf)
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
                    "unit_price": 6_240,
                }
            ],
        },
    ).json()

    generated = client.post(f"/api/draft-orders/{created['draft_order_id']}/quote.pdf")
    assert generated.status_code == 200
    assert rendered[-1]["pdf_settings"] == custom.pdf

    memory_store.save_admin_settings(CPQAdminSettings(), updated_by="manager@example.com")
    existing = client.get(f"/api/draft-orders/{created['draft_order_id']}/quote.pdf")
    assert existing.status_code == 200
    assert rendered[-1]["pdf_settings"] == custom.pdf
