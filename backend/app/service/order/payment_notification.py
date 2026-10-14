"""微信支付交易通知的业务校验与入账。"""

from app.config import settings
from app.models.order import Order, OrderEvent, OrderStatus
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.wechat_refund_event_repo import WechatRefundEventRepo
from app.service.order.payment_state import (
    PAYMENT_METHOD_WECHAT,
    PAYMENT_STATUS_EXPIRED,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PARTIAL,
    PAYMENT_STATUS_UNPAID,
    dumps_payment,
    loads_payment,
    now_text,
    resolve_external_paid_fen,
    status_value,
)
from app.service.order.wechat_normalizers import (
    PayNotifyNormalizer,
    WechatProtocolError,
)
from app.utils import yuan_to_fen


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
        await self.validate_order_amount(
            order,
            notify.total_fen,
            mismatch_message="微信支付通知金额不匹配",
        )

    async def validate_order_amount(
        self,
        order: Order,
        external_paid_fen: int,
        *,
        mismatch_message: str,
    ) -> None:
        """按订单支付快照严格校验微信外部支付腿金额。"""
        try:
            total_order_fen = yuan_to_fen(order.total_amount)
        except ValueError:
            raise ValueError("订单金额无效") from None
        payment = loads_payment(order.payment)
        expected_fen = resolve_external_paid_fen(payment, total_order_fen)
        if expected_fen <= 0:
            raise ValueError("订单无需外部支付")
        if external_paid_fen != expected_fen:
            raise ValueError(mismatch_message)

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
        payment = loads_payment(order.payment)
        await self._validate_refund_transaction_identity(order.id, transaction_id)
        payment_status = str(payment.get("status", PAYMENT_STATUS_UNPAID))
        if status_value(order) == OrderStatus.CANCELLED.value:
            return await self._record_cancelled_external_payment(
                order,
                payment=payment,
                payment_status=payment_status,
                paid_at=paid_at,
                transaction_id=transaction_id,
            )
        refund_terminal = str(payment.get("refundStatus", "")) in {"full", "over"}
        if payment_status == PAYMENT_STATUS_PAID:
            if str(payment.get("transactionId", "")) == transaction_id:
                return order
            raise ValueError("订单已绑定其他支付交易号")
        if refund_terminal and payment_status not in {
            PAYMENT_STATUS_UNPAID,
            PAYMENT_STATUS_PARTIAL,
        }:
            return order
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
        transaction_owner = await self._claim_transaction(transaction_id, order_id)
        if transaction_owner != order_id:
            raise ValueError("微信交易号已绑定其他订单")
        await self._record_paid_event(updated, payment["paidAt"])
        if refund_terminal:
            return updated
        # 微信到账后先核销券再发分：核销在支付事务内，双花 ValueError 可回滚支付；
        # 发分内部自 commit 会破坏回滚边界，必须放在核销之后
        from app.service.coupon import CouponService
        from app.service.points.payment import PointsPaymentService

        await CouponService(order_repo=self._order_repo).consume_on_payment(updated)
        await PointsPaymentService(order_repo=self._order_repo).award_on_payment(
            updated
        )
        return updated

    async def _record_cancelled_external_payment(
        self,
        order: Order,
        *,
        payment: dict,
        payment_status: str,
        paid_at: str,
        transaction_id: str,
    ) -> Order:
        """记录取消后的外部到账，保持取消终态并创建待退款事实。"""
        if not transaction_id:
            raise ValueError("微信支付通知缺少交易号")
        if payment_status == PAYMENT_STATUS_PAID:
            if str(payment.get("transactionId", "")) == transaction_id:
                return order
            raise ValueError("订单已绑定其他支付交易号")
        try:
            total_fen = yuan_to_fen(order.total_amount)
        except ValueError:
            raise ValueError("订单金额无效") from None
        external_paid_fen = resolve_external_paid_fen(payment, total_fen)
        if external_paid_fen <= 0:
            raise ValueError("订单无需外部支付")
        refund_status = str(payment.get("refundStatus", "") or "")
        payment.update(
            {
                "status": PAYMENT_STATUS_PAID,
                "method": str(payment.get("method", "") or PAYMENT_METHOD_WECHAT),
                "paidAt": paid_at or now_text(),
                "transactionId": transaction_id,
            }
        )
        if not refund_status:
            payment.update(
                {
                    "refundStatus": "pending",
                    "refundAmountFen": external_paid_fen,
                    "refundReason": "late_payment_after_cancellation",
                }
            )
        updated = await self._order_repo.record_cancelled_external_payment(
            order.id, dumps_payment(payment), payment["paidAt"]
        )
        if updated is None:
            latest = await self._order_repo.get_order(order.id)
            if latest is None:
                raise ValueError("订单不存在")
            latest_payment = loads_payment(latest.payment)
            if status_value(latest) != OrderStatus.CANCELLED.value:
                raise ValueError("订单支付状态更新冲突")
            if (
                str(latest_payment.get("status", PAYMENT_STATUS_UNPAID))
                == PAYMENT_STATUS_PAID
                and str(latest_payment.get("transactionId", "")) == transaction_id
            ):
                return latest
            raise ValueError("订单支付状态更新冲突")
        transaction_owner = await self._claim_transaction(transaction_id, order.id)
        if transaction_owner != order.id:
            raise ValueError("微信交易号已绑定其他订单")
        await self._record_paid_event(updated, payment["paidAt"])
        return updated

    async def _validate_refund_transaction_identity(
        self, order_id: str, transaction_id: str
    ) -> None:
        """退款先到时，迟到支付必须命中退款事实中的同一交易号。"""
        refund_event_repo = WechatRefundEventRepo(self._order_repo._db)
        transaction_ids = set(await refund_event_repo.list_transaction_ids(order_id))
        if transaction_ids and (
            len(transaction_ids) != 1 or transaction_id not in transaction_ids
        ):
            raise ValueError("退款交易号与订单不一致")

    async def claim_refund_transaction(self, transaction_id: str, order_id: str) -> str:
        """退款先到时认领原支付交易号并返回最终归属。"""
        return await self._claim_transaction(
            transaction_id,
            order_id,
            require_payment_snapshot=False,
        )

    async def _claim_transaction(
        self,
        transaction_id: str,
        order_id: str,
        *,
        require_payment_snapshot: bool = True,
    ) -> str:
        existing_order_id = await self._order_repo.get_payment_transaction_order_id(
            transaction_id
        )
        if existing_order_id and existing_order_id != order_id:
            return existing_order_id
        claimed = await self._order_repo.claim_payment_transaction(
            transaction_id, order_id, now_text()
        )
        if claimed:
            return order_id
        transaction_owner = await self._order_repo.get_payment_transaction_order_id(
            transaction_id
        )
        if transaction_owner != order_id:
            return transaction_owner or ""
        if not require_payment_snapshot:
            return transaction_owner
        latest = await self._order_repo.get_order(order_id)
        if latest is None:
            raise ValueError("订单不存在")
        latest_payment = loads_payment(latest.payment)
        if str(latest_payment.get("transactionId", "")) == transaction_id:
            return transaction_owner
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
