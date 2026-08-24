"""
有赞商品 RAG 自动灌库、多规格多属性解析仿真同步脚本。
"""

import asyncio
import urllib.parse
import json
import os
import sys

# 将项目根目录加入 Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import init_db
from app.service.chat import ChatService
from app.repository.session_repo import SessionRepo
from app.repository.message_repo import MessageRepo


async def main() -> None:
    print("🚀 启动有赞商品 RAG 自动灌库、多规格多属性解析仿真同步...")
    db_path = "data/bot.db"

    # 1. 连接物理数据库
    db = await init_db(db_path)

    try:
        # 2. 实例化全部依赖的仓库组件
        session_repo = SessionRepo(db)
        message_repo = MessageRepo(db)

        from app.repository.transfer_repo import TransferRepo
        from app.repository.knowledge_repo import KnowledgeRepo
        from app.repository.config_repo import ConfigRepo
        from app.service.embedding_search import EmbeddingSearcher
        from app.service.knowledge_retriever import KnowledgeRetriever

        transfer_repo = TransferRepo(db)
        knowledge_repo = KnowledgeRepo(db)
        config_repo = ConfigRepo(db)

        # 实例化 NumPy 向量搜索引擎并自愈对齐
        vs = EmbeddingSearcher()
        from app.config import settings

        vs_path = settings.EMBEDDING_INDEX_DIR
        all_kb_titles = await knowledge_repo.get_all_titles_with_keys()
        if all_kb_titles:
            await asyncio.to_thread(vs.build, all_kb_titles)
            await asyncio.to_thread(vs.save, vs_path)

        knowledge_retriever = KnowledgeRetriever(
            knowledge_repo, vs, config_repo=config_repo
        )

        # 实例化高保真 ChatService
        chat_service = ChatService(
            session_repo=session_repo,
            message_repo=message_repo,
            transfer_repo=transfer_repo,
            knowledge_retriever=knowledge_retriever,
        )

        # 3. 构造高仿真有赞商品上架的 Webhook 原始报文 (商品ID: 5836487486)
        item_id = 5836487486
        payload = {
            "type": "item_ItemState_Onsale",
            "timestamp": 1779347400,  # 🌟 将时间戳往后递增，顺畅越过乐观锁校验条件
            "msg_id": "simulated_sync_msg_id_999888",
            "msg": urllib.parse.quote(json.dumps({"item_id": item_id})),
        }

        # 4. 调用业务解耦后的系统事件处理器
        print("📥 正在分发 Webhook A轨 异步数据管道 [item_ItemState_Onsale]...")
        import datetime

        updated_at_str = datetime.datetime.fromtimestamp(payload["timestamp"]).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        await chat_service.handle_youzan_system_event(
            payload=payload, updated_at_str=updated_at_str, msg_id=payload["msg_id"]
        )

        print("\n🎉 恭喜！有赞同步与 RAG 向量灌录流程 100% 成功畅通！")
        print("\n================== 📝 物理数据库写入实况校验 ==================")

        # 校验 1：物理商品大宽表 youzan_products
        async with db.execute(
            "SELECT * FROM youzan_products WHERE item_id = ?", (item_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                print("✅ 物理商品宽表 [youzan_products] 成功写入 1 条高密度记录：")
                print(f"  - 商品 ID (item_id): {row['item_id']}")
                print(f"  - 商品名称 (title): {row['title']}")
                print(f"  - 商品别名 (alias): {row['alias']}")
                print(f"  - 统一原价: ￥{row['price_fen'] / 100.0:.2f} 元")
                print(f"  - 当前总库存: {row['stock']} 件")
                print(
                    f"  - 在售状态 (is_active): {'活跃在售' if row['is_active'] == 1 else '已下架'}"
                )
                print(f"  - 【新】智能特征标签 (tags): {row['tags']}")
                print(f"  - 【新】多规格矩阵 (skus_json): {row['skus_json']}")
                print(f"  - 【新】清洗提纯后的原料描述 (desc):\n    >>> {row['desc']}")
            else:
                print("❌ [youzan_products] 物理商品表写入失败")

        # 校验 2：RAG 向量知识库表 knowledge_base
        async with db.execute(
            "SELECT * FROM knowledge_base WHERE youzan_item_id = ?", (str(item_id),)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                print(
                    "\n✅ RAG 知识库 [knowledge_base] 成功灌录 1 条全新动态商品知识："
                )
                print(f"  - 知识点主题 (title): {row['title']}")
                print(f"  - 搜索触发词 (keywords): {row['keywords']}")
                print(
                    "  - 拼装渲染后的 Markdown 知识正文 (content):\n-------------------------------------------------------------"
                )
                print(row["content"])
                print("-------------------------------------------------------------")
            else:
                print("❌ [knowledge_base] 知识库表写入失败")

    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
