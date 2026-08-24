"""知识检索命中日志报表服务测试。"""

from app.service.knowledge_retrieval_report import (
    MAX_RETRIEVAL_REPORT_LIMIT,
    KnowledgeRetrievalReportService,
    build_retrieval_log_report,
    normalize_report_limit,
)


class _FakeLog:
    def __init__(
        self,
        *,
        created_at: str,
        bot_type: str = "customer",
        audience: str = "customer",
        query: str = "query",
        fallback_reason: str = "",
    ) -> None:
        self.id = 1
        self.created_at = created_at
        self.bot_type = bot_type
        self.audience = audience
        self.query = query
        self.retrieval_mode = "keyword_only"
        self.result_count = 0 if fallback_reason else 1
        self.fallback_reason = fallback_reason
        self.matched_entry_ids_json = "[1]"
        self.matched_titles_json = '["知识"]'


class _FakeRepo:
    def __init__(self, logs: list[object]) -> None:
        self.logs = logs
        self.requested_limit = 0

    async def list_recent_retrieval_logs(self, limit: int) -> list[object]:
        self.requested_limit = limit
        return self.logs[:limit]


def test_build_retrieval_log_report_summarizes_and_groups_trend() -> None:
    report = build_retrieval_log_report(
        [
            _FakeLog(created_at="2026-07-06 10:00:00", query="命中"),
            _FakeLog(
                created_at="2026-07-06 11:00:00",
                query="缺口",
                fallback_reason="no_match",
            ),
            _FakeLog(
                created_at="2026-07-05 09:00:00",
                bot_type="employee",
                audience="employee",
                query="缺口",
                fallback_reason="no_match",
            ),
        ],
        project_root="D:/Project/YunxiBakeBot",
        database_path="data/bot.db",
        limit=10,
    )

    assert report["summary"] == {
        "total": 3,
        "hit_count": 1,
        "no_match_count": 2,
        "no_match_rate": 0.6667,
    }
    assert report["breakdown"]["by_bot_type"] == {"customer": 2, "employee": 1}
    assert report["trend"]["by_date"][0]["date"] == "2026-07-06"
    assert report["trend"]["by_date"][0]["no_match_rate"] == 0.5
    assert report["top_no_match_queries"] == [{"query_category": "缺口", "count": 2}]
    assert report["recent_logs"][0]["matched_titles"] == ["知识"]


async def test_report_service_normalizes_limit_before_query() -> None:
    repo = _FakeRepo([_FakeLog(created_at="2026-07-06 10:00:00")])
    service = KnowledgeRetrievalReportService(repo)

    report = await service.build_recent_report(MAX_RETRIEVAL_REPORT_LIMIT + 1)

    assert repo.requested_limit == MAX_RETRIEVAL_REPORT_LIMIT
    assert report["metadata"]["limit"] == MAX_RETRIEVAL_REPORT_LIMIT


def test_normalize_report_limit_bounds_value() -> None:
    assert normalize_report_limit(0) == 1
    assert normalize_report_limit(5) == 5
    assert normalize_report_limit(MAX_RETRIEVAL_REPORT_LIMIT + 1) == (
        MAX_RETRIEVAL_REPORT_LIMIT
    )
