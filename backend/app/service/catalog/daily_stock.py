"""日常现烤每日库存服务。"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.repository.product_daily_stock_repo import ProductDailyStockRepo

BEIJING_TIME_ZONE = ZoneInfo("Asia/Shanghai")
STOCK_DATE_FORMAT = "%Y-%m-%d"


class ProductDailyStockService:
    """负责日常现烤（DAILY_READY）每日库存的复制、录入、预占与释放。"""

    def __init__(self, repo: ProductDailyStockRepo) -> None:
        self._repo = repo

    @staticmethod
    def current_stock_date() -> str:
        """返回北京时间当天日期（YYYY-MM-DD）。"""
        return datetime.now(BEIJING_TIME_ZONE).strftime(STOCK_DATE_FORMAT)

    async def ensure_date(self, stock_date: str) -> int:
        """确保目标日期库存完整：每次调用都补齐之前最近一天中缺失的商品行。

        copy_from_previous_date 只插入缺失行，不覆盖当天已录入的总量，
        因此当天已有部分商品行时，其余商品仍能从昨日补入。
        """
        self._validate_stock_date(stock_date)
        return await self._repo.copy_from_previous_date(stock_date)

    async def get_for_date(self, product_id: str, stock_date: str) -> dict | None:
        """读取单个商品在某天的每日库存记录，不触发跨日复制。"""
        self._validate_stock_date(stock_date)
        return await self._repo.get_for_date(product_id, stock_date)

    async def list_for_date(self, stock_date: str) -> list[dict]:
        """先补齐当天库存，再返回带商品展示字段的库存列表。"""
        await self.ensure_date(stock_date)
        return await self._repo.list_with_products(stock_date)

    async def set_total(
        self,
        stock_date: str,
        product_id: str,
        total_qty: int,
        operator: str,
    ) -> bool:
        """录入当天总量；总量不能低于已预占数量。"""
        if total_qty < 0:
            raise ValueError("每日库存总量不能为负数")
        await self.ensure_date(stock_date)
        updated = await self._repo.upsert_total(
            stock_date,
            product_id,
            total_qty,
            operator,
        )
        if not updated:
            raise ValueError("每日库存总量不能低于已预占数量")
        return True

    async def reserve(self, product_id: str, stock_date: str, quantity: int) -> bool:
        """先补齐当天库存，再原子预占；剩余可售量不足返回 False。"""
        await self.ensure_date(stock_date)
        return await self._repo.reserve(product_id, stock_date, quantity)

    async def release(self, product_id: str, stock_date: str, quantity: int) -> bool:
        """原子释放每日库存预占。"""
        self._validate_stock_date(stock_date)
        return await self._repo.release(product_id, stock_date, quantity)

    def _validate_stock_date(self, stock_date: str) -> None:
        """校验库存日期必须是合法的 YYYY-MM-DD。"""
        value = str(stock_date or "").strip()
        try:
            datetime.strptime(value, STOCK_DATE_FORMAT)
        except ValueError as exc:
            raise ValueError(f"库存日期格式无效: {stock_date}") from exc


__all__ = ["ProductDailyStockService"]
