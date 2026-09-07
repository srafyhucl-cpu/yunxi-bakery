"""微信退款通知业务闭环：事件事实、补偿、对账案件同一事务。

语义：
- 同一商户退款单号只消费一次，重复与乱序通知直接确认不重放。
- 全额退款自动执行三腿补偿（券退回、积分核验退回、余额原路退回）。
- 部分退款只记录事件事实与累计，补偿转人工案件（腿幂等键按订单维度）。
- 累计退款超过实付直接拒绝并建案，不执行任何补偿。
- 通知与查询共用同一应用函数，仅来源标记不同。
"""

from app.config import settings
from app.logger import setup_logger
from app.models.order import Order
from app.repository.order_repo import OrderRepo
from app.repository.points_refund_reconcile_repo import PointsRefundReconcileRepo
from app.repository.wechat_refund_event_repo import WechatRefundEventRepo
from app.service.order.payment_state import (
    compute_remain_fen,
    dumps_payment,
    loads_payment,
    now_text,
)
from app.service.order.wechat_normalizers import RefundNotify, RefundQueryResult
from app.utils import yuan_to_fen

logger = setup_logger()

REFUND_CASE_PREFIX = "refund:"
CAS_RETRY_LIMIT = 3

# 退款回调结构化确认语义（P0-2），不再靠字典 rejected 字符串判断。
OUTCOME_ACKNOWLEDGED = "acknowledged"
OUTCOME_RETRYABLE = "retryable"
OUTCOME_REJECTED_RECORDED = "rejected_recorded"
OUTCOME_DUPLICATE = "duplicate"


def is_terminal_success_kind(kind: str) -> bool:
    """终态确认语义：微信侧收到后不得再重试。"""
    return kind in (
        OUTCOME_ACKNOWLEDGED,
        OUTCOME_REJECTED_RECORDED,
        OUTCOME_DUPLICATE,
    )


class WechatRefundNotificationService:
    """负责微信退款通知与查询恢复的端到端消费。"""

    def __init__(self, order_repo: OrderRepo) -> None:
        self._order_repo = order_repo
        self._event_repo = WechatRefundEventRepo(order_repo._db)
        self._reconcile_repo = PointsRefundReconcileRepo(order_repo._db)

    async def apply_refund_notify(self, notify: RefundNotify) -> dict:
        """消费退款通知，返回终态，重复直接确认。"""
        async with self._order_repo.transaction():
            return await self._apply_event(
                out_trade_no=notify.out_trade_no,
                out_refund_no=notify.out_refund_no,
                refund_id=notify.refund_id,
                transaction_id=notify.transaction_id,
                refund_status=notify.refund_status,
                total_fen=notify.total_fen,
                refund_fen=notify.refund_fen,
                payer_total_fen=notify.payer_total_fen,
                payer_refund_fen=notify.payer_refund_fen,
                source="notify",
                mchid=notify.mchid,
            )

    async def apply_refund_query(
        self, result: RefundQueryResult, *, payer_total_fen: int
    ) -> dict:
        """由退款查询恢复，幂等键与通知共用，乱序安全。"""
        async with self._order_repo.transaction():
            return await self._apply_event(
                out_trade_no=result.out_trade_no,
                out_refund_no=result.out_refund_no,
                refund_id=result.refund_id,
                transaction_id=result.transaction_id,
                refund_status=result.refund_status,
                total_fen=result.total_fen,
                refund_fen=result.refund_fen,
                payer_total_fen=payer_total_fen,
                payer_refund_fen=result.refund_fen,
                source="query",
                mchid=result.mchid,
            )

    async def _apply_event(
        self,
        *,
        out_trade_no: str,
        out_refund_no: str,
        refund_id: str,
        transaction_id: str,
        refund_status: str,
        total_fen: int,
        refund_fen: int,
        payer_total_fen: int,
        payer_refund_fen: int,
        source: str,
        mchid: str,
    ) -> dict:
        if mchid != settings.WECHAT_PAY_MCH_ID:
            raise ValueError("微信退款通知商户号不匹配")
        if refund_status != "SUCCESS":
            return {
                "kind": OUTCOME_ACKNOWLEDGED,
                "orderId": out_trade_no,
                "outRefundNo": out_refund_no,
                "ignored": True,
                "refundStatus": refund_status,
            }
        order = await self._order_repo.get_order(out_trade_no)
        if order is None:
            raise ValueError("订单不存在")
        if payer_refund_fen <= 0 or refund_fen <= 0:
            raise ValueError("退款金额无效")
        try:
            order_total_fen = yuan_to_fen(order.total_amount)
        except ValueError:
            raise ValueError("订单金额无效") from None
        if total_fen != order_total_fen:
            await self._open_case(
                order,
                f"{REFUND_CASE_PREFIX}total_mismatch:{out_refund_no}",
                payer_refund_fen,
                f"原支付不一致 notify={total_fen} expected={order_total_fen}",
            )
            return {
                "kind": OUTCOME_REJECTED_RECORDED,
                "orderId": order.id,
                "outRefundNo": out_refund_no,
                "rejected": "原支付金额与订单不一致，已建案",
            }
        payment = loads_payment(order.payment)
        bound_transaction_id = str(payment.get("transactionId", "") or "")
        if bound_transaction_id and bound_transaction_id != transaction_id:
            await self._open_case(
                order,
                f"{REFUND_CASE_PREFIX}transaction_mismatch:{out_refund_no}",
                payer_refund_fen,
                f"交易号归属不一致 notify={transaction_id} bound={bound_transaction_id}",
            )
            return {
                "kind": OUTCOME_REJECTED_RECORDED,
                "orderId": order.id,
                "outRefundNo": out_refund_no,
                "rejected": "退款交易号与订单不一致，已建案",
            }
        external_paid_fen = compute_remain_fen(
            yuan_to_fen(order.total_amount),
            int(payment.get("couponFen", 0) or 0),
            int(payment.get("balanceFen", 0) or 0),
            int(payment.get("pointsFen", 0) or 0),
        )
        if payer_total_fen != external_paid_fen:
            await self._open_case(
                order,
                f"{REFUND_CASE_PREFIX}payer_total_mismatch:{out_refund_no}",
                payer_refund_fen,
                f"实付不一致 notify={payer_total_fen} expected={external_paid_fen}",
            )
            return {
                "kind": OUTCOME_REJECTED_RECORDED,
                "orderId": order.id,
                "outRefundNo": out_refund_no,
                "rejected": "实付金额与订单不一致，已建案",
            }
        created = await self._event_repo.insert_event(
            out_refund_no=out_refund_no,
            order_id=order.id,
            transaction_id=transaction_id,
            refund_id=refund_id,
            total_fen=total_fen,
            refund_fen=refund_fen,
            payer_refund_fen=payer_refund_fen,
            refund_status=refund_status,
            source=source,
        )
        if not created:
            return {
                "kind": OUTCOME_DUPLICATE,
                "orderId": order.id,
                "outRefundNo": out_refund_no,
                "duplicate": True,
            }
        accumulated = await self._event_repo.sum_payer_refund_fen(order.id)
        if accumulated > external_paid_fen:
            await self._open_case(
                order,
                f"{REFUND_CASE_PREFIX}over_refund:{out_refund_no}",
                payer_refund_fen,
                f"累计退款={accumulated} 超过实付={external_paid_fen}",
            )
            await self._record_refund_bookkeeping(order, accumulated, external_paid_fen)
            return {
                "kind": OUTCOME_REJECTED_RECORDED,
                "orderId": order.id,
                "outRefundNo": out_refund_no,
                "rejected": "累计退款超过实付，已建案",
            }
        if accumulated == external_paid_fen:
            await self._compensate_full_refund(order)
        else:
            await self._open_case(
                order,
                f"{REFUND_CASE_PREFIX}partial:{out_refund_no}",
                payer_refund_fen,
                f"部分退款累计={accumulated}/{external_paid_fen}，补偿转人工",
            )
        await self._record_refund_bookkeeping(order, accumulated, external_paid_fen)
        return {
            "kind": OUTCOME_ACKNOWLEDGED,
            "orderId": order.id,
            "outRefundNo": out_refund_no,
            "accumulatedFen": accumulated,
            "externalPaidFen": external_paid_fen,
        }

    async def _compensate_full_refund(self, order: Order) -> None:
        """全额退款三腿补偿，腿各自幂等，同一事务提交。"""
        from app.repository.balance_ledger_repo import BalanceLedgerRepo
        from app.repository.customer_master_repo import CustomerMasterRepo
        from app.repository.member_balance_repo import MemberBalanceRepo
        from app.service.coupon import CouponService
        from app.service.points.payment import PointsPaymentService
        from app.service.stored_value.member import MemberBalanceService
        from app.service.stored_value.payment import StoredValueOrderPaymentService

        db = self._order_repo._db
        await CouponService(order_repo=self._order_repo).refund_coupon(order)
        await PointsPaymentService(order_repo=self._order_repo).refund_points(order)
        member_service = MemberBalanceService(
            balance_repo=MemberBalanceRepo(db),
            ledger_repo=BalanceLedgerRepo(db),
            customer_repo=CustomerMasterRepo(db),
        )
        await StoredValueOrderPaymentService(
            order_repo=self._order_repo, member_service=member_service
        ).refund_order_balance(order)

    async def _open_case(
        self, order: Order, unique_id: str, amount: int, note: str
    ) -> None:
        """追加人工对账案件，同单同因幂等。"""
        try:
            mobile = str(loads_payment(order.payment).get("mobile", "") or "")
        except ValueError:
            mobile = ""
        await self._reconcile_repo.append(
            order_id=order.id,
            mobile=mobile,
            unique_id=unique_id,
            reason=unique_id,
            amount=amount,
            note=note,
        )

    async def _record_refund_bookkeeping(
        self, order: Order, accumulated: int, external_paid_fen: int
    ) -> None:
        """CAS 更新订单退款累计，防止并发退款丢失累计。"""
        for _ in range(CAS_RETRY_LIMIT):
            latest = await self._order_repo.get_order(order.id)
            if latest is None:
                raise ValueError("订单不存在")
            payment = loads_payment(latest.payment)
            expected = latest.payment
            payment["refundFen"] = accumulated
            if accumulated > external_paid_fen:
                payment["refundStatus"] = "over"
            elif accumulated == external_paid_fen:
                payment["refundStatus"] = "full"
            else:
                payment["refundStatus"] = "partial"
            updated = await self._order_repo.update_payment_cas(
                latest.id, expected, dumps_payment(payment), now_text()
            )
            if updated is not None:
                return
        raise ValueError("订单退款累计更新冲突")
