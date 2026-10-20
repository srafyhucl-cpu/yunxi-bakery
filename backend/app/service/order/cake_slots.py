"""定制蛋糕 2 小时时段容量预占服务。"""

from datetime import datetime

from app.repository.cake_slot_repo import CakeSlotRepo

EXPECT_TIME_FORMAT = "%Y-%m-%d %H:%M"
DEFAULT_CAKE_SLOT_CAPACITY = 5


def extract_slot_key(expect_time: str) -> str:
    """从预约时间中提取 2 小时时段键，格式为 YYYY-MM-DD HH:00-HH:00。"""
    if not expect_time:
        raise ValueError("预约时间不能为空")
    try:
        dt = datetime.strptime(expect_time, EXPECT_TIME_FORMAT)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"预约时间格式无效: {expect_time}") from exc
    slot_start_hour = (dt.hour // 2) * 2
    slot_end_hour = slot_start_hour + 2
    return f"{dt.strftime('%Y-%m-%d')} {slot_start_hour:02d}:00-{slot_end_hour:02d}:00"


class CakeSlotCapacityService:
    """以数据库原子计数保证同一时段定制蛋糕不超卖。"""

    def __init__(
        self,
        repo: CakeSlotRepo,
        max_capacity: int = DEFAULT_CAKE_SLOT_CAPACITY,
    ) -> None:
        self._repo = repo
        self._max_capacity = max_capacity

    async def reserve(self, order_id: str, expect_time: str) -> bool:
        """预占订单所在时段名额；容量已满返回 False。"""
        normalized_order_id = str(order_id or "").strip()
        if not normalized_order_id:
            raise ValueError("订单号不能为空")
        slot_key = extract_slot_key(expect_time)
        async with self._repo.transaction():
            return await self._repo.reserve(
                slot_key,
                normalized_order_id,
                self._max_capacity,
            )

    async def release(self, order_id: str) -> bool:
        """释放订单名额；无预占或重复释放均为幂等成功。"""
        normalized_order_id = str(order_id or "").strip()
        if not normalized_order_id:
            raise ValueError("订单号不能为空")
        async with self._repo.transaction():
            return await self._repo.release(normalized_order_id)

    async def count(self, expect_time: str) -> int:
        """统计指定预约时间所在时段的已预占单量。"""
        slot_key = extract_slot_key(expect_time)
        return await self._repo.count_for_slot(slot_key)


__all__ = [
    "CakeSlotCapacityService",
    "DEFAULT_CAKE_SLOT_CAPACITY",
    "EXPECT_TIME_FORMAT",
    "extract_slot_key",
]
