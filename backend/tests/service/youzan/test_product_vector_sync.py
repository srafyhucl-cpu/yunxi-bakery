from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from app.models.content_change_history import SyncSource, WriteResult
from app.repository.config_repo import ConfigRepo
from app.repository.knowledge_repo import KnowledgeRepo
from app.repository.knowledge_product_repo import KnowledgeProductRepo
from app.service.knowledge_retriever import KnowledgeRetriever
from app.service.youzan.event_handler import YouzanEventHandler
from app.service.youzan.product_sync import sync_product_to_rag


class _FakeModel:
    def encode(self, texts: list[str], normalize_embeddings: bool = True) -> Any:
        assert normalize_embeddings is True
        return np.array([[0.1, 0.2, 0.3] for _ in texts])


class _FakeEmbeddingSearcher:
    def __init__(self, *, fail_upsert: bool = False) -> None:
        self.model = _FakeModel()
        self.fail_upsert = fail_upsert
        self.events: list[tuple[str, str]] = []

    def _get_model(self) -> _FakeModel:
        return self.model

    async def upsert_one(self, key: str, vector: list[float]) -> None:
        self.events.append(("upsert", key))
        if self.fail_upsert:
            raise RuntimeError("vector index unavailable")
        assert vector

    async def delete_one(self, key: str) -> None:
        self.events.append(("delete", key))


def _parsed_product(item_id: int = 10001) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "title": "草莓生日蛋糕",
        "alias": f"cake-{item_id}",
        "price_fen": 19800,
        "stock": 99,
        "image": "",
        "skus": [],
        "item_props": [],
        "desc_clean": "动物奶油草莓夹心。",
        "spec_names": [],
        "prop_names": [],
        "ingredients": [],
    }


async def _get_state(db, item_id: str) -> dict:
    rows = await db.execute_fetchall(
        "SELECT vector_sync_status, vector_synced_at, vector_sync_error, "
        "vector_sync_retry_count FROM knowledge_base WHERE youzan_item_id = ?",
        (item_id,),
    )
    return rows[0]


@pytest.mark.asyncio
async def test_product_vector_sync_marks_success_only_after_vector_write(db) -> None:
    searcher = _FakeEmbeddingSearcher()
    result = await sync_product_to_rag(
        KnowledgeProductRepo(db),
        searcher,
        _parsed_product(),
        1,
        "在售",
        "在售",
        "2026-08-07 10:00:00",
        SyncSource.YOUZAN_WEBHOOK,
        "10001",
    )

    assert result == WriteResult.APPLIED
    assert searcher.events == [("upsert", "10001")]
    state = await _get_state(db, "10001")
    assert state["vector_sync_status"] == "success"
    assert state["vector_synced_at"] != ""
    assert state["vector_sync_error"] == ""


@pytest.mark.asyncio
async def test_product_vector_sync_marks_failed_when_vector_write_fails(db) -> None:
    searcher = _FakeEmbeddingSearcher(fail_upsert=True)

    result = await sync_product_to_rag(
        KnowledgeProductRepo(db),
        searcher,
        _parsed_product(10002),
        1,
        "在售",
        "在售",
        "2026-08-07 10:00:00",
        SyncSource.YOUZAN_WEBHOOK,
        "10002",
    )

    assert result == WriteResult.FAILED
    state = await _get_state(db, "10002")
    assert state["vector_sync_status"] == "failed"
    assert "vector index unavailable" in state["vector_sync_error"]
    assert state["vector_sync_retry_count"] == 1


@pytest.mark.asyncio
async def test_duplicate_product_revision_is_idempotent(db) -> None:
    searcher = _FakeEmbeddingSearcher()
    repo = KnowledgeProductRepo(db)
    args = (
        repo,
        searcher,
        _parsed_product(10003),
        1,
        "在售",
        "在售",
        "2026-08-07 10:00:00",
        SyncSource.YOUZAN_WEBHOOK,
        "10003",
    )

    assert await sync_product_to_rag(*args) == WriteResult.APPLIED
    assert await sync_product_to_rag(*args) == WriteResult.SKIPPED
    assert searcher.events == [("upsert", "10003")]


@pytest.mark.asyncio
async def test_inactive_product_deletes_vector_once(db) -> None:
    searcher = _FakeEmbeddingSearcher()
    repo = KnowledgeProductRepo(db)

    assert (
        await sync_product_to_rag(
            repo,
            searcher,
            _parsed_product(10004),
            1,
            "在售",
            "在售",
            "2026-08-07 10:00:00",
            SyncSource.YOUZAN_WEBHOOK,
            "10004",
        )
        == WriteResult.APPLIED
    )
    assert (
        await sync_product_to_rag(
            repo,
            searcher,
            _parsed_product(10004),
            0,
            "下架",
            "下架",
            "2026-08-07 11:00:00",
            SyncSource.YOUZAN_WEBHOOK,
            "10004",
        )
        == WriteResult.APPLIED
    )

    assert searcher.events == [("upsert", "10004"), ("delete", "10004")]


@pytest.mark.asyncio
async def test_product_webhook_reports_failure_when_vector_state_is_not_durable(
    db,
) -> None:
    class _ProductClient:
        async def get_product(self, item_id: int) -> dict[str, Any]:
            return {
                "response": {
                    "item": {
                        "title": f"商品 {item_id}",
                        "alias": str(item_id),
                        "price": 19800,
                        "quantity": 9,
                        "pic_url": "",
                        "desc": "商品正文",
                        "skus": [],
                        "item_props": [],
                    }
                }
            }

    searcher = _FakeEmbeddingSearcher(fail_upsert=True)
    retriever = KnowledgeRetriever(
        KnowledgeRepo(db),
        searcher,  # type: ignore[arg-type]
        config_repo=ConfigRepo(db),
    )
    handler = YouzanEventHandler(
        db=db,
        knowledge_retriever=retriever,
        youzan_client=_ProductClient(),  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError, match="商品向量同步失败"):
        await handler.handle_system_event(
            payload={"msg": {"item_id": 10005}},
            event_type="ITEM_STATE",
            updated_at_str="2026-08-07 10:00:00",
            msg_id="item-vector-failure",
        )

    state = await _get_state(db, "10005")
    assert state["vector_sync_status"] == "failed"
    assert state["vector_sync_retry_count"] == 1
