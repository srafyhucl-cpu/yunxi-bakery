"""后台知识检索命中报表 API 测试。"""

import pytest

from app.api.admin.knowledge_retrieval_report import (
    create_admin_knowledge_retrieval_report_router,
)
from app.database import close_db, init_db
from app.models.knowledge import KnowledgeAudience
from app.repository.knowledge_repo import KnowledgeRepo
from app.service.knowledge_retrieval_report import KnowledgeRetrievalReportService
from app.service.knowledge_retriever import KnowledgeRetriever

CUSTOMER_QUERY = "admin report customer sentinel"
MISSING_QUERY = "admin report missing sentinel"


def _get_route_endpoint(router, path: str, method: str):
    for route in router.routes:
        if getattr(route, "path", "") == path and method in getattr(
            route, "methods", set()
        ):
            return route.endpoint
    raise AssertionError(f"Route not found: {method} {path}")


@pytest.mark.asyncio
async def test_admin_knowledge_retrieval_report_summary_returns_report() -> None:
    db = await init_db(":memory:")
    try:
        repo = KnowledgeRepo(db)
        await repo.insert_entry(
            category="faq",
            title="admin-report-customer",
            content=CUSTOMER_QUERY,
            keywords=CUSTOMER_QUERY,
            priority=10,
            sync_source="admin_report_test",
            audience=KnowledgeAudience.CUSTOMER.value,
        )
        retriever = KnowledgeRetriever(repo, audience=KnowledgeAudience.CUSTOMER.value)
        await retriever.search_keyword_only(CUSTOMER_QUERY)
        await retriever.search_keyword_only(MISSING_QUERY)
        router = create_admin_knowledge_retrieval_report_router(
            KnowledgeRetrievalReportService(repo)
        )
        endpoint = _get_route_endpoint(
            router,
            "/api/v1/admin/knowledge-retrieval-report/summary",
            "GET",
        )

        payload = await endpoint(limit=10)

        assert payload["code"] == 0
        assert payload["data"]["summary"] == {
            "total": 2,
            "hit_count": 1,
            "no_match_count": 1,
            "no_match_rate": 0.5,
        }
        assert payload["data"]["breakdown"]["by_audience"] == {"customer": 2}
        assert payload["data"]["top_no_match_queries"] == [
            {"query_category": "other", "count": 1}
        ]
    finally:
        await close_db(db)
