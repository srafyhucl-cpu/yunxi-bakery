"""知识库检索命中日志报表脚本测试。"""

import json

import pytest

from app.database import close_db, init_db
from app.models.knowledge import KnowledgeAudience
from app.repository.knowledge_repo import KnowledgeRepo
from app.service.knowledge_retriever import KnowledgeRetriever
from scripts import report_knowledge_retrieval_logs as report_script

CUSTOMER_QUERY = "report customer sentinel"
EMPLOYEE_QUERY = "report employee sentinel"
MISSING_QUERY = "report missing sentinel"


@pytest.mark.asyncio
async def test_retrieval_log_report_summarizes_hits_and_no_match(tmp_path) -> None:
    db_path = tmp_path / "retrieval-report.db"
    conn = await init_db(str(db_path))
    try:
        repo = KnowledgeRepo(conn)
        await _seed_report_entries(repo)
        await _run_report_retrievals(repo)
    finally:
        await close_db(conn)

    logs = await report_script.load_recent_logs(str(db_path), limit=20)
    report = report_script.build_report(logs, db_path=str(db_path), limit=20)

    assert report["status"] == "ok"
    assert report["summary"] == {
        "total": 3,
        "hit_count": 2,
        "no_match_count": 1,
        "no_match_rate": 0.3333,
    }
    assert report["breakdown"]["by_bot_type"] == {"customer": 2, "employee": 1}
    assert report["breakdown"]["by_audience"] == {"customer": 2, "employee": 1}
    assert report["breakdown"]["by_fallback_reason"] == {"no_match": 1}
    assert report["trend"]["by_date"][0] == {
        "date": report["recent_logs"][0]["created_at"][:10],
        "total": 3,
        "hit_count": 2,
        "no_match_count": 1,
        "no_match_rate": 0.3333,
    }
    assert report["top_no_match_queries"] == [{"query_category": "other", "count": 1}]
    assert report["recent_logs"][0]["query"] == ""


def test_retrieval_log_report_handles_bad_json() -> None:
    class BadLog:
        id = 1
        created_at = "2026-07-06 00:00:00"
        bot_type = "customer"
        audience = "customer"
        query = "bad json"
        retrieval_mode = "keyword_only"
        result_count = 1
        fallback_reason = ""
        matched_entry_ids_json = "{"
        matched_titles_json = "{"

    report = report_script.build_report([BadLog()], db_path=":memory:", limit=1)

    assert report["summary"]["hit_count"] == 1
    assert report["recent_logs"][0]["matched_entry_ids"] == []
    assert report["recent_logs"][0]["matched_titles"] == []


def test_retrieval_log_report_groups_daily_trend() -> None:
    class Log:
        def __init__(self, created_at: str, fallback_reason: str = "") -> None:
            self.id = 1
            self.created_at = created_at
            self.bot_type = "customer"
            self.audience = "customer"
            self.query = "trend"
            self.retrieval_mode = "keyword_only"
            self.result_count = 0 if fallback_reason else 1
            self.fallback_reason = fallback_reason
            self.matched_entry_ids_json = "[]"
            self.matched_titles_json = "[]"

    report = report_script.build_report(
        [
            Log("2026-07-06 10:00:00"),
            Log("2026-07-06 11:00:00", "no_match"),
            Log("2026-07-05 09:00:00", "no_match"),
        ],
        db_path=":memory:",
        limit=10,
    )

    assert report["trend"]["by_date"] == [
        {
            "date": "2026-07-06",
            "total": 2,
            "hit_count": 1,
            "no_match_count": 1,
            "no_match_rate": 0.5,
        },
        {
            "date": "2026-07-05",
            "total": 1,
            "hit_count": 0,
            "no_match_count": 1,
            "no_match_rate": 1.0,
        },
    ]


@pytest.mark.asyncio
async def test_retrieval_log_report_main_outputs_json(tmp_path, capsys) -> None:
    db_path = tmp_path / "retrieval-report-main.db"
    conn = await init_db(str(db_path))
    try:
        repo = KnowledgeRepo(conn)
        await _seed_report_entries(repo)
        await KnowledgeRetriever(
            repo,
            audience=KnowledgeAudience.CUSTOMER.value,
        ).search_keyword_only(CUSTOMER_QUERY)
    finally:
        await close_db(conn)

    exit_code = await report_script.main(
        ["--db", str(db_path), "--limit", "5", "--json"]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["summary"]["total"] == 1
    assert payload["recent_logs"][0]["matched_titles"] == ["report-customer"]


async def _seed_report_entries(repo: KnowledgeRepo) -> None:
    await repo.insert_entry(
        category="faq",
        title="report-customer",
        content=CUSTOMER_QUERY,
        keywords=CUSTOMER_QUERY,
        priority=10,
        sync_source="retrieval_report_test",
        audience=KnowledgeAudience.CUSTOMER.value,
    )
    await repo.insert_entry(
        category="faq",
        title="report-employee",
        content=EMPLOYEE_QUERY,
        keywords=EMPLOYEE_QUERY,
        priority=10,
        sync_source="retrieval_report_test",
        audience=KnowledgeAudience.EMPLOYEE.value,
    )


async def _run_report_retrievals(repo: KnowledgeRepo) -> None:
    await KnowledgeRetriever(
        repo,
        audience=KnowledgeAudience.CUSTOMER.value,
    ).search_keyword_only(CUSTOMER_QUERY)
    await KnowledgeRetriever(
        repo,
        audience=KnowledgeAudience.EMPLOYEE.value,
    ).search_keyword_only(EMPLOYEE_QUERY)
    await KnowledgeRetriever(
        repo,
        audience=KnowledgeAudience.CUSTOMER.value,
    ).search_keyword_only(MISSING_QUERY)
