"""知识库检索命中日志只读报表。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import aiosqlite

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.config import settings  # noqa: E402
from app.database import resolve_database_path  # noqa: E402
from app.repository.knowledge_repo import KnowledgeRepo  # noqa: E402
from app.service.knowledge_retrieval_report import (  # noqa: E402
    DEFAULT_RETRIEVAL_REPORT_LIMIT,
    build_retrieval_log_report,
)

TEXT_QUERY_MAX_LENGTH = 80


async def load_recent_logs(db_path: str, limit: int) -> list[object]:
    resolved_db_path = resolve_database_path(db_path)
    uri = _build_readonly_uri(resolved_db_path)
    conn = await aiosqlite.connect(uri, uri=True)
    conn.row_factory = aiosqlite.Row
    try:
        return await KnowledgeRepo(conn).list_recent_retrieval_logs(limit=limit)
    finally:
        await conn.close()


def build_report(logs: list[object], *, db_path: str, limit: int) -> dict[str, object]:
    return build_retrieval_log_report(
        logs,
        project_root=str(ROOT_DIR),
        database_path=str(resolve_database_path(db_path)),
        limit=limit,
    )


def print_text_report(report: dict[str, object]) -> None:
    summary = report["summary"]
    metadata = report["metadata"]
    print("knowledge_retrieval_logs_report status=ok")
    print(f"db={metadata['db']}")
    print(
        "total={total} hit={hit_count} no_match={no_match_count} "
        "no_match_rate={no_match_rate}".format(**summary)
    )
    print(
        "by_bot_type="
        + json.dumps(report["breakdown"]["by_bot_type"], ensure_ascii=False)
    )
    print(
        "by_audience="
        + json.dumps(report["breakdown"]["by_audience"], ensure_ascii=False)
    )
    print(
        "by_retrieval_mode="
        + json.dumps(report["breakdown"]["by_retrieval_mode"], ensure_ascii=False)
    )
    print("trend_by_date=" + json.dumps(report["trend"]["by_date"], ensure_ascii=False))
    print("recent:")
    for item in report["recent_logs"][:10]:
        query = _truncate_text(str(item["query"]), TEXT_QUERY_MAX_LENGTH)
        row = dict(item)
        row["query"] = query
        print(
            "[{id}] {created_at} {bot_type}/{audience} {retrieval_mode} "
            "count={result_count} fallback={fallback_reason} query={query}".format(
                **row,
            )
        )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Report knowledge retrieval logs")
    parser.add_argument("--db", default=settings.DB_PATH, help="SQLite 数据库路径")
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_RETRIEVAL_REPORT_LIMIT,
        help="读取最近 N 条",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        resolved_db_path = resolve_database_path(args.db)
        logs = await load_recent_logs(args.db, max(args.limit, 1))
    except aiosqlite.Error as exc:
        print(f"[ERROR] 读取知识检索日志失败: {exc}", file=sys.stderr)
        return 1
    payload = build_retrieval_log_report(
        logs,
        project_root=str(ROOT_DIR),
        database_path=str(resolved_db_path),
        limit=max(args.limit, 1),
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_text_report(payload)
    return 0


def _build_readonly_uri(db_path: str) -> str:
    if db_path == ":memory:":
        return db_path
    return Path(db_path).resolve().as_uri() + "?mode=ro"


def _truncate_text(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
