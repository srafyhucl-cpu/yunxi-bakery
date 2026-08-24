"""商品 RAG 文本动静分离测试。"""

import numpy as np
import pytest

from app.models.content_change_history import SyncSource, WriteResult
from app.repository.knowledge_product_repo import KnowledgeProductRepo
from app.service.youzan.product_sync import sync_product_to_rag


class _CapturingModel:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def encode(self, texts, normalize_embeddings=True):  # noqa: ANN001, ARG002
        self.texts.extend(texts)
        return np.array([[0.1, 0.2, 0.3] for _ in texts])


class _CapturingVectorStore:
    def __init__(self) -> None:
        self.model = _CapturingModel()
        self.upserted: list[str] = []

    def _get_model(self) -> _CapturingModel:
        return self.model

    async def upsert_one(self, key: str, vector: list[float]) -> None:  # noqa: ARG002
        self.upserted.append(key)


class _FakeKnowledgeRetriever:
    def __init__(self) -> None:
        self._vs = _CapturingVectorStore()


@pytest.mark.asyncio
async def test_product_embedding_text_excludes_realtime_stock(db) -> None:
    retriever = _FakeKnowledgeRetriever()
    parsed = {
        "item_id": 10001,
        "title": "草莓生日蛋糕",
        "alias": "cake-10001",
        "price_fen": 19800,
        "stock": 99,
        "image": "https://img.example/cake.jpg",
        "skus": [
            {
                "price": 19800,
                "quantity": 12,
                "properties_name_json": '[{"k":"规格","v":"6寸"}]',
            }
        ],
        "item_props": [
            {
                "prop_name": "甜度",
                "is_multiple": False,
                "text_models": [{"prop_text_name": "少糖", "price": 0}],
            }
        ],
        "desc_clean": "动物奶油草莓夹心，建议冷藏食用。",
    }

    result = await sync_product_to_rag(
        KnowledgeProductRepo(db),
        retriever._vs,
        parsed,
        1,
        "在售, 草莓, 动物奶油",
        "在售",
        "2026-07-09 10:00:00",
        SyncSource.YOUZAN_WEBHOOK,
        "10001",
    )

    assert result == WriteResult.APPLIED
    assert retriever._vs.upserted == ["10001"]
    embedding_text = retriever._vs.model.texts[0]
    assert "草莓生日蛋糕" in embedding_text
    assert "售价 ￥198.00 元" in embedding_text
    assert "当前可用库存" not in embedding_text
    assert "当前可用总库存" not in embedding_text
    assert "99 件" not in embedding_text
    assert "12 件" not in embedding_text

    rows = await db.execute_fetchall(
        "SELECT content FROM knowledge_base WHERE youzan_item_id = ?",
        ("10001",),
    )
    assert "当前可用库存 12 件" in rows[0]["content"]
