"""
分析与埋点数据访问层。
"""

from app.repository.base import BaseRepository


class AnalyticsRepo(BaseRepository):
    """分析与埋点大宽表仓库。"""

    async def add_event(
        self,
        session_id: str | None,
        buyer_id: str | None,
        event_type: str,
        event_source: str,
        ref_id: str | None,
        meta_data: str,
        created_at: str,
    ) -> None:
        """记录一条埋点分析事件。"""
        await self._db.execute(
            "INSERT INTO analytics_events (session_id, buyer_id, event_type, event_source, ref_id, meta_data, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                buyer_id,
                event_type,
                event_source,
                ref_id,
                meta_data,
                created_at,
            ),
        )
        await self._db.commit()

    async def check_recent_recommend(
        self,
        session_id: str,
        ref_id: str,
        hour_limit: int = 1,
    ) -> bool:
        """
        查验过去指定小时数内（默认1小时），相同 session_id 是否对同款商品产生过推荐行为。
        用于滑动去重防刷，保护转化率指标。
        返回 True 表示已推荐过（应静默去重），False 表示未推荐过。
        """
        rows = await self._db.execute_fetchall(
            "SELECT 1 FROM analytics_events "
            'WHERE session_id = ? AND ref_id = ? AND event_type = "product_recommend" '
            'AND datetime(created_at) > datetime("now", "-" || ? || " hour") LIMIT 1',
            (session_id, ref_id, hour_limit),
        )
        return len(rows) > 0

    async def check_ai_recommend_for_conversion(
        self,
        buyer_id: str,
        ref_id: str,
        lookback_hours: int = 24,
    ) -> str | None:
        """
        追溯校验在过去 24 小时内，该买家是否曾受过 AI 针对此商品的推荐行为。
        如果存在，则返回最新一次推荐会话的 session_id，用以做精确的 ROI 业绩归因；不存在返回 None。
        """
        rows = await self._db.execute_fetchall(
            "SELECT session_id FROM analytics_events "
            'WHERE buyer_id = ? AND ref_id = ? AND event_type = "product_recommend" '
            'AND datetime(created_at) > datetime("now", "-" || ? || " hour") '
            "ORDER BY created_at DESC LIMIT 1",
            (buyer_id, ref_id, lookback_hours),
        )
        return rows[0]["session_id"] if rows else None

    async def rotate_analytics_logs(self, days_to_keep: int = 90) -> None:
        """自动滚动清理超出保留天数的历史分析日志，保障 SQLite 磁盘容量不爆满。"""
        await self._db.execute(
            'DELETE FROM analytics_events WHERE datetime(created_at) < datetime("now", "-" || ? || " days")',
            (days_to_keep,),
        )
        await self._db.commit()
        # 提示系统进行磁盘碎片重整，物理收缩文件大小
        await self._db.execute("PRAGMA incremental_vacuum(100)")
        await self._db.commit()
