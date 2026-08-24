"""券支付联动：抵扣快照、支付核销、退款退回、未支付清快照。"""

import sqlite3

from app.config import settings
from app.logger import setup_logger
from app.models.member import CouponStatus
from app.models.order import Order
from app.repository.coupon_inventory_repo import CouponInventoryRepo
from app.repository.coupon_template_repo import CouponTemplateRepo
from app.repository.order_repo import OrderRepo
from app.service.coupon.inventory import CouponInventoryService
from app.service.coupon.rules import calc_discount, is_coupon_available
from app.service.order.payment_state import (
    PAYMENT_METHOD_COMBINED,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PARTIAL,
    PAYMENT_STATUS_UNPAID,
    compute_remain_fen,
    dumps_payment,
    loads_payment,
    now_text,
    status_value,
)

logger = setup_logger()


class CouponPaymentService:
    """负责订单券抵扣快照、支付核销与退款退回。"""

    def __init__(
        self,
        inventory_service: CouponInventoryService | None = None,
        template_repo: CouponTemplateRepo | None = None,
        order_repo: OrderRepo | None = None,
    ) -> None:
        self._order_repo = order_repo or OrderRepo(None)
        db = self._order_repo._db
        self._inventory_service = inventory_service or CouponInventoryService(db)
        self._template_repo = template_repo or CouponTemplateRepo(db)
        self._inventory_repo = CouponInventoryRepo(db)

    async def apply_coupon_snapshot(
        self,
        order: Order,
        *,
        user_id: str,
        coupon_id: str,
        mobile: str,
    ) -> dict:
        """校验并写券抵扣 partial 快照（支付成功才核销）。"""
        payment = loads_payment(order.payment)
        payment_status = str(payment.get("status", PAYMENT_STATUS_UNPAID))
        if payment_status == PAYMENT_STATUS_PAID:
            raise ValueError("订单已支付")
        if int(payment.get("balanceFen", 0) or 0) > 0:
            raise ValueError("订单已部分支付，不能再应用优惠券")
        state = await self._inventory_repo.get_latest_state(
            coupon_id, mobile, authority=settings.COUPON_AUTHORITY
        )
        if state is None or state["status"] != CouponStatus.TAKE:
            raise ValueError("优惠券不可用")
        template_row = await self._template_repo.get(str(state.get("template_id", "")))
        template = dict(template_row) if template_row is not None else None
        if template is None:
            template = {
                "id": state.get("template_id", ""),
                "coupon_type": "",
                "threshold_fen": 0,
                "value_fen": int(state.get("value_fen", 0) or 0),
                "discount_bp": 0,
                "cap_fen": 0,
                "valid_from": state.get("valid_from", ""),
                "valid_until": state.get("valid_until", ""),
                "status": "active",
            }
        total_fen = self._total_fen(order)
        now = now_text()
        if not is_coupon_available(template, total_fen, now):
            raise ValueError("优惠券不满足使用条件")
        coupon_fen = calc_discount(template, total_fen)
        if coupon_fen <= 0:
            raise ValueError("优惠券抵扣金额无效")
        balance_fen = int(payment.get("balanceFen", 0) or 0)
        points_fen = int(payment.get("pointsFen", 0) or 0)
        if coupon_fen > total_fen - balance_fen - points_fen:
            raise ValueError("优惠券抵扣金额超过剩余应付")
        remain_fen = compute_remain_fen(total_fen, coupon_fen, balance_fen, points_fen)
        payment.update(
            {
                "status": PAYMENT_STATUS_PARTIAL,
                "method": PAYMENT_METHOD_COMBINED,
                "couponId": coupon_id,
                "couponFen": coupon_fen,
                "remainFen": remain_fen,
            }
        )
        updated = await self._order_repo.update_payment_to_partial_if_unpaid_or_partial_active(
            order.id, dumps_payment(payment), now
        )
        if updated is None:
            raise ValueError("订单支付状态更新冲突")
        await self._order_repo._db.commit()
        return {
            "orderId": order.id,
            "status": status_value(updated),
            "paymentStatus": PAYMENT_STATUS_PARTIAL,
            "paymentMethod": PAYMENT_METHOD_COMBINED,
            "couponId": coupon_id,
            "couponFen": coupon_fen,
            "pointsFen": points_fen,
            "balanceFen": balance_fen,
            "remainFen": remain_fen,
        }

    async def consume_on_payment(self, order: Order) -> None:
        """支付成功后核销券（幂等）。

        支付路径若在外层事务内调用：CouponInventoryRepo.insert 内部自 commit，
        会连同支付落账一起提交并释放 savepoint，随后 RELEASE SAVEPOINT 报错；
        此处捕获该确定性错误并按最新态幂等确认，跨单双花 ValueError 不受影响
        （在插入前抛出，外层事务整体回滚、支付不落账）。
        """
        payment = loads_payment(order.payment)
        if str(payment.get("status", PAYMENT_STATUS_UNPAID)) != PAYMENT_STATUS_PAID:
            return
        coupon_id = str(payment.get("couponId", "") or "")
        if not coupon_id:
            return
        mobile = await self._try_resolve_mobile(order.user_id)
        if mobile is None:
            return
        try:
            await self._inventory_service.consume_once(
                coupon_id,
                mobile,
                order_no=order.id,
                deducted_fen=int(payment.get("couponFen", 0) or 0),
                occurred_at=now_text(),
            )
        except sqlite3.OperationalError as exc:
            if "savepoint" not in str(exc).lower():
                raise
            logger.warning(
                "券核销在外层事务内触发 savepoint 释放，幂等确认落账 order=%s coupon=%s",
                order.id,
                coupon_id,
            )
            await self._assert_latest_consume(coupon_id, mobile, order.id, exc)

    async def refund_coupon(self, order: Order) -> None:
        """已支付全单退款退回券（幂等）。"""
        payment = loads_payment(order.payment)
        coupon_id = str(payment.get("couponId", "") or "")
        if not coupon_id:
            return
        mobile = await self._try_resolve_mobile(order.user_id)
        if mobile is None:
            return
        try:
            await self._inventory_service.refund_once(
                coupon_id,
                mobile,
                order_no=order.id,
                occurred_at=now_text(),
            )
        except sqlite3.OperationalError as exc:
            if "savepoint" not in str(exc).lower():
                raise
            logger.warning(
                "券退回在外层事务内触发 savepoint 释放，幂等确认落账 order=%s coupon=%s",
                order.id,
                coupon_id,
            )
            latest = await self._inventory_repo.get_latest_state(
                coupon_id, mobile, authority=settings.COUPON_AUTHORITY
            )
            if (
                latest is None
                or latest["status"] != CouponStatus.BACK
                or str(latest.get("order_no", "") or "") != order.id
            ):
                raise ValueError("优惠券退回状态异常，请对账处理") from exc

    async def clear_coupon_snapshot(self, order: Order) -> None:
        """未支付取消/超时：只清快照，不写 BACK。"""
        latest = await self._order_repo.get_order(order.id)
        if latest is None:
            return
        payment = loads_payment(latest.payment)
        if not payment.get("couponId"):
            return
        balance_fen = int(payment.get("balanceFen", 0) or 0)
        points_fen = int(payment.get("pointsFen", 0) or 0)
        payment["couponId"] = ""
        payment["couponFen"] = 0
        payment["remainFen"] = compute_remain_fen(
            self._total_fen(latest), 0, balance_fen, points_fen
        )
        # 券/积分/余额都清空后恢复未支付态，避免残留 partial 与 method
        if balance_fen <= 0 and points_fen <= 0:
            payment["status"] = PAYMENT_STATUS_UNPAID
            payment["method"] = ""
        await self._order_repo.update_payment(
            order.id, dumps_payment(payment), now_text()
        )

    async def _assert_latest_consume(
        self, coupon_id: str, mobile: str, order_id: str, exc: Exception
    ) -> None:
        """savepoint 释放后确认核销行已随支付一起落账。"""
        latest = await self._inventory_repo.get_latest_state(
            coupon_id, mobile, authority=settings.COUPON_AUTHORITY
        )
        if (
            latest is None
            or latest["status"] != CouponStatus.CONSUME
            or str(latest.get("order_no", "") or "") != order_id
        ):
            raise ValueError("优惠券核销状态异常，请对账处理") from exc

    async def _try_resolve_mobile(self, user_id: str) -> str | None:
        try:
            from app.repository.customer_master_repo import CustomerMasterRepo
            from app.service.stored_value.member import MemberBalanceService

            return await MemberBalanceService(
                customer_repo=CustomerMasterRepo(self._order_repo._db)
            ).resolve_mobile(user_id)
        except ValueError:
            logger.debug("订单用户 %s 未识别为会员，跳过券联动", user_id)
            return None

    @staticmethod
    def _total_fen(order: Order) -> int:
        from app.utils import yuan_to_fen

        return yuan_to_fen(order.total_amount)
