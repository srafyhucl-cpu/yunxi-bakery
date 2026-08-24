"""
有赞商品名称异动与向量唯一主键防幽灵残留压力集成测试。
"""

import json
import os
import pytest

from app.database import init_db
from app.config import settings
from app.repository.session_repo import SessionRepo
from app.repository.message_repo import MessageRepo
from app.repository.transfer_repo import TransferRepo
from app.repository.knowledge_repo import KnowledgeRepo
from app.repository.config_repo import ConfigRepo
from app.service.embedding_search import EmbeddingSearcher
from app.service.knowledge_retriever import KnowledgeRetriever
from app.repository.analytics_repo import AnalyticsRepo
from app.repository.youzan_webhook_event_repo import YouzanWebhookEventRepo
from app.service.chat import ChatService
from app.service.youzan.client import YouzanClient
from app.service.youzan.event_handler import YouzanEventHandler


@pytest.mark.asyncio
async def test_product_name_change_prevents_residue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    测试场景：
    模拟同一款商品 `item_id=888`：
    1. 第 1 次名称为 "老款慕斯蛋糕"，推送入库。
    2. 第 2 次更名为 "尊享重制版慕斯蛋糕"，再次推送入库。
    断言：
    - 数据库中对应 item_id 的知识条目内容已被成功增量更新。
    - 向量引擎中 `doc_count` 数量始终维持在 1 处（原地更新），不产生幽灵向量污染。
    - 向量索引的主键必须是商品的唯一不变量 ID ("888")，而不是变动的名称。
    """
    # 1. 初始化隔离的内存 SQLite 数据库，防本地物理库污染
    db = await init_db(":memory:")

    try:
        # 2. 准备各大 Repository 与核心检索引擎
        session_repo = SessionRepo(db)
        message_repo = MessageRepo(db)
        transfer_repo = TransferRepo(db)
        knowledge_repo = KnowledgeRepo(db)
        config_repo = ConfigRepo(db)

        vs = EmbeddingSearcher()
        # 为防止污染物理缓存，将持久化路径重定向
        tmp_index_path = "data/test_embedding_name_change_tmp.index"
        monkeypatch.setattr(settings, "EMBEDDING_INDEX_DIR", tmp_index_path)

        # 全量空初始化
        vs.build([])
        knowledge_retriever = KnowledgeRetriever(
            knowledge_repo, vs, config_repo=config_repo
        )

        # 3. 实例化核心对话服务（显式注入有赞依赖，L-1.2）
        youzan_client = YouzanClient(config_repo=config_repo)
        webhook_event_repo = YouzanWebhookEventRepo(db)
        youzan_event_handler = YouzanEventHandler(
            db=db,
            knowledge_retriever=knowledge_retriever,
            youzan_client=youzan_client,
            audit_repo=webhook_event_repo,
        )
        chat_service = ChatService(
            session_repo=session_repo,
            message_repo=message_repo,
            transfer_repo=transfer_repo,
            knowledge_retriever=knowledge_retriever,
            youzan_client=youzan_client,
            youzan_webhook_events_repo=webhook_event_repo,
            youzan_event_handler=youzan_event_handler,
            analytics_repo=AnalyticsRepo(db),
        )

        # 4. 模拟第 1 次推送："老款慕斯蛋糕"
        product_v1 = {
            "title": "老款慕斯蛋糕",
            "alias": "alias_888",
            "price": 19800,
            "quantity": 30,
            "pic_url": "http://img.yzcdn.cn/old_mousse.jpg",
            "desc": "精选动物奶油，老少咸宜。",
            "skus": [],
            "item_props": [],
        }

        # 模拟有赞 API 详情响应
        async def mock_get_product_v1(self, item_id: str | int) -> dict:
            return {"data": {"item": product_v1}}

        monkeypatch.setattr(YouzanClient, "get_product", mock_get_product_v1)

        # 模拟 Webhook 触发
        payload_v1 = {
            "type": "item_ItemState_Onsale",
            "msg": json.dumps({"item_id": 888}),
        }
        await chat_service.handle_youzan_system_event(
            payload=payload_v1,
            event_type=payload_v1["type"],
            updated_at_str="2026-05-20 17:16:00",
            msg_id="msg_001",
        )

        # 校验：向量数量和主键必须 100% 精确对齐唯一 ID
        assert vs.doc_count == 1
        assert vs._doc_keys[0] == "888"

        # 从物理库检索校验
        kb_entries = await knowledge_repo.get_by_youzan_item_ids(["888"])
        assert len(kb_entries) == 1
        assert "老款慕斯蛋糕" in kb_entries[0].title
        assert "售价 ￥198.00 元" in kb_entries[0].content

        # 5. 模拟第 2 次更名推送："尊享重制版慕斯蛋糕"
        product_v2 = {
            "title": "尊享重制版慕斯蛋糕",
            "alias": "alias_888",
            "price": 25800,
            "quantity": 45,
            "pic_url": "http://img.yzcdn.cn/new_mousse.jpg",
            "desc": "尊享升级，重装归来！",
            "skus": [],
            "item_props": [],
        }

        async def mock_get_product_v2(self, item_id: str | int) -> dict:
            return {"data": {"item": product_v2}}

        monkeypatch.setattr(YouzanClient, "get_product", mock_get_product_v2)

        # 以更高的更新时间戳触发事件，击穿乐观锁防线进行覆盖
        payload_v2 = {
            "type": "item_ItemState_Onsale",
            "msg": json.dumps({"item_id": 888}),
        }
        await chat_service.handle_youzan_system_event(
            payload=payload_v2,
            event_type=payload_v2["type"],
            updated_at_str="2026-05-20 17:17:00",
            msg_id="msg_002",
        )

        # 💥 刚性卡点验证：断言数量依然为 1！代表旧有向量已被原子擦除并原地覆盖，幽灵向量残留清除率: 100%
        assert vs.doc_count == 1
        assert vs._doc_keys[0] == "888"

        # 校验物理库中的标题已完美平移为最新名称
        kb_entries_updated = await knowledge_repo.get_by_youzan_item_ids(["888"])
        assert len(kb_entries_updated) == 1
        assert "尊享重制版慕斯蛋糕" in kb_entries_updated[0].title
        assert "售价 ￥258.00 元" in kb_entries_updated[0].content
        assert "老款慕斯蛋糕" not in kb_entries_updated[0].title

    finally:
        await db.close()
        if os.path.exists(tmp_index_path):
            os.remove(tmp_index_path)
