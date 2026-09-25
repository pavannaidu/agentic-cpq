from __future__ import annotations

from fastapi.testclient import TestClient

from server import main
from server.main import app


class FakeSearchClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def search_governed_candidates(self, **kwargs):
        self.calls.append(kwargs)
        candidates = kwargs["candidates"]
        return {
            "results": list(reversed(candidates))[: kwargs["limit"]],
            "mode": "semantic",
            "fallback_used": False,
        }


def test_product_search_uses_governed_ranker_and_redacts_internal_source(monkeypatch) -> None:
    fake = FakeSearchClient()
    monkeypatch.setattr(main, "agent_client", fake)
    monkeypatch.setattr(
        main.lakebase,
        "get_products",
        lambda: [
            {
                "sku": "CHAIR-1",
                "title": "Treatment chair",
                "category": "equipment",
                "unit_price": 100,
                "doc_source": "internal.pdf",
            },
            {
                "sku": "CAM-2",
                "title": "Intraoral camera",
                "category": "imaging",
                "unit_price": 200,
                "doc_source": "internal.pdf",
            },
        ],
    )

    response = TestClient(app).get("/api/products/search?q=mouth+camera")

    assert response.status_code == 200
    payload = response.json()
    assert [row["sku"] for row in payload["results"]] == ["CAM-2", "CHAIR-1"]
    assert all("doc_source" not in row for row in payload["results"])
    assert payload["metadata"] == {"mode": "semantic", "fallback_used": False}
    assert payload["source"] == "lakebase"
    assert fake.calls[0]["kind"] == "products"
    assert fake.calls[0]["query"] == "mouth camera"
    assert fake.calls[0]["limit"] == 24


def test_product_search_filters_category_before_ranking(monkeypatch) -> None:
    fake = FakeSearchClient()
    monkeypatch.setattr(main, "agent_client", fake)
    monkeypatch.setattr(
        main.lakebase,
        "get_products",
        lambda: [
            {"sku": "CHAIR-1", "title": "Chair", "category": "equipment"},
            {"sku": "CAM-2", "title": "Camera", "category": "imaging"},
        ],
    )

    response = TestClient(app).get("/api/products/search?q=clinic&category=Imaging")

    assert response.status_code == 200
    assert [row["sku"] for row in fake.calls[0]["candidates"]] == ["CAM-2"]


def test_account_search_returns_only_ranked_governed_rows(monkeypatch) -> None:
    fake = FakeSearchClient()
    accounts = [
        {"account_id": "acct-one", "name": "One Dental", "state": "IL"},
        {"account_id": "acct-two", "name": "Two Dental", "state": "TX"},
    ]
    monkeypatch.setattr(main, "agent_client", fake)
    monkeypatch.setattr(main.lakebase, "get_accounts", lambda: accounts)

    response = TestClient(app).get("/api/accounts/search?q=texas+practice")

    assert response.status_code == 200
    payload = response.json()
    assert [row["account_id"] for row in payload["results"]] == ["acct-two", "acct-one"]
    assert payload["metadata"] == {"mode": "semantic", "fallback_used": False}
    assert fake.calls[0] == {
        "kind": "accounts",
        "query": "texas practice",
        "candidates": accounts,
        "limit": 20,
    }
