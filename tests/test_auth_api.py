from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from server import main
from server.main import app


def _deployed_settings(*manager_emails: str):
    return SimpleNamespace(
        is_databricks_app=True,
        manager_email_allowlist=frozenset(email.casefold() for email in manager_emails),
        databricks_app_name="agentic-cpq-test",
    )


def _headers(email: str) -> dict[str, str]:
    return {
        "x-forwarded-email": email,
        "x-forwarded-preferred-username": email.split("@", 1)[0],
    }


def test_me_discloses_server_authorized_views_and_execution_identity(monkeypatch) -> None:
    monkeypatch.setattr(main, "settings", _deployed_settings("manager@example.com"))
    client = TestClient(app)

    seller = client.get("/api/me", headers=_headers("seller@example.com")).json()
    manager = client.get("/api/me", headers=_headers("manager@example.com")).json()

    assert seller["allowed_views"] == ["seller"]
    assert seller["default_view"] == "seller"
    assert seller["execution_identity"] == "databricks-app:agentic-cpq-test"
    assert manager["allowed_views"] == ["seller", "manager"]


def test_client_cannot_self_authorize_manager_view(monkeypatch) -> None:
    monkeypatch.setattr(main, "settings", _deployed_settings())
    response = TestClient(app).post(
        "/api/draft-orders",
        headers=_headers("seller@example.com"),
        json={
            "account_id": "acct-riverfront",
            "view_role": "manager",
        },
    )

    assert response.status_code == 403


def test_draft_owner_isolated_but_allowlisted_manager_can_access(monkeypatch) -> None:
    monkeypatch.setattr(main, "settings", _deployed_settings("manager@example.com"))
    client = TestClient(app)
    created = client.post(
        "/api/draft-orders",
        headers=_headers("alice@example.com"),
        json={"account_id": "acct-riverfront"},
    ).json()

    assert created["owner_email"] == "alice@example.com"
    denied = client.get(
        f"/api/draft-orders/{created['draft_order_id']}",
        headers=_headers("bob@example.com"),
    )
    allowed = client.get(
        f"/api/draft-orders/{created['draft_order_id']}?view_role=manager",
        headers=_headers("manager@example.com"),
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200


def test_deployed_request_without_forwarded_identity_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(main, "settings", _deployed_settings())

    response = TestClient(app).get("/api/me")

    assert response.status_code == 401
