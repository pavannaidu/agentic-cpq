from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from pyspark.dbutils import DBUtils
from pyspark.sql import SparkSession


def get_spark() -> SparkSession:
    return SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()


def get_dbutils(spark: SparkSession) -> DBUtils:
    return DBUtils(spark)


def get_workspace_context(spark: SparkSession) -> tuple[str, str]:
    dbutils = get_dbutils(spark)
    context = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
    host = context.apiUrl().get().rstrip("/")
    token = context.apiToken().get()
    return host, token


def call_api(
    spark: SparkSession,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    query: dict[str, str] | None = None,
    timeout_seconds: int = 90,
) -> dict[str, Any]:
    host, token = get_workspace_context(spark)
    url = f"{host}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "agentic-cpq-demo-bootstrap/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"{method} {path} failed with {exc.code}: {body}") from exc


def write_volume_json(spark: SparkSession, path: str, payload: dict[str, Any]) -> None:
    dbutils = get_dbutils(spark)
    dbutils.fs.put(path, json.dumps(payload, indent=2, sort_keys=True), True)


def ensure_volume_directory(spark: SparkSession, path: str) -> None:
    get_dbutils(spark).fs.mkdirs(path)


def find_by_display_name(items: list[dict[str, Any]], display_name: str) -> dict[str, Any] | None:
    for item in items:
        if item.get("display_name") == display_name:
            return item
    return None


def find_by_title(items: list[dict[str, Any]], title: str) -> dict[str, Any] | None:
    for item in items:
        if item.get("title") == title:
            return item
    return None


def runtime_file_path(module_globals: Mapping[str, Any] | None = None) -> Path:
    candidates: list[str] = []
    if module_globals:
        for key in ("__file__", "filename"):
            value = module_globals.get(key)
            if isinstance(value, str) and value:
                candidates.append(value)

    argv0 = sys.argv[0] if sys.argv else ""
    if argv0 and argv0 not in {"-c", "-"}:
        candidates.append(argv0)

    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.is_absolute() or path.exists():
            return path.resolve()

    raise RuntimeError("Unable to determine the runtime file path for this Databricks task.")


def repo_shared_path(file_name: str | None = None) -> Path:
    shared_root = Path(__file__).resolve().parents[1] / "shared"
    return shared_root if file_name is None else shared_root / file_name


def guidance_volume_path(catalog: str, schema: str, volume: str) -> str:
    return f"/Volumes/{catalog}/{schema}/{volume}"


def grant_permission(
    spark: SparkSession,
    *,
    object_type: str,
    object_id: str,
    service_principal_name: str,
    permission_level: str,
) -> dict[str, Any]:
    return call_api(
        spark,
        "PATCH",
        f"/api/2.0/permissions/{object_type}/{object_id}",
        payload={
            "access_control_list": [
                {
                    "service_principal_name": service_principal_name,
                    "permission_level": permission_level,
                }
            ]
        },
    )
