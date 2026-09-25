from __future__ import annotations

import argparse
import json
import sys

from common import get_spark, grant_permission, guidance_volume_path, runtime_file_path

SCRIPT_FILE = runtime_file_path(globals())
SHARED_ROOT = SCRIPT_FILE.parents[1] / "shared"
if SHARED_ROOT.exists() and str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))

from agentic_cpq_demo.demo_data import TABLE_NAMES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Grant the Databricks App principal access to UC and the unified Genie Agent."
    )
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--guidance-volume", required=True)
    parser.add_argument("--genie-space-id", required=True)
    parser.add_argument("--app-client-id", required=True)
    return parser.parse_args()


def _grant_uc_permissions(
    spark,
    catalog: str,
    schema: str,
    guidance_volume: str,
    principal: str,
) -> None:
    spark.sql(f"GRANT USE CATALOG ON CATALOG `{catalog}` TO `{principal}`")
    spark.sql(f"GRANT USE SCHEMA ON SCHEMA `{catalog}`.`{schema}` TO `{principal}`")
    for table_name in TABLE_NAMES:
        spark.sql(f"GRANT SELECT ON TABLE `{catalog}`.`{schema}`.`{table_name}` TO `{principal}`")
    spark.sql(
        f"GRANT READ VOLUME ON VOLUME `{catalog}`.`{schema}`.`{guidance_volume}` TO `{principal}`"
    )


def main() -> None:
    args = parse_args()
    genie_space_id = args.genie_space_id.strip()
    if not genie_space_id:
        raise ValueError("A non-empty --genie-space-id is required.")

    spark = get_spark()
    _grant_uc_permissions(
        spark,
        args.catalog,
        args.schema,
        args.guidance_volume,
        args.app_client_id,
    )
    grant_permission(
        spark,
        object_type="genie",
        object_id=genie_space_id,
        service_principal_name=args.app_client_id,
        permission_level="CAN_RUN",
    )

    print(
        json.dumps(
            {
                "status": "ok",
                "app_client_id": args.app_client_id,
                "granted_tables": list(TABLE_NAMES),
                "genie_space_id": genie_space_id,
                "genie_permission": "CAN_RUN",
                "guidance_volume": {
                    "full_name": f"{args.catalog}.{args.schema}.{args.guidance_volume}",
                    "path": f"{guidance_volume_path(args.catalog, args.schema, args.guidance_volume)}/",
                    "permission": "READ_VOLUME",
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
