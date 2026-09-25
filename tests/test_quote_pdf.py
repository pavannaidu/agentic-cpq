from __future__ import annotations

from server.quote_pdf import build_quote_pdf
from server.models import QuotePdfSettings


def test_quote_pdf_paginates_large_line_item_sets() -> None:
    lines = [
        {
            "sku": f"SKU-{index:03d}",
            "title": f"Professional equipment package {index + 1}",
            "category": "equipment",
            "quantity": index % 3 + 1,
            "list_price": 1250 + index,
            "unit_price": 1195 + index,
            "total_price": (1195 + index) * (index % 3 + 1),
        }
        for index in range(100)
    ]

    document = build_quote_pdf(
        quote_id="Q-DEMO-100",
        order_id="draft-demo",
        revision_number=2,
        account={"name": "Riverfront Dental Group", "segment": "mid-market", "region": "Central"},
        seller_email="seller@example.com",
        line_items=lines,
    )

    assert document.startswith(b"%PDF-")
    assert len(document) > 10_000
    assert document.count(b"/Type /Page") >= 3


def test_quote_pdf_accepts_compact_branded_visibility_settings() -> None:
    document = build_quote_pdf(
        quote_id="Q-BRAND-100",
        order_id="draft-brand",
        revision_number=1,
        account={"name": "Northstar Dental", "segment": "enterprise", "region": "Central"},
        seller_email="seller@example.com",
        line_items=[
            {
                "sku": "SOFT-PRACTICE-12",
                "title": "Practice Management",
                "category": "software",
                "quantity": 1,
                "list_price": 3_600,
                "unit_price": 3_420,
                "total_price": 3_420,
            }
        ],
        pdf_settings=QuotePdfSettings(
            layout="compact",
            show_list_prices=False,
            show_savings=False,
            brand_name="Northstar",
            document_title="Equipment proposal",
            accent_color="#2457C5",
            footer_text="Prepared by Northstar",
            terms_text="Net 30.",
            validity_days=45,
        ),
    )

    assert document.startswith(b"%PDF-")
    assert len(document) > 2_000
