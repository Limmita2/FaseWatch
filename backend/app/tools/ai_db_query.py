from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from app.core.database import AsyncSessionLocal, engine
from app.services.ai_sql_service import execute_readonly_sql, maybe_answer_with_sql, validate_readonly_sql


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _print_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("0 rows")
        return

    keys = list(rows[0].keys())
    widths = {
        key: min(max(len(key), *(len(_as_text(row.get(key))) for row in rows)), 80)
        for key in keys
    }
    print("\t".join(key.ljust(widths[key]) for key in keys))
    for row in rows:
        print("\t".join(_as_text(row.get(key))[: widths[key]].ljust(widths[key]) for key in keys))


async def _run(question: str | None, sql: str | None, as_json: bool) -> int:
    async with AsyncSessionLocal() as db:
        if sql:
            result = await execute_readonly_sql(db, validate_readonly_sql(sql))
        elif question:
            result = await maybe_answer_with_sql(db, question)
            if not result:
                print("Не вдалося побудувати read-only SQL для цього питання.")
                return 2
        else:
            print("Вкажіть питання або --sql.")
            return 2

        if as_json:
            print(json.dumps(result.__dict__, ensure_ascii=False, default=str, indent=2))
        elif result.direct_answer:
            print(result.direct_answer)
        else:
            print(result.sql)
            _print_rows(result.rows)
        return 0


async def _main() -> int:
    parser = argparse.ArgumentParser(description="FaceWatch read-only DB helper for AI/CLI usage.")
    parser.add_argument("question", nargs="*", help="Natural-language question in Russian/Ukrainian.")
    parser.add_argument("--sql", help="Validated read-only SELECT/WITH query.")
    parser.add_argument("--json", action="store_true", help="Print raw result as JSON.")
    args = parser.parse_args()

    try:
        question = " ".join(args.question).strip() or None
        return await _run(question, args.sql, args.json)
    finally:
        await engine.dispose()


def main() -> None:
    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
