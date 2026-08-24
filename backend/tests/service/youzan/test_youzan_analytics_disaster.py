"""
有赞双轨同步与分布式容灾加固（乐观锁、推荐判重、24小时支付归因）集成回归测试。
"""

import datetime
import pytest

from app.database import init_db
from app.repository.youzan_repo import YouzanProductRepo
from app.repository.analytics_repo import AnalyticsRepo


@pytest.mark.asyncio
async def test_youzan_out_of_order_optimistic_lock() -> None:
    """测试有赞 Webhook 乱序到达防御：时序乐观锁检查机制。"""
    # 1. 初始化内存中 SQLite，避免产生物理文件噪音
    db = await init_db(":memory:")
    product_repo = YouzanProductRepo(db)

    try:
        # 商品唯一标识
        item_id = 999111222
        alias = "lines_puppy_blue_series"

        # 2. 模拟先打入一个较新的 updated_at 商品变更包（12:00:05）
        newer_time = "2026-05-20 12:00:05"
        await product_repo.upsert_product(
            item_id=item_id,
            title="小狗系列五一限定蛋糕(最新版)",
            alias=alias,
            price_fen=28800,
            stock=100,
            image="http://img.com/new.png",
            is_active=1,
            updated_at=newer_time,
        )

        # 验证第一次写入成功
        prod = await product_repo.get_by_id(item_id)
        assert prod is not None
        assert prod["title"] == "小狗系列五一限定蛋糕(最新版)"
        assert prod["stock"] == 100

        # 3. 故意打入一个由于网络延迟迟到的、updated_at 较旧的变更包（12:00:00）
        older_time = "2026-05-20 12:00:00"
        await product_repo.upsert_product(
            item_id=item_id,
            title="小狗系列五一限定蛋糕(旧版已过时)",
            alias=alias,
            price_fen=25800,
            stock=50,
            image="http://img.com/old.png",
            is_active=1,
            updated_at=older_time,
        )

        # 4. 核心断言：验证虽然打入了旧版数据，但由于乐观锁防线，本地数据依然维持最新 12:00:05 版！
        current_prod = await product_repo.get_by_id(item_id)
        assert current_prod is not None
        assert current_prod["title"] == "小狗系列五一限定蛋糕(最新版)"
        assert current_prod["price_fen"] == 28800
        assert current_prod["stock"] == 100
        assert current_prod["updated_at"] == newer_time

    finally:
        await db.close()


@pytest.mark.asyncio
async def test_analytics_recommend_deduplication_and_roi_attribution() -> None:
    """测试分析埋点：推荐1小时滑动去重与支付24小时 ROI 业绩归因合流防线。"""
    db = await init_db(":memory:")
    product_repo = YouzanProductRepo(db)
    analytics_repo = AnalyticsRepo(db)

    try:
        session_id = "session_mock_bake_888"
        buyer_id = "buyer_yz_openid_999"
        alias = "matcha_crepe_cake_alias"

        # 首先将关联的物理商品信息写入
        await product_repo.upsert_product(
            item_id=888555,
            title="小山园抹茶千层",
            alias=alias,
            price_fen=28800,
            stock=150,
            image="http://img.com/matcha.jpg",
            is_active=1,
            updated_at="2026-05-20 12:00:00",
        )

        # 1. 测试 B（AI 推荐一小时滑动排重防线）
        # 记录第一次推荐事件
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await analytics_repo.add_event(
            session_id=session_id,
            buyer_id=buyer_id,
            event_type="product_recommend",
            event_source="ai_bot",
            ref_id=alias,
            meta_data='{"title": "小山园抹茶千层"}',
            created_at=now_str,
        )

        # 核心判重断言：在 1 小时滑动窗口内，相同的 session_id 针对同款商品别名触发推荐判定，应该返回 True！
        is_duplicate = await analytics_repo.check_recent_recommend(
            session_id, alias, hour_limit=1
        )
        assert is_duplicate is True

        # 验证不同 session_id 未被排重影响
        assert (
            await analytics_repo.check_recent_recommend(
                "session_another_diff", alias, hour_limit=1
            )
            is False
        )

        # 2. 测试 C（AI 导购付款 24小时 ROI 业绩归因防线）
        # 追溯查询：当买家在 24 小时内付款时，校验是否存在对应商品的 RAG 导购推荐
        归因_session_id = await analytics_repo.check_ai_recommend_for_conversion(
            buyer_id, alias, lookback_hours=24
        )

        # 核心归因断言：成功追溯出正是 session_id = "session_mock_bake_888" 为该买家种了草！从而将销售绩效准确归因！
        assert 归因_session_id == session_id

    finally:
        await db.close()
