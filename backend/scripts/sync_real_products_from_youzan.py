"""
有赞线上正式环境：100% 真实在售商品拉取、多规格解析与 RAG 向量灌库脚本。
"""

import asyncio
import urllib.parse
import json
import os
import sys

# 将项目根目录加入 Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import init_db
from app.config import settings
from app.service.chat import ChatService
from app.repository.session_repo import SessionRepo
from app.repository.message_repo import MessageRepo
from app.service.youzan.client import YouzanClient
from app.repository.config_repo import ConfigRepo


async def main() -> None:
    print("🚀 启动有赞线上正式环境：真实商品全自动同步对齐管道...")

    # 1. 强制关闭 Mock 模式
    settings.YOUZAN_MOCK_MODE = False
    print(
        f"  - 真实连通有赞模式已激活! (YOUZAN_MOCK_MODE = {settings.YOUZAN_MOCK_MODE})"
    )
    print(f"  - 目标微商城 KDT_ID: {settings.YOUZAN_KDT_ID}")

    db_path = "data/bot.db"
    db = await init_db(db_path)

    try:
        # 2. 实例化全部依赖的仓库组件
        session_repo = SessionRepo(db)
        message_repo = MessageRepo(db)

        from app.repository.transfer_repo import TransferRepo
        from app.repository.knowledge_repo import KnowledgeRepo
        from app.service.embedding_search import EmbeddingSearcher
        from app.service.knowledge_retriever import KnowledgeRetriever

        transfer_repo = TransferRepo(db)
        knowledge_repo = KnowledgeRepo(db)
        config_repo = ConfigRepo(db)

        # 实例化 NumPy 向量搜索引擎并自愈对齐
        vs = EmbeddingSearcher()
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

        # 3. 现场创建真实的 YouzanClient 并连通 API 循环分页抓取所有在售商品列表（最极客的分页自适应机制，无限流拉取！）
        yz_client = YouzanClient(config_repo=config_repo)
        print(
            "🔗 正在建立与有赞开放平台的 HTTPS 连接，开始循环自适应拉取线上全量在售商品列表..."
        )

        items = []
        page_no = 1
        page_size = 100  # 每次请求有赞支持的最大单页上限

        while True:
            print(f"  - 正在请求第 {page_no} 页商品数据...")
            resp = await yz_client._call(
                "youzan.items.onsale.get",
                "3.0.0",
                {
                    "kdt_id": settings.YOUZAN_KDT_ID,
                    "page_no": page_no,
                    "page_size": page_size,
                },
            )

            outer_data = (
                resp.get("data") or resp.get("response")
                if isinstance(resp, dict)
                else None
            )
            if not isinstance(outer_data, dict) or "items" not in outer_data:
                print(f"\n❌ 第 {page_no} 页数据获取失败，已中止。响应: {resp}")
                break

            page_items = outer_data.get("items")
            if not page_items:
                # 已无更多数据
                break

            items.extend(page_items)
            print(f"    ✓ 成功拉取到 {len(page_items)} 条商品")

            if len(page_items) < page_size:
                # 最后一页已抓取完成，优雅跳出
                break

            page_no += 1
            await asyncio.sleep(0.1)  # 礼貌延迟，防止有赞 QPS 限制

        await yz_client.close()

        total_count = len(items)
        print(
            f"✅ 成功连接有赞商铺！当前在线累计检测到真实在售商品总数: {total_count} 条"
        )

        if total_count == 0:
            print(
                "⚠️ 您真实的线上店铺中当前没有正在上架销售的商品，请先去有赞后台上架蛋糕。"
            )
            return

        # 4. 循环调用 handle_youzan_system_event 实时触发双轨更新与增量 Embedding 构建
        import datetime
        import time

        success_count = 0
        for idx, item in enumerate(items, 1):
            item_id = item.get("item_id")
            title = item.get("title")
            print(
                f"\n[{idx}/{total_count}] 📥 正在实时请求、清洗并灌录线上商品: [{title}] (ID: {item_id})..."
            )

            # 模拟 Webhook 消息
            payload = {
                "type": "item_ItemState_Onsale",
                "timestamp": int(time.time()) + idx * 60,  # 递增时间越过乐观锁
                "msg_id": f"real_sync_msg_id_{item_id}_{int(time.time())}",
                "msg": urllib.parse.quote(json.dumps({"item_id": item_id})),
            }

            updated_at_str = datetime.datetime.fromtimestamp(
                payload["timestamp"]
            ).strftime("%Y-%m-%d %H:%M:%S")

            try:
                # 强保线上真实通道
                settings.YOUZAN_MOCK_MODE = False

                await chat_service.handle_youzan_system_event(
                    payload=payload,
                    event_type=payload["type"],
                    updated_at_str=updated_at_str,
                    msg_id=payload["msg_id"],
                )
                print(f"  - 🎉 真实商品 [{title}] 同步与 RAG 向量灌库 100% 成功！")
                success_count += 1
            except Exception as e:
                print(f"  - ❌ 商品 [{title}] 同步失败: {e}")

        print(
            f"\n🏆 阶段大胜利！一共成功同步线上真实商品: {success_count} / {total_count} 条！"
        )
        print(
            "💡 恭喜！您现在可以直接返回 SQLite Viewer，刷新 [youzan_products] 和 [knowledge_base] 表，尽情查阅这些最真实的商品数据了！"
        )

    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
