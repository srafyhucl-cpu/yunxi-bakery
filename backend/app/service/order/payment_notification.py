"""微信支付交易通知的业务校验与入账。"""

from decimal import Decimal, InvalidOperation

from app.config import settings
from app.models.order import Order, OrderEvent, OrderStatus
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.service.order.payment_state import (
    PAYMENT_METHOD_WECHAT,
    PAYMENT_STATUS_EXPIRED,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PARTIAL,
    PAYMENT_STATUS_UNPAID,
    compute_remain_fen,
    dumps_payment,
    loads_payment,
    now_text,
    status_value,
)
from app.service.order.wechat_normalizers import (
    PayNotifyNormalizer,
    WechatProtocolError,
)


class WechatPaymentNotificationService:
    """负责微信通知字段校验、交易号认领和支付事件写入。"""

    def __init__(
        self,
        order_repo: OrderRepo,
        event_repo: OrderEventRepo | None = None,
    ) -> None:
        self._order_repo = order_repo
        self._event_repo = event_repo
        self._pay_notify_normalizer = PayNotifyNormalizer()

    async def validate_transaction(self, transaction: dict) -> None:
        """校验微信通知的商户、应用、金额、币种和交易号。

        B3.5（评审问题 4）：币种取 v3 报文 `amount.currency`（顶层无 currency），
        字段校验委托独立 PayNotifyNormalizer，逐字段负向用例见
        tests/service/test_wechat_normalizers.py。
        """
        try:
            notify = self._pay_notify_normalizer.normalize(transaction)
        except WechatProtocolError as exc:
            raise ValueError(str(exc)) from exc
        if notify.mchid != settings.WECHAT_PAY_MCH_ID:
            raise ValueError("微信支付通知商户号不匹配")
        if notify.appid != settings.WECHAT_MINIAPP_APP_ID:
            raise ValueError("微信支付通知 appid 不匹配")
        transaction_id = notify.transaction_id
        if not transaction_id:
            raise ValueError("微信支付通知缺少交易号")
        order_id = notify.out_trade_no
        order = await self._order_repo.get_order(order_id)
        if order is None:
            raise ValueError("订单不存在")
        try:
            total_order_fen = int(Decimal(str(order.total_amount)) * 100)
        except (InvalidOperation, ValueError):
            raise ValueError("订单金额无效") from None
        payment = loads_payment(order.payment)
        coupon_fen = int(payment.get("couponFen", 0) or 0)
        balance_fen = int(payment.get("balanceFen", 0) or 0)
        points_fen = int(payment.get("pointsFen", 0) or 0)
        expected_fen = compute_remain_fen(
            total_order_fen, coupon_fen, balance_fen, points_fen
        )
        if expected_fen <= 0:
            raise ValueError("订单无需外部支付")
        if notify.total_fen != expected_fen:
            raise ValueError("微信支付通知金额不匹配")

    async def mark_paid(
        self,
        order_id: str,
        *,
        paid_at: str,
        transaction_id: str,
    ) -> Order:
        """原子认领交易号并把订单置为已支付。"""
        order = await self._order_repo.get_order(order_id)
        if order is None:
            raise ValueError("订单不存在")
        if status_value(order) == OrderStatus.CANCELLED.value:
            raise ValueError("订单已取消")
        payment = loads_payment(order.payment)
        payment_status = str(payment.get("status", PAYMENT_STATUS_UNPAID))
        if payment_status == PAYMENT_STATUS_PAID:
            if str(payment.get("transactionId", "")) == transaction_id:
                return order
            raise ValueError("订单已绑定其他支付交易号")
        if payment_status == PAYMENT_STATUS_EXPIRED:
            raise ValueError("订单支付已超时")
        if not transaction_id:
            raise ValueError("微信支付通知缺少交易号")
        if payment_status == PAYMENT_STATUS_PARTIAL:
            payment.update(
                {
                    "status": PAYMENT_STATUS_PAID,
                    "paidAt": paid_at or now_text(),
                    "transactionId": transaction_id,
                }
            )
            updated = await self._order_repo.update_payment_to_paid_if_unpaid_or_partial_active(
                order.id, dumps_payment(payment), payment["paidAt"]
            )
        else:
            payment.update(
                {
                    "status": PAYMENT_STATUS_PAID,
                    "method": PAYMENT_METHOD_WECHAT,
                    "paidAt": paid_at or now_text(),
                    "transactionId": transaction_id,
                }
            )
            updated = await self._order_repo.update_payment_if_unpaid_active(
                order.id, dumps_payment(payment), payment["paidAt"]
            )
        if updated is None:
            latest = await self._order_repo.get_order(order.id)
            if latest is None:
                raise ValueError("订单不存在")
            latest_payment = loads_payment(latest.payment)
            if status_value(latest) == OrderStatus.CANCELLED.value:
                raise ValueError("订单已取消")
            if (
                str(latest_payment.get("status", PAYMENT_STATUS_UNPAID))
                == PAYMENT_STATUS_PAID
            ):
                if str(latest_payment.get("transactionId", "")) == transaction_id:
                    return latest
                raise ValueError("订单已绑定其他支付交易号")
            raise ValueError("订单支付状态更新冲突")
        await self._claim_transaction(transaction_id, order_id)
        await self._record_paid_event(updated, payment["paidAt"])
        # 微信到账后先核销券再发分：核销在支付事务内，双花 ValueError 可回滚支付；
        # 发分内部自 commit 会破坏回滚边界，必须放在核销之后
        from app.service.coupon import CouponService
        from app.service.points.payment import PointsPaymentService

        await CouponService(order_repo=self._order_repo).consume_on_payment(updated)
        await PointsPaymentService(order_repo=self._order_repo).award_on_payment(
            updated
        )
        return updated

    async def _claim_transaction(self, transaction_id: str, order_id: str) -> None:
        existing_order_id = await self._order_repo.get_payment_transaction_order_id(
            transaction_id
        )
        if existing_order_id and existing_order_id != order_id:
            raise ValueError("微信交易号已绑定其他订单")
        claimed = await self._order_repo.claim_payment_transaction(
            transaction_id, order_id, now_text()
        )
        if claimed:
            return
        existing_order_id = await self._order_repo.get_payment_transaction_order_id(
            transaction_id
        )
        if existing_order_id != order_id:
            raise ValueError("微信交易号已绑定其他订单")
        latest = await self._order_repo.get_order(order_id)
        if latest is None:
            raise ValueError("订单不存在")
        latest_payment = loads_payment(latest.payment)
        if str(latest_payment.get("transactionId", "")) == transaction_id:
            return
        raise ValueError("微信交易号重复通知状态异常")

    async def _record_paid_event(self, order: Order, paid_at: str) -> None:
        if self._event_repo is None:
            return
        await self._event_repo.add(
            OrderEvent(
                order_id=order.id,
                status=PAYMENT_STATUS_PAID,
                operator="wechat-pay",
                note="微信支付通知确认到账",
                created_at=paid_at,
            )
        )


__all__ = ["WechatPaymentNotificationService"]
