from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common import ensure_volume_directory, get_dbutils, get_spark, guidance_volume_path, runtime_file_path
from guidance_documents import GUIDANCE_DOCUMENT_NAMES

SCRIPT_FILE = runtime_file_path(globals())
SHARED_ROOT = SCRIPT_FILE.parents[1] / "shared"
if SHARED_ROOT.exists() and str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))

from agentic_cpq_demo.demo_data import (
    ACCOUNTS,
    PRODUCTS,
    PROMOTIONS,
    SAMPLE_PROMPTS,
    SOURCE_FRESHNESS,
    build_account_history_rows,
    build_approval_rule_rows,
    build_bundle_component_rows,
    build_installed_base_rows,
    build_inventory_rows,
    build_equipment_order_history_rows,
    build_pricebook_rows,
    build_quote_conversion_history_rows,
    build_legacy_quote_history_rows,
    build_supplier_price_book_rows,
    build_supplier_segment_pricing_rows,
    build_warranty_eligibility_rows,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed demo Unity Catalog tables and Genie guidance documents.")
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--guidance-volume", required=True)
    return parser.parse_args()


def _normalized_products() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for product in PRODUCTS:
        rows.append(
            {
                **product,
                "bundle_tags_text": ", ".join(product["bundle_tags"]),
            }
        )
    return rows


def _guidance_documents_dir() -> Path:
    return SCRIPT_FILE.parent / "genie_guidance_docs"


def _guidance_document_paths() -> list[Path]:
    documents_dir = _guidance_documents_dir()
    paths = [documents_dir / name for name in GUIDANCE_DOCUMENT_NAMES]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing reviewed Genie guidance documents: {', '.join(missing)}")
    discovered = {path.name for path in documents_dir.glob("*.docx")}
    expected = set(GUIDANCE_DOCUMENT_NAMES)
    if discovered != expected:
        unexpected = sorted(discovered - expected)
        raise RuntimeError(f"Genie guidance directory must contain exactly the reviewed documents; unexpected={unexpected}")
    return paths


def _dbutils_local_file_uri(path: Path) -> str:
    """Build a local DBUtils URI without URL-encoding workspace filesystem paths."""

    return f"file:{path.expanduser().resolve().as_posix()}"


def main() -> None:
    args = parse_args()
    spark = get_spark()
    dbutils = get_dbutils(spark)

    spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{args.catalog}`.`{args.schema}`")
    spark.sql(
        f"CREATE VOLUME IF NOT EXISTS `{args.catalog}`.`{args.schema}`.`{args.guidance_volume}`"
    )

    table_rows = {
        "products": _normalized_products(),
        "pricebook": build_pricebook_rows(),
        "bundle_components": build_bundle_component_rows(),
        "account_history": build_account_history_rows(),
        "installed_base": build_installed_base_rows(),
        "inventory": build_inventory_rows(),
        "promotions": PROMOTIONS,
        "equipment_order_history": build_equipment_order_history_rows(),
        "supplier_segment_pricing": build_supplier_segment_pricing_rows(),
        "supplier_price_book": build_supplier_price_book_rows(),
        "legacy_quote_history": build_legacy_quote_history_rows(),
        "quote_conversion_history": build_quote_conversion_history_rows(),
        "approval_rules": build_approval_rule_rows(),
        "warranty_eligibility": build_warranty_eligibility_rows(),
        "accounts": ACCOUNTS,
        # Served by the app at runtime (Lakebase synced), so they must be tables too.
        "sample_prompts": [{"prompt": prompt} for prompt in SAMPLE_PROMPTS],
        "source_freshness": SOURCE_FRESHNESS,
    }

    for table_name, rows in table_rows.items():
        fq = f"`{args.catalog}`.`{args.schema}`.`{table_name}`"
        # Add a stable surrogate `id` so every table has a primary key. Lakebase
        # synced tables (UC -> Postgres) require a PK on the source Delta table.
        keyed_rows = [{"id": index, **row} for index, row in enumerate(rows)]
        dataframe = spark.createDataFrame(keyed_rows)
        dataframe.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(fq)
        _ensure_primary_key(spark, fq, table_name)

    guidance_root = guidance_volume_path(
        args.catalog,
        args.schema,
        args.guidance_volume,
    )
    ensure_volume_directory(spark, guidance_root)
    guidance_documents = _guidance_document_paths()
    for path in guidance_documents:
        dbutils.fs.cp(_dbutils_local_file_uri(path), f"{guidance_root}/{path.name}", True)

    print(
        json.dumps(
            {
                "status": "ok",
                "seeded_tables": sorted(table_rows.keys()),
                "guidance_volume": f"{args.catalog}.{args.schema}.{args.guidance_volume}",
                "guidance_documents_path": guidance_root,
                "guidance_document_files": [path.name for path in guidance_documents],
            },
            indent=2,
        )
    )


def _ensure_primary_key(spark, fq: str, table_name: str) -> None:
    """Make the table sync-ready: Change Data Feed on + NOT NULL `id` + PRIMARY KEY(id).
    Defensive/idempotent so re-runs (overwrite) don't hard-fail on an existing constraint."""
    constraint = f"{table_name}_pk"
    statements = [
        f"ALTER TABLE {fq} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)",
        f"ALTER TABLE {fq} ALTER COLUMN id SET NOT NULL",
        f"ALTER TABLE {fq} DROP CONSTRAINT IF EXISTS {constraint}",
        f"ALTER TABLE {fq} ADD CONSTRAINT {constraint} PRIMARY KEY (id)",
    ]
    for statement in statements:
        try:
            spark.sql(statement)
        except Exception as exc:  # noqa: BLE001 - seeding must not fail on constraint quirks
            print(json.dumps({"warning": "constraint step failed", "sql": statement, "error": str(exc)}))


if __name__ == "__main__":
    main()
