"""知识库检索命中日志 smoke 检查。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.database import close_db, init_db  # noqa: E402
from app.models.knowledge import KnowledgeAudience  # noqa: E402
from app.repository.knowledge_repo import KnowledgeRepo  # noqa: E402
from app.service.knowledge_retriever import KnowledgeRetriever  # noqa: E402
from app.service.knowledge_retrieval_logger import hash_retrieval_query  # noqa: E402

CUSTOMER_QUERY = "retrieval log customer sentinel"
EMPLOYEE_QUERY = "retrieval log employee sentinel"
MISSING_QUERY = "retrieval log missing sentinel"


@dataclass(frozen=True)
class RetrievalLogSmokeCheck:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


async def run_smoke_checks() -> list[RetrievalLogSmokeCheck]:
    conn = await init_db(":memory:")
    try:
        repo = KnowledgeRepo(conn)
        await _seed_entries(repo)
        await _run_retrievals(repo)
        logs = await repo.list_recent_retrieval_logs(limit=10)
        return _build_checks(logs)
    finally:
        await close_db(conn)


async def _seed_entries(repo: KnowledgeRepo) -> None:
    await repo.insert_entry(
        category="faq",
        title="retrieval-log-customer",
        content=CUSTOMER_QUERY,
        keywords=CUSTOMER_QUERY,
        priority=10,
        sync_source="retrieval_log_smoke",
        audience=KnowledgeAudience.CUSTOMER.value,
    )
    await repo.insert_entry(
        category="faq",
        title="retrieval-log-employee",
        content=EMPLOYEE_QUERY,
        keywords=EMPLOYEE_QUERY,
        priority=10,
        sync_source="retrieval_log_smoke",
        audience=KnowledgeAudience.EMPLOYEE.value,
    )


async def _run_retrievals(repo: KnowledgeRepo) -> None:
    customer_retriever = KnowledgeRetriever(
        repo,
        audience=KnowledgeAudience.CUSTOMER.value,
    )
    employee_retriever = KnowledgeRetriever(
        repo,
        audience=KnowledgeAudience.EMPLOYEE.value,
    )
    await customer_retriever.search_keyword_only(CUSTOMER_QUERY, limit=5)
    await employee_retriever.search_keyword_only(EMPLOYEE_QUERY, limit=5)
    await customer_retriever.search_keyword_only(MISSING_QUERY, limit=5)


def _build_checks(logs: list[object]) -> list[RetrievalLogSmokeCheck]:
    return [
        _check_log_present(
            "customer.hit_log_written",
            logs,
            query=CUSTOMER_QUERY,
            bot_type="customer",
            audience=KnowledgeAudience.CUSTOMER.value,
            expected_title="retrieval-log-customer",
        ),
        _check_log_present(
            "employee.hit_log_written",
            logs,
            query=EMPLOYEE_QUERY,
            bot_type="employee",
            audience=KnowledgeAudience.EMPLOYEE.value,
            expected_title="retrieval-log-employee",
        ),
        _check_no_match_log(logs),
        _check_bool(
            "log.count",
            len(logs) == 3,
            f"expected 3 logs, got {len(logs)}",
        ),
    ]


def _check_log_present(
    name: str,
    logs: list[object],
    *,
    query: str,
    bot_type: str,
    audience: str,
    expected_title: str,
) -> RetrievalLogSmokeCheck:
    for log in logs:
        if not _matches_log(log, query, bot_type, audience):
            continue
        titles = json.loads(str(log.matched_titles_json))
        return RetrievalLogSmokeCheck(
            name,
            expected_title in titles and log.result_count == 1,
            "" if expected_title in titles else f"titles={titles}",
        )
    return RetrievalLogSmokeCheck(name, False, "log missing")


def _matches_log(log: object, query: str, bot_type: str, audience: str) -> bool:
    return (
        getattr(log, "query_hash", "") == hash_retrieval_query(query)
        and getattr(log, "bot_type", "") == bot_type
        and getattr(log, "audience", "") == audience
    )


def _check_no_match_log(logs: list[object]) -> RetrievalLogSmokeCheck:
    for log in logs:
        if getattr(log, "query_hash", "") != hash_retrieval_query(MISSING_QUERY):
            continue
        passed = log.result_count == 0 and log.fallback_reason == "no_match"
        detail = (
            "" if passed else f"count={log.result_count} fallback={log.fallback_reason}"
        )
        return RetrievalLogSmokeCheck("fallback.no_match_logged", passed, detail)
    return RetrievalLogSmokeCheck("fallback.no_match_logged", False, "log missing")


def _check_bool(
    name: str,
    passed: bool,
    failure_detail: str,
) -> RetrievalLogSmokeCheck:
    return RetrievalLogSmokeCheck(name, passed, "" if passed else failure_detail)


def build_json_report(checks: list[RetrievalLogSmokeCheck]) -> dict[str, object]:
    failed_checks = [check for check in checks if not check.passed]
    return {
        "status": "passed" if not failed_checks else "failed",
        "metadata": {
            "generated_at": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "project_root": str(ROOT_DIR),
            "db": ":memory:",
            "llm": "disabled",
            "vector_search": "disabled",
        },
        "total": len(checks),
        "failed": len(failed_checks),
        "checks": [check.to_dict() for check in checks],
        "failed_names": [check.name for check in failed_checks],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check knowledge retrieval logs")
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    checks = await run_smoke_checks()
    report = build_json_report(checks)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"knowledge_retrieval_logs_smoke status={report['status']}")
        for check in checks:
            mark = "OK" if check.passed else "FAIL"
            print(f"[{mark}] {check.name} {check.detail}".rstrip())
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
