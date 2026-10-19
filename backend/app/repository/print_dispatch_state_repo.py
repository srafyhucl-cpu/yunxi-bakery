"""订单打印调度游标数据访问层。"""

from app.repository.base import BaseRepository
from app.utils import now_str

# 游标表只保留固定单行，避免多实例或误插产生第二份状态。
DEFAULT_STATE_ID = "default"
_STATE_COLUMNS = "id, last_updated_at, last_order_id, updated_at"


class PrintDispatchStateRepo(BaseRepository):
    """打印调度游标的读取与推进。"""

    async def get_or_create(self, default_updated_at: str) -> dict:
        """读取游标；首次启动时以传入时间初始化，之后保持原值。"""
        await self._db.execute(
            "INSERT OR IGNORE INTO order_print_dispatch_state ("
            + _STATE_COLUMNS
            + ") VALUES (?, ?, ?, ?)",
            (DEFAULT_STATE_ID, default_updated_at, "", now_str()),
        )
        rows = await self._db.execute_fetchall(
            "SELECT "
            + _STATE_COLUMNS
            + " FROM order_print_dispatch_state WHERE id = ? LIMIT 1",
            (DEFAULT_STATE_ID,),
        )
        if not rows:
            raise RuntimeError("打印调度游标初始化失败")
        return dict(rows[0])

    async def set_cursor(self, last_updated_at: str, last_order_id: str) -> None:
        """推进游标；调用方负责在扫描成功后统一提交事务。"""
        await self._db.execute(
            "INSERT INTO order_print_dispatch_state ("
            + _STATE_COLUMNS
            + ") VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "last_updated_at = excluded.last_updated_at, "
            "last_order_id = excluded.last_order_id, "
            "updated_at = excluded.updated_at",
            (
                DEFAULT_STATE_ID,
                last_updated_at,
                last_order_id,
                now_str(),
            ),
        )


__all__ = ["DEFAULT_STATE_ID", "PrintDispatchStateRepo"]
