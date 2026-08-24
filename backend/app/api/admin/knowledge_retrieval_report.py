"""知识检索命中日志后台只读报表路由。"""

from fastapi import APIRouter, Depends, Header

from app.api.admin import verify_token
from app.service.knowledge_retrieval_report import (
    DEFAULT_RETRIEVAL_REPORT_LIMIT,
    KnowledgeRetrievalReportService,
)


def create_admin_knowledge_retrieval_report_router(
    service: KnowledgeRetrievalReportService,
) -> APIRouter:
    """创建知识检索命中报表后台路由。"""
    root_router = APIRouter()
    api_router = APIRouter(
        prefix="/api/v1/admin/knowledge-retrieval-report",
        tags=["admin-knowledge-retrieval-report-api"],
        dependencies=[Depends(verify_token)],
    )

    @api_router.get("/summary")
    async def summary_api(
        authorization: str | None = Header(default=None),
        limit: int = DEFAULT_RETRIEVAL_REPORT_LIMIT,
    ) -> dict:
        report = await service.build_recent_report(limit)
        return {"code": 0, "data": report}

    root_router.include_router(api_router)
    return root_router
