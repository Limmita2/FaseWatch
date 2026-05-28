from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.services.ai_service import ai_service


ALLOWED_TABLES = {
    "groups",
    "messages",
    "faces",
    "persons",
    "message_phones",
    "platform_states",
    "platform_group_links",
    "telegram_account_groups",
    "ai_chats",
    "ai_messages",
    "ai_reports",
}

FORBIDDEN_SQL_PATTERNS = (
    "alter",
    "call",
    "create",
    "delete",
    "drop",
    "execute",
    "grant",
    "insert",
    "load",
    "lock",
    "merge",
    "optimize",
    "replace",
    "repair",
    "revoke",
    "set",
    "show",
    "truncate",
    "unlock",
    "update",
    "use",
)

MAX_ROWS = 100


@dataclass
class SqlToolResult:
    sql: str
    rows: list[dict[str, Any]]
    row_count: int
    direct_answer: str | None = None


def _looks_like_database_question(question: str) -> bool:
    lowered = question.lower()
    markers = (
        "sql",
        "бд",
        "баз",
        "данн",
        "таблиц",
        "запис",
        "count",
        "select",
        "messages",
        "groups",
        "faces",
        "persons",
        "message_phones",
        "сколько",
        "кільк",
        "груп",
        "актив",
    )
    return any(marker in lowered for marker in markers)


def _build_deterministic_sql(question: str) -> str | None:
    lowered = question.lower()
    asks_count = any(marker in lowered for marker in ("сколько", "кільк", "count", "количество", "запис", "скіл", "скол"))
    active_groups_sql = _build_active_groups_sql(question)
    if active_groups_sql and (asks_count or "актив" in lowered):
        return active_groups_sql

    if not asks_count:
        return None

    group_stats_sql = _build_group_stats_sql(question)
    if group_stats_sql:
        return group_stats_sql

    if "person_id" in lowered:
        return (
            "SELECT COUNT(*) AS faces_with_person_id, "
            "COUNT(DISTINCT person_id) AS unique_person_id "
            "FROM faces WHERE person_id IS NOT NULL"
        )

    for table in sorted(ALLOWED_TABLES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(table)}\b", lowered):
            return f"SELECT COUNT(*) AS total_records FROM {table}"
    return None


def _build_active_groups_sql(question: str) -> str | None:
    lowered = question.lower()
    if not any(marker in lowered for marker in ("груп", "group", "чат", "канал")):
        return None
    if not any(marker in lowered for marker in ("актив", "active")):
        return None
    if not any(marker in lowered for marker in ("24", "сут", "доб", "день", "останні", "послед", "годин", "час")):
        return None

    return (
        "SELECT "
        "COUNT(DISTINCT m.group_id) AS active_groups, "
        "COUNT(m.id) AS messages_24h, "
        "COUNT(DISTINCT CASE WHEN m.has_photo THEN m.id END) AS photos_24h, "
        "GROUP_CONCAT(DISTINCT g.name ORDER BY g.name SEPARATOR ', ') AS group_names "
        "FROM messages m "
        "JOIN groups g ON g.id = m.group_id "
        "WHERE m.timestamp >= UTC_TIMESTAMP() - INTERVAL 24 HOUR"
    )


def _build_group_stats_sql(question: str) -> str | None:
    lowered = question.lower()
    if not any(marker in lowered for marker in ("груп", "group", "канал", "чат")):
        return None

    match = re.search(r"(?<!\d)-?\d{6,20}(?!\d)", question)
    if not match:
        return None

    group_ref = match.group(0)
    telegram_id_filter = ""
    if re.fullmatch(r"-?\d+", group_ref):
        telegram_id_filter = f"g.telegram_id = {int(group_ref)} OR "

    return (
        "SELECT "
        "CAST(g.id AS CHAR) AS group_id, "
        "g.name AS group_name, "
        "g.telegram_id AS telegram_id, "
        "g.external_id AS external_id, "
        "COUNT(DISTINCT m.id) AS objects_total, "
        "COUNT(DISTINCT CASE WHEN m.has_photo THEN m.id END) AS photos_total, "
        "COUNT(DISTINCT f.id) AS faces_total, "
        "COUNT(DISTINCT CASE WHEN f.person_id IS NOT NULL THEN f.id END) AS faces_with_person_id, "
        "COUNT(DISTINCT f.person_id) AS unique_person_id "
        "FROM groups g "
        "LEFT JOIN messages m ON m.group_id = g.id "
        "LEFT JOIN faces f ON f.message_id = m.id "
        f"WHERE {telegram_id_filter}g.external_id = '{group_ref}' "
        "GROUP BY g.id, g.name, g.telegram_id, g.external_id"
    )


def _column_type(column) -> str:
    return column.type.compile() if hasattr(column.type, "compile") else str(column.type)


def build_readonly_schema_prompt() -> str:
    lines = [
        "БД FaceWatch — MariaDB. Доступна тільки аналітична read-only БД.",
        "Дозволено тільки один SQL-запит SELECT або WITH.",
        "Синтаксис MariaDB: INTERVAL N HOUR/DAY, NOW(), DATE_SUB(), GROUP_CONCAT().",
        "НЕ використовуй PostgreSQL синтаксис (::, INTERVAL '1 hour', generate_series тощо).",
        "Дозволені таблиці та колонки:",
    ]
    for table in sorted(Base.metadata.sorted_tables, key=lambda item: item.name):
        if table.name not in ALLOWED_TABLES:
            continue
        columns = ", ".join(f"{column.name} {_column_type(column)}" for column in table.columns)
        lines.append(f"- {table.name}: {columns}")
    return "\n".join(lines)


def _extract_json_object(value: str) -> dict[str, Any] | None:
    value = re.sub(r"<think>.*?</think>", "", value, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", value, flags=re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_sql(sql: str) -> str:
    sql = re.sub(r"<think>.*?</think>", "", sql, flags=re.IGNORECASE | re.DOTALL).strip()
    sql = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE).strip()
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL).strip()
    if sql.endswith(";"):
        sql = sql[:-1].strip()
    return sql


def _referenced_tables(sql: str) -> set[str]:
    tables: set[str] = set()
    for match in re.finditer(r"\b(?:from|join)\s+`?([a-zA-Z_][\w]*)`?", sql, flags=re.IGNORECASE):
        tables.add(match.group(1).lower())
    return tables


def validate_readonly_sql(sql: str) -> str:
    normalized = _normalize_sql(sql)
    lowered = normalized.lower()
    if not lowered:
        raise ValueError("empty SQL")
    if ";" in normalized:
        raise ValueError("only one SQL statement is allowed")
    if not (lowered.startswith("select ") or lowered.startswith("with ")):
        raise ValueError("only SELECT/WITH queries are allowed")
    for keyword in FORBIDDEN_SQL_PATTERNS:
        if re.search(rf"\b{keyword}\b", lowered):
            raise ValueError(f"forbidden SQL keyword: {keyword}")

    referenced = _referenced_tables(normalized)
    unknown = referenced - ALLOWED_TABLES
    if unknown:
        raise ValueError(f"table is not allowed: {', '.join(sorted(unknown))}")
    if not referenced:
        raise ValueError("query must reference an allowed table")

    if " limit " not in lowered and "count(" not in lowered:
        normalized = f"{normalized} LIMIT {MAX_ROWS}"
    return normalized


async def build_sql_for_question(question: str) -> str | None:
    if not _looks_like_database_question(question):
        return None
    deterministic_sql = _build_deterministic_sql(question)
    if deterministic_sql:
        return validate_readonly_sql(deterministic_sql)

    prompt = f"""
{build_readonly_schema_prompt()}

Вопрос пользователя:
{question}

Если для ответа нужен SQL-запрос к БД, верни строго JSON:
{{"needs_sql": true, "sql": "SELECT ..."}}

Если SQL не нужен, верни строго JSON:
{{"needs_sql": false, "sql": ""}}

Не добавляй markdown и пояснения.
"""
    content = await ai_service.generate(prompt.strip())
    parsed = _extract_json_object(content)
    if not parsed or not parsed.get("needs_sql"):
        return None
    sql = str(parsed.get("sql") or "")
    return validate_readonly_sql(sql)


async def execute_readonly_sql(db: AsyncSession, sql: str) -> SqlToolResult:
    result = await db.execute(text(sql))
    keys = list(result.keys())
    rows = result.fetchmany(MAX_ROWS)
    serialized = [dict(zip(keys, row)) for row in rows]
    sql_result = SqlToolResult(sql=sql, rows=serialized, row_count=len(serialized))
    sql_result.direct_answer = _format_direct_answer(sql_result)
    return sql_result


async def maybe_answer_with_sql(db: AsyncSession, question: str) -> SqlToolResult | None:
    try:
        sql = await build_sql_for_question(question)
        if not sql:
            return None
        return await execute_readonly_sql(db, sql)
    except Exception:
        return None


def _fmt_count(value: Any) -> str:
    if value is None:
        return "0"
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(value)


def _format_direct_answer(result: SqlToolResult) -> str | None:
    if not result.rows:
        if "FROM groups g" in result.sql and "objects_total" in result.sql:
            return "Група не знайдена за вказаним ID."
        return None

    row = result.rows[0]
    if "active_groups" in row and "group_names" in row:
        names = row.get("group_names") or "—"
        return (
            "За останні 24 години:\n"
            f"- активних груп: {_fmt_count(row.get('active_groups'))}\n"
            f"- повідомлень: {_fmt_count(row.get('messages_24h'))}\n"
            f"- фото: {_fmt_count(row.get('photos_24h'))}\n"
            f"- групи: {names}"
        )

    if {"group_name", "objects_total", "photos_total", "faces_total", "faces_with_person_id", "unique_person_id"} <= row.keys():
        group_label = row.get("group_name") or row.get("external_id") or row.get("group_id")
        tg_id = row.get("telegram_id") or row.get("external_id") or "—"
        return (
            f"Група `{group_label}` (`{tg_id}`):\n"
            f"- всього об'єктів/повідомлень: {_fmt_count(row.get('objects_total'))}\n"
            f"- фотографій: {_fmt_count(row.get('photos_total'))}\n"
            f"- знайдених облич: {_fmt_count(row.get('faces_total'))}\n"
            f"- облич з person_id: {_fmt_count(row.get('faces_with_person_id'))}\n"
            f"- унікальних person_id: {_fmt_count(row.get('unique_person_id'))}"
        )

    if {"faces_with_person_id", "unique_person_id"} <= row.keys():
        return (
            f"У всій базі FaceWatch:\n"
            f"- облич з person_id: {_fmt_count(row.get('faces_with_person_id'))}\n"
            f"- унікальних person_id: {_fmt_count(row.get('unique_person_id'))}"
        )
    return None
