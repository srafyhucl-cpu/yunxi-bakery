"""券库存账本：核销/退回的幂等与事务边界。"""

import sqlite3

from app.config import settings
from app.models.member import CouponStatus
from app.repository.coupon_inventory_repo import CouponInventoryRepo


class CouponInventoryService:
    """券生命周期账本（核销/退回，幂等）。"""

    def __init__(self, db) -> None:
        self._repo = CouponInventoryRepo(db)

    async def consume_once(
        self,
        coupon_id: str,
        mobile: str,
        *,
        order_no: str,
        deducted_fen: int,
        occurred_at: str,
    ) -> dict | None:
        """核销一张券：事务内校验最新态=TAKE 并插入 CONSUME 行（幂等）。

        authority 取 settings.COUPON_AUTHORITY：youzan 模式下 import/webhook
        镜像行是有效来源；local 模式下只认 order/local 行。并发双核销由唯一索引
        (coupon_id, status, mobile) 兜底，IntegrityError 转幂等返回。

        同单重复核销幂等返回；跨订单核销抛 ValueError（防一张券抵扣两单，
        余额/组合/储值支付路径在事务内，抛错整体回滚，支付不落账）。
        """
        authority = settings.COUPON_AUTHORITY
        async with self._repo.transaction():
            existing = await self._repo.get_latest_state(
                coupon_id, mobile, authority=authority
            )
            if existing is not None and existing["status"] == CouponStatus.CONSUME:
                if str(existing.get("order_no", "") or "") == order_no:
                    return existing
                raise ValueError("优惠券已被其他订单核销")
            try:
                return await self._repo.consume(
                    coupon_id,
                    mobile,
                    order_no=order_no,
                    deducted_fen=deducted_fen,
                    consumed_at=occurred_at,
                    occurred_at=occurred_at,
                    authority=authority,
                )
            except sqlite3.IntegrityError:
                # 并发核销冲突：重读最新态，同单幂等返回、跨单拒绝
                latest = await self._repo.get_latest_state(
                    coupon_id, mobile, authority=authority
                )
                if latest is not None:
                    if str(latest.get("order_no", "") or "") == order_no:
                        return latest
                    raise ValueError("优惠券已被其他订单核销")
                raise

    async def refund_once(
        self,
        coupon_id: str,
        mobile: str,
        *,
        order_no: str,
        occurred_at: str,
    ) -> dict | None:
        """退回已核销券：事务内校验最新态=CONSUME 并插入 BACK 行（幂等）。

        同单重复退回幂等返回；跨订单退回抛 ValueError（与核销同源防双花）。
        """
        authority = settings.COUPON_AUTHORITY
        async with self._repo.transaction():
            existing = await self._repo.get_latest_state(
                coupon_id, mobile, authority=authority
            )
            if existing is not None and existing["status"] == CouponStatus.BACK:
                if str(existing.get("order_no", "") or "") == order_no:
                    return existing
                raise ValueError("优惠券已被其他订单退回")
            try:
                return await self._repo.refund(
                    coupon_id,
                    mobile,
                    order_no=order_no,
                    refunded_at=occurred_at,
                    occurred_at=occurred_at,
                    authority=authority,
                )
            except sqlite3.IntegrityError:
                # 并发退回冲突：重读最新态，同单幂等返回、跨单拒绝
                latest = await self._repo.get_latest_state(
                    coupon_id, mobile, authority=authority
                )
                if latest is not None:
                    if str(latest.get("order_no", "") or "") == order_no:
                        return latest
                    raise ValueError("优惠券已被其他订单退回")
                raise
