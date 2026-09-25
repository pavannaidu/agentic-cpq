from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from databricks.sdk import WorkspaceClient

from common import call_api, get_dbutils, get_spark, guidance_volume_path, runtime_file_path
from guidance_documents import GUIDANCE_DOCUMENT_NAMES

SCRIPT_FILE = runtime_file_path(globals())
SHARED_ROOT = SCRIPT_FILE.parents[1] / "shared"
if SHARED_ROOT.exists() and str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))

from agentic_cpq_demo.demo_data import TABLE_NAMES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Smoke test the unified CPQ Genie Agent, guidance volume, and app access."
    )
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--guidance-volume", required=True)
    parser.add_argument("--genie-space-id", required=True)
    parser.add_argument("--app-client-id", required=True)
    return parser.parse_args()


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _principal_has_permission(
    permissions: dict[str, object],
    principal: str,
    allowed_levels: set[str],
) -> bool:
    for acl in permissions.get("access_control_list", []):
        if not isinstance(acl, dict) or acl.get("service_principal_name") != principal:
            continue
        for permission in acl.get("all_permissions", []):
            if isinstance(permission, dict) and permission.get("permission_level") in allowed_levels:
                return True
    return False


def _assert_genie_permission(spark, *, space_id: str, app_client_id: str) -> bool:
    if not space_id.strip():
        raise RuntimeError("Genie Agent ID was not configured.")
    permissions = call_api(spark, "GET", f"/api/2.0/permissions/genie/{space_id}")
    if not _principal_has_permission(permissions, app_client_id, {"CAN_RUN", "CAN_MANAGE"}):
        raise RuntimeError(
            f"App service principal {app_client_id} is missing CAN_RUN on Genie Agent {space_id}."
        )
    return True


def _row_mapping(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    if hasattr(row, "asDict"):
        return row.asDict(recursive=True)
    return {}


def _assert_guidance_volume_permission(
    spark,
    *,
    catalog: str,
    schema: str,
    guidance_volume: str,
    app_client_id: str,
) -> bool:
    rows = spark.sql(
        f"SHOW GRANTS ON VOLUME `{catalog}`.`{schema}`.`{guidance_volume}`"
    ).collect()
    for row in rows:
        normalized = {
            str(key).replace("_", "").replace(" ", "").casefold(): value
            for key, value in _row_mapping(row).items()
        }
        principal = str(normalized.get("principal", ""))
        action = str(normalized.get("actiontype", "")).replace("_", " ").upper()
        if principal == app_client_id and action in {"READ VOLUME", "ALL PRIVILEGES", "OWN"}:
            return True
    full_name = f"{catalog}.{schema}.{guidance_volume}"
    raise RuntimeError(
        f"App service principal {app_client_id} is missing READ VOLUME on {full_name}."
    )


def _assert_guidance_documents(spark, *, catalog: str, schema: str, guidance_volume: str) -> list[str]:
    path = guidance_volume_path(catalog, schema, guidance_volume)
    entries = get_dbutils(spark).fs.ls(path)
    actual = sorted(
        str(_get(entry, "name", "")).rstrip("/")
        for entry in entries
        if str(_get(entry, "name", "")) and not str(_get(entry, "name", "")).endswith("/")
    )
    expected = sorted(GUIDANCE_DOCUMENT_NAMES)
    if actual != expected:
        raise RuntimeError(
            f"Genie guidance volume must contain exactly the five reviewed DOCX files; "
            f"expected={expected}, actual={actual}."
        )
    return actual


def _assert_genie_answers(workspace, *, space_id: str, prompt: str) -> dict[str, object]:
    message = workspace.genie.start_conversation_and_wait(space_id, prompt)
    conversation_id = str(_get(message, "conversation_id", "") or "")
    message_id = str(_get(message, "id", "") or "")
    attachments = _values(_get(message, "attachments"))
    has_answer = any(
        bool(_get(_get(attachment, "text"), "content", ""))
        or bool(_get(_get(attachment, "query"), "query", ""))
        for attachment in attachments
    )
    if not conversation_id or not message_id or not has_answer:
        raise RuntimeError(f"Genie returned no usable answer for prompt: {prompt}")
    return {
        "conversation_id": conversation_id,
        "message_id": message_id,
        "attachment_count": len(attachments),
    }


def _volume_document_names(text: str) -> set[str]:
    names: set[str] = set()
    marker = "/explore/data/volumes/"
    for candidate in re.findall(r"https?://[^\s)>\]]+", text):
        parsed = urlparse(candidate)
        if marker not in parsed.path.casefold():
            continue
        preview = unquote((parse_qs(parsed.query).get("filePreviewPath") or [""])[0])
        name = preview.rstrip("/").rsplit("/", 1)[-1]
        if name:
            names.add(name)
    return names


def _message_text(item: Any) -> str:
    if str(_get(item, "type", "")).casefold() != "message":
        return ""
    parts: list[str] = []
    for part in _values(_get(item, "content")):
        text = str(_get(part, "text", "") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def _assert_useful_guidance(text: str, *, prompt: str) -> None:
    normalized = " ".join(text.lower().split())
    failure_markers = (
        "no search results",
        "don't have access to documentation",
        "do not have access to documentation",
        "don't have any search results",
        "i would need access to",
        "please provide the relevant documentation",
        "share or upload the relevant documentation",
        "based on standard equipment care positioning best practices",
    )
    if any(marker in normalized for marker in failure_markers):
        raise RuntimeError(
            f"Genie Agent returned non-actionable guidance for prompt: {prompt}: {text[:300]}"
        )


def _assert_genie_agent_guidance(
    workspace,
    *,
    space_id: str,
    prompt: str,
    client: Any | None = None,
) -> dict[str, object]:
    owns_client = client is None
    if client is None:
        from databricks_openai import DatabricksOpenAI

        client = DatabricksOpenAI(workspace_client=workspace, max_retries=1, timeout=180)
        host = workspace.config.host
        host = host if host.startswith("http") else f"https://{host}"
        client.base_url = f"{host.rstrip('/')}/api/2.0/genie/agents/{space_id}"

    answers: list[str] = []
    cited_documents: set[str] = set()
    conversation_id = ""
    status = ""

    def consume_item(item: Any) -> None:
        text = _message_text(item)
        if not text:
            return
        answers.append(text)
        cited_documents.update(_volume_document_names(text))

    def consume_response(response: Any) -> None:
        nonlocal conversation_id, status
        conversation_id = str(_get(response, "conversation_id", "") or conversation_id)
        status = str(_get(response, "status", "") or status).upper()
        for item in _values(_get(response, "output")):
            consume_item(item)

    try:
        stream = client.responses.create(
            model="genie-agent",
            input=[
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                }
            ],
            stream=True,
        )
        for event in stream:
            event_type = str(_get(event, "type", "")).casefold()
            if event_type == "response.output_item.done":
                consume_item(_get(event, "item"))
            elif event_type in {"response.created", "response.completed", "response.failed"}:
                consume_response(_get(event, "response"))

        answer = "\n\n".join(dict.fromkeys(answers)).strip()
        if status == "FAILED":
            raise RuntimeError("Genie Agent Mode failed while retrieving seller guidance.")
        if not answer:
            raise RuntimeError(f"Genie Agent Mode returned no visible answer for prompt: {prompt}")
        _assert_useful_guidance(answer, prompt=prompt)
        expected = set(GUIDANCE_DOCUMENT_NAMES)
        recognized = sorted(cited_documents & expected)
        if not recognized:
            raise RuntimeError(
                "Genie Agent Mode answered without a citation to one of the reviewed guidance documents."
            )
        return {
            "conversation_id": conversation_id or None,
            "answer_excerpt": answer[:600],
            "cited_documents": recognized,
        }
    finally:
        if owns_client:
            client.close()


def main() -> None:
    args = parse_args()
    spark = get_spark()
    genie_space_id = args.genie_space_id.strip()
    if not genie_space_id:
        raise ValueError("A non-empty --genie-space-id is required.")

    table_counts = {}
    for table_name in TABLE_NAMES:
        count = spark.sql(
            f"SELECT COUNT(*) AS cnt FROM `{args.catalog}`.`{args.schema}`.`{table_name}`"
        ).collect()[0]["cnt"]
        table_counts[table_name] = count

    guidance_documents = _assert_guidance_documents(
        spark,
        catalog=args.catalog,
        schema=args.schema,
        guidance_volume=args.guidance_volume,
    )
    permission_checks = {
        "genie_agent": _assert_genie_permission(
            spark,
            space_id=genie_space_id,
            app_client_id=args.app_client_id,
        ),
        "guidance_volume": _assert_guidance_volume_permission(
            spark,
            catalog=args.catalog,
            schema=args.schema,
            guidance_volume=args.guidance_volume,
            app_client_id=args.app_client_id,
        ),
    }

    workspace = WorkspaceClient()
    genie_answer = _assert_genie_answers(
        workspace,
        space_id=genie_space_id,
        prompt="Name one product that is eligible for a seller quote.",
    )
    guidance_answer = _assert_genie_agent_guidance(
        workspace,
        space_id=genie_space_id,
        prompt=(
            "Using the attached seller guidance, explain how to handle a financing "
            "question without inventing rates. Cite the source document."
        ),
    )

    print(
        json.dumps(
            {
                "status": "ok",
                "table_counts": table_counts,
                "genie_space_id": genie_space_id,
                "guidance_volume": f"{args.catalog}.{args.schema}.{args.guidance_volume}",
                "guidance_documents": guidance_documents,
                "permission_checks": permission_checks,
                "genie_conversation_answer": genie_answer,
                "genie_agent_guidance_answer": guidance_answer,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
