"""知识库 audience 和有效期治理 smoke 检查。"""

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
from app.models.knowledge import KnowledgeAudience, KnowledgeReviewStatus  # noqa: E402
from app.repository.knowledge_repo import KnowledgeRepo  # noqa: E402
from app.service.knowledge_retriever import KnowledgeRetriever  # noqa: E402

QUERY = "governance sentinel"
VALID_FROM_PAST = "2000-01-01 00:00:00"
VALID_UNTIL_PAST = "2000-01-02 00:00:00"
VALID_UNTIL_FUTURE = "2999-12-31 23:59:59"

EXPECTED_DEFAULT_TITLES = {
    "governance-shared-valid",
    "governance-window-valid",
}
EXPECTED_CUSTOMER_TITLES = {
    "governance-shared-valid",
    "governance-customer-valid",
    "governance-window-valid",
}
EXPECTED_EMPLOYEE_TITLES = {
    "governance-shared-valid",
    "governance-employee-valid",
    "governance-window-valid",
}
HIDDEN_TITLES = {
    "governance-draft-hidden",
    "governance-archived-hidden",
    "governance-expired-hidden",
    "governance-future-hidden",
}


@dataclass(frozen=True)
class GovernanceSmokeCheck:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


async def run_smoke_checks() -> list[GovernanceSmokeCheck]:
    conn = await init_db(":memory:")
    try:
        repo = KnowledgeRepo(conn)
        await _seed_governance_entries(repo)
        results = await _search_by_audience(repo)
        return _build_checks(results)
    finally:
        await close_db(conn)


async def _seed_governance_entries(repo: KnowledgeRepo) -> None:
    await _insert_fixture_entry(repo, "governance-shared-valid")
    await _insert_fixture_entry(
        repo,
        "governance-customer-valid",
        audience=KnowledgeAudience.CUSTOMER.value,
    )
    await _insert_fixture_entry(
        repo,
        "governance-employee-valid",
        audience=KnowledgeAudience.EMPLOYEE.value,
    )
    await _insert_fixture_entry(
        repo,
        "governance-draft-hidden",
        review_status=KnowledgeReviewStatus.DRAFT.value,
    )
    await _insert_fixture_entry(
        repo,
        "governance-archived-hidden",
        review_status=KnowledgeReviewStatus.ARCHIVED.value,
    )
    await _insert_fixture_entry(
        repo,
        "governance-expired-hidden",
        valid_from=VALID_FROM_PAST,
        valid_until=VALID_UNTIL_PAST,
    )
    await _insert_fixture_entry(
        repo,
        "governance-future-hidden",
        valid_from=VALID_UNTIL_FUTURE,
    )
    await _insert_fixture_entry(
        repo,
        "governance-window-valid",
        valid_from=VALID_FROM_PAST,
        valid_until=VALID_UNTIL_FUTURE,
    )


async def _insert_fixture_entry(
    repo: KnowledgeRepo,
    title: str,
    *,
    audience: str = KnowledgeAudience.ALL.value,
    review_status: str = KnowledgeReviewStatus.PUBLISHED.value,
    valid_from: str = "",
    valid_until: str = "",
) -> None:
    await repo.insert_entry(
        category="faq",
        title=title,
        content=f"{title} {QUERY}",
        keywords=QUERY,
        priority=10,
        sync_source="governance_smoke",
        audience=audience,
        review_status=review_status,
        valid_from=valid_from,
        valid_until=valid_until,
    )


async def _search_by_audience(
    repo: KnowledgeRepo,
) -> dict[str, set[str]]:
    default_retriever = KnowledgeRetriever(repo)
    customer_retriever = KnowledgeRetriever(
        repo,
        audience=KnowledgeAudience.CUSTOMER.value,
    )
    employee_retriever = KnowledgeRetriever(
        repo,
        audience=KnowledgeAudience.EMPLOYEE.value,
    )
    return {
        "default": {
            entry.title
            for entry in await default_retriever.search_keyword_only(QUERY, limit=20)
        },
        "customer": {
            entry.title
            for entry in await customer_retriever.search_keyword_only(QUERY, limit=20)
        },
        "employee": {
            entry.title
            for entry in await employee_retriever.search_keyword_only(QUERY, limit=20)
        },
    }


def _build_checks(results: dict[str, set[str]]) -> list[GovernanceSmokeCheck]:
    all_returned_titles = set().union(*results.values())
    return [
        _check_titles(
            "audience.default_all_only",
            results["default"],
            EXPECTED_DEFAULT_TITLES,
        ),
        _check_titles(
            "audience.customer_all_plus_customer",
            results["customer"],
            EXPECTED_CUSTOMER_TITLES,
        ),
        _check_titles(
            "audience.employee_all_plus_employee",
            results["employee"],
            EXPECTED_EMPLOYEE_TITLES,
        ),
        _check_absent(
            "governance.hidden_entries_excluded",
            all_returned_titles,
            HIDDEN_TITLES,
        ),
        _check_bool(
            "validity.window_entry_visible",
            "governance-window-valid" in all_returned_titles,
            "valid window entry missing",
        ),
    ]


def _check_titles(
    name: str,
    actual: set[str],
    expected: set[str],
) -> GovernanceSmokeCheck:
    if actual == expected:
        return GovernanceSmokeCheck(name, True)
    return GovernanceSmokeCheck(
        name,
        False,
        f"expected={sorted(expected)} actual={sorted(actual)}",
    )


def _check_absent(
    name: str,
    actual: set[str],
    hidden: set[str],
) -> GovernanceSmokeCheck:
    leaked = sorted(actual & hidden)
    return GovernanceSmokeCheck(
        name,
        not leaked,
        "" if not leaked else f"leaked={leaked}",
    )


def _check_bool(name: str, passed: bool, failure_detail: str) -> GovernanceSmokeCheck:
    return GovernanceSmokeCheck(name, passed, "" if passed else failure_detail)


def build_json_report(checks: list[GovernanceSmokeCheck]) -> dict[str, object]:
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
    parser = argparse.ArgumentParser(
        description="Check knowledge audience and validity governance"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    checks = await run_smoke_checks()
    report = build_json_report(checks)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"knowledge_audience_governance_smoke status={report['status']}")
        for check in checks:
            mark = "OK" if check.passed else "FAIL"
            print(f"[{mark}] {check.name} {check.detail}".rstrip())
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
