from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from common import call_api, find_by_title, get_spark, guidance_volume_path, runtime_file_path

SCRIPT_FILE = runtime_file_path(globals())
SHARED_ROOT = SCRIPT_FILE.parents[1] / "shared"
if SHARED_ROOT.exists() and str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))

from agentic_cpq_demo.demo_data import build_genie_serialized_space, genie_space_title


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or update the unified CPQ Genie Agent and attach its guidance volume."
    )
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--guidance-volume", required=True)
    parser.add_argument("--warehouse-id", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--agent-prefix", required=True)
    return parser.parse_args()


def _resource_id(resource: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = resource.get(key)
        if value:
            return str(value)
    raise KeyError(keys[0])


def _patch_with_update_mask(
    spark,
    path: str,
    payload: dict[str, Any],
    fields: tuple[str, ...],
) -> None:
    call_api(
        spark,
        "PATCH",
        path,
        payload=payload,
        query={"update_mask": ",".join(fields)},
    )


def ensure_genie_space(
    spark,
    *,
    title: str,
    description: str,
    warehouse_id: str,
    serialized_space: str,
) -> dict[str, Any]:
    response = call_api(spark, "GET", "/api/2.0/genie/spaces")
    existing = find_by_title(response.get("spaces", []), title)
    if existing:
        space_id = _resource_id(existing, "id", "space_id", "genie_space_id")
        # Genie requires an explicit update mask; without one the PATCH can
        # silently leave both the governed tables and attached volume stale.
        _patch_with_update_mask(
            spark,
            f"/api/2.0/genie/spaces/{space_id}",
            {
                "title": title,
                "description": description,
                "warehouse_id": warehouse_id,
                "serialized_space": serialized_space,
            },
            ("title", "description", "warehouse_id", "serialized_space"),
        )
        return existing
    return call_api(
        spark,
        "POST",
        "/api/2.0/genie/spaces",
        payload={
            "title": title,
            "description": description,
            "warehouse_id": warehouse_id,
            "parent_path": "/Workspace/Shared",
            "serialized_space": serialized_space,
        },
    )


def main() -> None:
    args = parse_args()
    if not args.warehouse_id.strip():
        raise ValueError("A non-empty --warehouse-id is required to create the Genie Agent.")
    spark = get_spark()

    serialized_space = build_genie_serialized_space(
        args.catalog,
        args.schema,
        args.guidance_volume,
    )
    genie = ensure_genie_space(
        spark,
        title=genie_space_title(args.agent_prefix, args.environment),
        description=(
            "Unified Agentic CPQ intelligence for structured CPQ data "
            "and cited guidance documents."
        ),
        warehouse_id=args.warehouse_id,
        serialized_space=serialized_space,
    )

    genie_id = _resource_id(genie, "id", "space_id", "genie_space_id")
    guidance_path = guidance_volume_path(
        args.catalog,
        args.schema,
        args.guidance_volume,
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "genie_agent": {
                    "id": genie_id,
                    "title": genie.get("title")
                    or genie_space_title(args.agent_prefix, args.environment),
                    "warehouse_id": args.warehouse_id,
                },
                "guidance_volume": {
                    "full_name": f"{args.catalog}.{args.schema}.{args.guidance_volume}",
                    "path": f"{guidance_path}/",
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
