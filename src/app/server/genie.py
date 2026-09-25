from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import timedelta
from typing import Any, Iterable
from urllib.parse import parse_qs, unquote, urlparse

from databricks.sdk import WorkspaceClient

from .config import Settings
from .models import (
    EvidenceFreshness,
    EvidenceStatus,
    GenieCitation,
    GenieEvidenceEnvelope,
    GenieSqlAttachment,
)
from .redaction import normalize_view_role

logger = logging.getLogger(__name__)

_SPACE_ID_CACHE: dict[str, str] = {}
ROW_LIMIT = 50
GENIE_WAIT_TIMEOUT = timedelta(seconds=85)

_SENSITIVE_COLUMN_NAMES = frozenset(
    {
        "suppliercost",
        "grossmarginpct",
        "approvalfloorpct",
        "legacywholesalecost",
        "negotiatedcost",
        "overpayperunit",
        "overpayamount",
        "legacysuppliercost",
        "correctsuppliercost",
    }
)
_SENSITIVE_PROSE = re.compile(
    r"\b(?:supplier\s+cost|gross\s+margin|margin\s+floor|approval\s+floor|"
    r"legacy\s+(?:wholesale|supplier)\s+cost|negotiated\s+cost|overpay(?:ment)?)\b",
    re.IGNORECASE,
)
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


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


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _enum_text(value: Any) -> str:
    return _text(_get(value, "value", value)).upper()


def _is_not_found_error(exc: Exception) -> bool:
    """Recognize stale conversation IDs without depending on one SDK error class."""

    return (
        type(exc).__name__ == "NotFoundError"
        or getattr(exc, "status_code", None) == 404
    )


def _normal_column(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", _text(value).casefold())


def _is_sensitive_column(value: Any) -> bool:
    return _normal_column(value) in _SENSITIVE_COLUMN_NAMES


def _sanitize_seller_prose(value: str, *, replacement: str = "") -> str:
    """Remove complete sentences/lines containing buy-side commercial facts."""

    clean = _text(value).replace("**", "")
    if not clean or not _SENSITIVE_PROSE.search(clean):
        return clean
    parts = re.split(r"(?<=[.!?])\s+|\n+", clean)
    retained = [part.strip() for part in parts if part.strip() and not _SENSITIVE_PROSE.search(part)]
    return " ".join(retained).strip() or replacement


def _resolve_space_id(workspace: WorkspaceClient, settings: Settings) -> str | None:
    if settings.genie_space_id:
        return settings.genie_space_id
    title = settings.genie_space_title
    if title in _SPACE_ID_CACHE:
        return _SPACE_ID_CACHE[title]
    try:
        response = workspace.api_client.do("GET", "/api/2.0/genie/spaces")
        for space in response.get("spaces", []):
            if space.get("title") == title:
                space_id = space.get("space_id") or space.get("id")
                if space_id:
                    _SPACE_ID_CACHE[title] = str(space_id)
                    return str(space_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not resolve configured Genie space (%s).", type(exc).__name__)
    return None


def _query_result_error() -> tuple[list[str], list[list[Any]], bool, str]:
    return [], [], False, "QUERY_RESULT_FAILED"


def _extract_rows(
    workspace: WorkspaceClient,
    space_id: str,
    conversation_id: str,
    message_id: str,
    attachment_id: str,
) -> tuple[list[str], list[list[Any]], bool, str | None]:
    try:
        result = workspace.genie.get_message_attachment_query_result(
            space_id,
            conversation_id,
            message_id,
            attachment_id,
        )
        statement = _get(result, "statement_response")
        if not statement:
            return _query_result_error()
        manifest = _get(statement, "manifest")
        schema = _get(manifest, "schema")
        columns = [
            _text(_get(column, "name"))
            for column in _values(_get(schema, "columns"))
            if _text(_get(column, "name"))
        ]
        data = _get(statement, "result")
        raw_rows = _values(_get(data, "data_array"))
        rows = [list(row) for row in raw_rows if isinstance(row, (list, tuple))]
        total_rows = _get(manifest, "total_row_count")
        truncated = len(rows) > ROW_LIMIT or bool(_get(data, "truncated", False))
        if isinstance(total_rows, int):
            truncated = truncated or total_rows > ROW_LIMIT
        return columns, rows[:ROW_LIMIT], truncated, None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Genie query-result fetch failed (%s).", type(exc).__name__)
        return _query_result_error()


def _citation_from(value: Any) -> GenieCitation | None:
    if isinstance(value, str):
        title = value.strip()
        return GenieCitation(title=title) if title else None
    if not isinstance(value, dict) and not hasattr(value, "__dict__"):
        return None
    citation_id = _text(_get(value, "citation_id") or _get(value, "id"))
    title = _text(
        _get(value, "title")
        or _get(value, "name")
        or _get(value, "display_name")
    )
    uri = _text(_get(value, "uri") or _get(value, "url") or _get(value, "link"))
    snippet = _text(
        _get(value, "snippet")
        or _get(value, "text")
        or _get(value, "content")
    )
    source = _text(_get(value, "source") or _get(value, "type")) or "genie"
    if not any((citation_id, title, uri, snippet)):
        return None
    return GenieCitation(
        citation_id=citation_id,
        title=title,
        uri=uri,
        snippet=snippet[:2000],
        source=source,
    )


def _citations_from(container: Any) -> list[GenieCitation]:
    """Read only explicitly named citation collections; ignore unknown attachments."""

    citations: list[GenieCitation] = []
    for name in ("citations", "sources", "references"):
        for raw in _values(_get(container, name)):
            citation = _citation_from(raw)
            if citation is not None:
                citations.append(citation)
    return citations


def _dedupe_citations(citations: Iterable[GenieCitation]) -> list[GenieCitation]:
    result: list[GenieCitation] = []
    seen: set[tuple[str, ...]] = set()
    for citation in citations:
        key = tuple(
            value.casefold()
            for value in (
                citation.citation_id,
                citation.uri,
                citation.title,
                citation.snippet,
            )
            if value
        )
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(citation)
    return result


def _volume_citations(value: str) -> list[GenieCitation]:
    citations: list[GenieCitation] = []
    for label, uri in _MARKDOWN_LINK.findall(value):
        parsed = urlparse(uri)
        if "/explore/data/volumes/" not in parsed.path.casefold():
            continue
        query = parse_qs(parsed.query)
        filename = unquote((query.get("filePreviewPath") or [""])[0]).strip()
        title = filename.rsplit("/", 1)[-1] or label.strip()
        citations.append(
            GenieCitation(
                citation_id=uri,
                title=title,
                uri=uri,
                snippet=label.strip() if label.strip() != title else "",
                source="genie_volume",
            )
        )
    return citations


def _markdown_table(value: str) -> tuple[list[str], list[list[Any]], bool]:
    lines = [line.strip() for line in value.splitlines() if line.strip().startswith("|")]
    if len(lines) < 2:
        return [], [], False

    def cells(line: str) -> list[str]:
        return [cell.strip() for cell in line.strip().strip("|").split("|")]

    columns = cells(lines[0])
    separator = cells(lines[1])
    if not columns or len(separator) != len(columns) or not all(
        re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in separator
    ):
        return [], [], False
    raw_rows = [cells(line) for line in lines[2:]]
    rows = [row[: len(columns)] for row in raw_rows if len(row) >= len(columns)]
    return columns, rows[:ROW_LIMIT], len(rows) > ROW_LIMIT


def _agent_output_text(item: Any) -> tuple[str, list[GenieCitation]]:
    if _text(_get(item, "type")).casefold() != "message":
        return "", []
    texts: list[str] = []
    citations: list[GenieCitation] = []
    for part in _values(_get(item, "content")):
        if _text(_get(part, "type")).casefold() not in {"output_text", "text"}:
            continue
        value = _text(_get(part, "text"))
        if value:
            texts.append(value)
            citations.extend(_volume_citations(value))
        citations.extend(_citations_from(part))
        for annotation in _values(_get(part, "annotations")):
            citation = _citation_from(annotation)
            if citation is not None:
                citations.append(citation)
    return "\n\n".join(texts).strip(), citations


def _function_output_text(item: Any) -> str:
    value = _get(item, "output")
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    try:
        return json.dumps(value, separators=(",", ":"), default=str)
    except TypeError:
        return _text(value)


def _message_identifier(item: Any) -> str:
    metadata = _get(item, "metadata")
    return _text(_get(metadata, "message_id") or _get(item, "id"))


async def ask_genie_agent(
    settings: Settings,
    *,
    question: str,
    conversation_id: str | None = None,
    workspace: WorkspaceClient | None = None,
    client: Any | None = None,
    view_role: str | None = "manager",
) -> GenieEvidenceEnvelope:
    """Use Genie Agent Mode for mixed structured-data and Volume-document evidence.

    Agent Mode is streamed even when a non-streaming response is requested. Only
    final messages, SQL function calls/results, citations, and terminal metadata
    are retained. Reasoning and unknown output items are deliberately discarded.
    """

    if not settings.genie_enabled:
        return _unavailable("GENIE_DISABLED", "Governed research is disabled.")

    owns_client = client is None
    try:
        workspace = workspace or await asyncio.to_thread(WorkspaceClient)
        space_id = await asyncio.to_thread(_resolve_space_id, workspace, settings)
        if not space_id:
            return _unavailable(
                "GENIE_SPACE_NOT_FOUND",
                "The governed research space is not available.",
            )
        if client is None:
            from databricks_openai import AsyncDatabricksOpenAI

            client = AsyncDatabricksOpenAI(workspace_client=workspace, max_retries=1)
            host = workspace.config.host
            host = host if host.startswith("http") else f"https://{host}"
            client.base_url = f"{host.rstrip('/')}/api/2.0/genie/agents/{space_id}"

        async def create_stream(active_conversation_id: str | None) -> Any:
            extra_body = (
                {"conversation_id": active_conversation_id}
                if active_conversation_id
                else {}
            )
            return await client.responses.create(
                model="genie-agent",
                input=[
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": question}],
                    }
                ],
                stream=True,
                extra_body=extra_body,
            )

        try:
            stream = await create_stream(conversation_id)
        except Exception as exc:
            if not conversation_id or not _is_not_found_error(exc):
                raise
            logger.warning(
                "Genie Agent Mode conversation was stale; retrying without prior state."
            )
            conversation_id = None
            stream = await create_stream(None)

        resolved_conversation_id = conversation_id or ""
        message_id = ""
        status = ""
        answer_by_item: dict[str, str] = {}
        citations: list[GenieCitation] = []
        sql_by_call: dict[str, GenieSqlAttachment] = {}
        call_order: list[str] = []
        failed = False

        def consume_response(response: Any) -> None:
            nonlocal resolved_conversation_id, status, message_id
            resolved_conversation_id = (
                _text(_get(response, "conversation_id")) or resolved_conversation_id
            )
            status = _enum_text(_get(response, "status")) or status
            for output_item in _values(_get(response, "output")):
                consume_item(output_item)

        def consume_item(item: Any) -> None:
            nonlocal message_id
            item_type = _text(_get(item, "type")).casefold()
            if item_type == "reasoning":
                return
            if item_type == "message":
                answer, item_citations = _agent_output_text(item)
                item_id = _text(_get(item, "id")) or f"message-{len(answer_by_item)}"
                if answer:
                    answer_by_item[item_id] = answer
                citations.extend(item_citations)
                message_id = _message_identifier(item) or message_id
                return
            if item_type == "function_call":
                arguments = _get(item, "arguments")
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                if not isinstance(arguments, dict):
                    arguments = {}
                sql = _text(arguments.get("sql"))
                if not sql:
                    return
                call_id = _text(_get(item, "call_id") or _get(item, "id"))
                call_id = call_id or f"sql-{len(call_order)}"
                if call_id not in sql_by_call:
                    call_order.append(call_id)
                sql_by_call[call_id] = GenieSqlAttachment(
                    attachment_id=call_id,
                    sql=sql,
                    description=_text(arguments.get("description") or arguments.get("title")),
                )
                return
            if item_type == "function_call_output":
                call_id = _text(_get(item, "call_id") or _get(item, "id"))
                output = _function_output_text(item)
                columns, rows, truncated = _markdown_table(output)
                if not call_id:
                    call_id = call_order[-1] if call_order else f"sql-{len(call_order)}"
                attachment = sql_by_call.get(call_id)
                if attachment is None:
                    attachment = GenieSqlAttachment(attachment_id=call_id)
                    sql_by_call[call_id] = attachment
                    call_order.append(call_id)
                attachment.columns = columns
                attachment.rows = rows
                attachment.truncated = truncated

        async for event in stream:
            event_type = _text(_get(event, "type") or _get(event, "event")).casefold()
            event_data = _get(event, "data")
            event_body = event_data if event_data is not None else event
            if event_type == "response.created":
                consume_response(_get(event_body, "response"))
            elif event_type == "response.output_item.done":
                consume_item(_get(event_body, "item"))
            elif event_type == "response.completed":
                consume_response(_get(event_body, "response"))
            elif event_type == "response.failed":
                failed = True
                consume_response(_get(event_body, "response"))

        answer = "\n\n".join(dict.fromkeys(answer_by_item.values())).strip()
        sql_attachments = [sql_by_call[key] for key in call_order]
        has_evidence = bool(answer or sql_attachments or citations)
        if failed or status == "FAILED":
            evidence_status = EvidenceStatus.PARTIAL if has_evidence else EvidenceStatus.ERROR
            error_code = "GENIE_REQUEST_FAILED"
            error_message = "The governed research request could not be completed."
        elif not has_evidence:
            evidence_status = EvidenceStatus.ERROR
            error_code = "EMPTY_RESPONSE"
            error_message = "The governed research request returned no usable evidence."
        else:
            evidence_status = EvidenceStatus.SUCCESS
            error_code = None
            error_message = None
        envelope = GenieEvidenceEnvelope(
            status=evidence_status,
            source="genie_agent_mode",
            answer=answer,
            conversation_id=resolved_conversation_id or None,
            message_id=message_id or None,
            citations=_dedupe_citations(citations),
            sql_attachments=sql_attachments,
            truncated=any(attachment.truncated for attachment in sql_attachments),
            error_code=error_code,
            error_message=error_message,
        )
        return project_evidence(envelope, view_role)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Genie Agent Mode request failed (%s).", type(exc).__name__)
        return GenieEvidenceEnvelope(
            status=EvidenceStatus.ERROR,
            source="genie_agent_mode",
            conversation_id=conversation_id,
            freshness=EvidenceFreshness(
                status="unavailable",
                detail="No live Genie evidence was retrieved.",
            ),
            error_code="GENIE_REQUEST_FAILED",
            error_message="The governed research service could not complete this request.",
        )
    finally:
        if owns_client and client is not None:
            try:
                await client.close()
            except Exception:  # pragma: no cover - shutdown remains best-effort
                logger.debug("Could not close the Genie Agent Mode client.", exc_info=True)


def project_evidence(
    evidence: GenieEvidenceEnvelope,
    view_role: str | None,
) -> GenieEvidenceEnvelope:
    """Return a role-safe copy while retaining the complete envelope for persistence."""

    if normalize_view_role(view_role) != "seller":
        return evidence.model_copy(deep=True)

    projected = evidence.model_copy(deep=True)
    projected.answer = _sanitize_seller_prose(
        projected.answer,
        replacement="Governed results are available; buy-side commercial details were withheld.",
    )
    for attachment in projected.sql_attachments:
        keep_indexes = [
            index
            for index, column in enumerate(attachment.columns)
            if not _is_sensitive_column(column)
        ]
        attachment.columns = [attachment.columns[index] for index in keep_indexes]
        attachment.rows = [
            [row[index] for index in keep_indexes if index < len(row)]
            for row in attachment.rows
        ]
        attachment.sql = ""
        attachment.description = ""
    for citation in projected.citations:
        citation.snippet = _sanitize_seller_prose(citation.snippet)
    projected.knowledge_fallback.answer = _sanitize_seller_prose(
        projected.knowledge_fallback.answer,
        replacement="Seller guidance is available; buy-side commercial details were withheld.",
    )
    return projected


def sku_values_from_evidence(evidence: GenieEvidenceEnvelope) -> set[str]:
    """Ground SKU values exclusively in cells from explicitly named `sku` columns."""

    result: set[str] = set()
    for attachment in evidence.sql_attachments:
        sku_indexes = [
            index
            for index, column in enumerate(attachment.columns)
            if _normal_column(column) == "sku"
        ]
        for row in attachment.rows:
            for index in sku_indexes:
                if index >= len(row) or row[index] is None:
                    continue
                sku = _text(row[index])
                if sku:
                    result.add(sku)
    return result


def _unavailable(code: str, message: str) -> GenieEvidenceEnvelope:
    return GenieEvidenceEnvelope(
        status=EvidenceStatus.UNAVAILABLE,
        freshness=EvidenceFreshness(
            status="unavailable",
            detail="No live Genie evidence was retrieved.",
        ),
        error_code=code,
        error_message=message,
    )


def ask_genie(
    settings: Settings,
    *,
    question: str,
    conversation_id: str | None = None,
    workspace: WorkspaceClient | None = None,
    wait_timeout: timedelta = GENIE_WAIT_TIMEOUT,
    view_role: str | None = "manager",
) -> GenieEvidenceEnvelope:
    """Ask one curated Genie space and return a bounded, typed evidence envelope.

    The supported Conversation API is intentionally used here. Unknown attachment
    kinds and internal reasoning are ignored; raw upstream errors never cross the API.
    """

    if not settings.genie_enabled:
        return _unavailable("GENIE_DISABLED", "Governed research is disabled.")
    try:
        workspace = workspace or WorkspaceClient()
        space_id = _resolve_space_id(workspace, settings)
        if not space_id:
            return _unavailable(
                "GENIE_SPACE_NOT_FOUND",
                "The governed research space is not available.",
            )
        if conversation_id:
            try:
                message = workspace.genie.create_message_and_wait(
                    space_id,
                    conversation_id,
                    question,
                    timeout=wait_timeout,
                )
            except Exception as exc:
                if not _is_not_found_error(exc):
                    raise
                logger.warning(
                    "Genie Conversation API state was stale; starting a fresh conversation."
                )
                conversation_id = None
                message = workspace.genie.start_conversation_and_wait(
                    space_id,
                    question,
                    timeout=wait_timeout,
                )
        else:
            message = workspace.genie.start_conversation_and_wait(
                space_id,
                question,
                timeout=wait_timeout,
            )

        resolved_conversation_id = _text(_get(message, "conversation_id"))
        message_id = _text(_get(message, "id") or _get(message, "message_id"))
        message_status = _enum_text(_get(message, "status"))
        texts: list[str] = []
        citations: list[GenieCitation] = []
        sql_attachments: list[GenieSqlAttachment] = []
        result_failed = False

        for attachment in _values(_get(message, "attachments")):
            text_attachment = _get(attachment, "text")
            content = _text(_get(text_attachment, "content"))
            if content:
                texts.append(content)
            citations.extend(_citations_from(attachment))
            citations.extend(_citations_from(text_attachment))

            query = _get(attachment, "query")
            if query is None:
                continue
            attachment_id = _text(_get(attachment, "attachment_id") or _get(attachment, "id"))
            columns: list[str] = []
            rows: list[list[Any]] = []
            truncated = False
            error_code: str | None = None
            if attachment_id and resolved_conversation_id and message_id:
                columns, rows, truncated, error_code = _extract_rows(
                    workspace,
                    space_id,
                    resolved_conversation_id,
                    message_id,
                    attachment_id,
                )
            else:
                error_code = "QUERY_RESULT_FAILED"
            result_failed = result_failed or error_code is not None
            sql_attachments.append(
                GenieSqlAttachment(
                    attachment_id=attachment_id,
                    sql=_text(_get(query, "query") or _get(query, "sql")),
                    description=_text(_get(query, "description")),
                    columns=columns,
                    rows=rows,
                    truncated=truncated,
                    error_code=error_code,
                )
            )

        answer = "\n\n".join(texts).strip().replace("**", "")
        if not answer:
            answer = next(
                (attachment.description for attachment in sql_attachments if attachment.description),
                "",
            )
        truncated = any(attachment.truncated for attachment in sql_attachments)
        terminal_error = message_status in {"FAILED", "CANCELLED"}
        if terminal_error and not (answer or sql_attachments):
            status = EvidenceStatus.ERROR
            error_code = "GENIE_REQUEST_FAILED"
            error_message = "The governed research request could not be completed."
        elif not (answer or sql_attachments):
            status = EvidenceStatus.ERROR
            error_code = "EMPTY_RESPONSE"
            error_message = "The governed research request returned no usable evidence."
        elif terminal_error or result_failed:
            status = EvidenceStatus.PARTIAL
            error_code = "QUERY_RESULT_FAILED" if result_failed else "GENIE_REQUEST_FAILED"
            error_message = "Some governed research evidence could not be retrieved."
        else:
            status = EvidenceStatus.SUCCESS
            error_code = None
            error_message = None

        envelope = GenieEvidenceEnvelope(
            status=status,
            answer=answer,
            conversation_id=resolved_conversation_id or conversation_id,
            message_id=message_id or None,
            citations=_dedupe_citations(citations),
            sql_attachments=sql_attachments,
            truncated=truncated,
            error_code=error_code,
            error_message=error_message,
        )
        return project_evidence(envelope, view_role)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Genie request failed (%s).", type(exc).__name__)
        return GenieEvidenceEnvelope(
            status=EvidenceStatus.ERROR,
            conversation_id=conversation_id,
            freshness=EvidenceFreshness(
                status="unavailable",
                detail="No live Genie evidence was retrieved.",
            ),
            error_code="GENIE_REQUEST_FAILED",
            error_message="The governed research service could not complete this request.",
        )
