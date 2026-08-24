import pytest
from fastapi import Request

from app.api.admin_knowledge import create_admin_knowledge_router
from app.config import settings
from app.database import close_db, init_db
from app.repository.content_change_history_repo import ContentChangeHistoryRepo
from app.repository.knowledge_admin_repo import KnowledgeAdminRepo
from app.repository.knowledge_repo import KnowledgeRepo
from app.service.knowledge_admin import KnowledgeAdminService
from app.service.knowledge_sync import KnowledgeSyncService


class _FakeModel:
    def encode(self, texts, normalize_embeddings=True):  # noqa: ARG002
        return [[0.1, 0.2, 0.3] for _ in texts]


class _FakeEmbeddingSearcher:
    def _get_model(self):
        return _FakeModel()

    async def upsert_one(self, key: str, vector: list[float]) -> None:  # noqa: ARG002
        return None

    async def delete_one(self, key: str) -> None:  # noqa: ARG002
        return None


def _get_route_endpoint(router, path: str, method: str):
    for route in router.routes:
        if getattr(route, "path", "") == path and method in getattr(
            route, "methods", set()
        ):
            return route.endpoint
    raise AssertionError(f"Route not found: {method} {path}")


def _build_request(
    path: str, method: str = "GET", cookies: dict | None = None, body: bytes = b""
) -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [(b"content-type", b"application/json")],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "scheme": "http",
    }

    async def receive() -> dict:
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(scope, receive=receive)
    request._cookies = cookies or {}
    return request


@pytest.mark.asyncio
async def test_admin_knowledge_api_create_and_detail() -> None:
    db = await init_db(":memory:")
    repo = KnowledgeRepo(db)
    history_repo = ContentChangeHistoryRepo(db)
    router = create_admin_knowledge_router(
        KnowledgeAdminService(
            knowledge_repo=repo,
            admin_repo=KnowledgeAdminRepo(db),
            history_repo=history_repo,
            sync_service=KnowledgeSyncService(
                repo, history_repo, _FakeEmbeddingSearcher()
            ),
        )
    )
    create_endpoint = _get_route_endpoint(
        router, "/api/v1/admin/knowledge-config/entries", "POST"
    )
    detail_endpoint = _get_route_endpoint(
        router, "/api/v1/admin/knowledge-config/entries/{entry_id}", "GET"
    )

    request = _build_request(
        "/api/v1/admin/knowledge-config/entries",
        method="POST",
        body=(
            '{"title":"配送说明","content":"主城区当日配送","content_type":"faq",'
            '"keywords":"配送","priority":50,"is_active":true,'
            '"audience":"customer","review_status":"published",'
            '"valid_from":"2026-07-06 09:00:00","valid_until":"2026-07-31 23:59:59"}'
        ).encode("utf-8"),
    )
    created = await create_endpoint(
        request=request,
        authorization=f"Bearer {settings.ADMIN_API_TOKEN}",
    )

    assert created["code"] == 0
    assert created["data"]["vector_sync_status"] == "success"
    assert created["data"]["audience"] == "customer"
    assert created["data"]["review_status"] == "published"
    assert created["data"]["valid_from"] == "2026-07-06 09:00:00"
    assert created["data"]["valid_until"] == "2026-07-31 23:59:59"
    assert created["data"]["reviewed_by"] == "admin"
    assert created["data"]["reviewed_at"]

    detail = await detail_endpoint(
        entry_id=created["data"]["id"],
        authorization=f"Bearer {settings.ADMIN_API_TOKEN}",
    )
    assert detail["code"] == 0
    assert detail["data"]["entry"]["title"] == "配送说明"
    assert detail["data"]["entry"]["audience"] == "customer"
    assert detail["data"]["entry"]["review_status"] == "published"
    assert len(detail["data"]["history"]) == 1
    await close_db(db)
