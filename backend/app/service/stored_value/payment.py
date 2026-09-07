"""订单储值支付与组合支付服务。"""

from app.config import settings
from app.models.order import Order, OrderStatus
from app.models.stored_value import BalanceBizType, BalanceSource
from app.repository.order_repo import OrderRepo
from app.service.integrations.wechat_pay import WechatPayIntegrationService
from app.service.order.payment_state import (
    PAYMENT_METHOD_COMBINED,
    PAYMENT_STATUS_PARTIAL,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_UNPAID,
    PaymentSession,
    build_balance_payment,
    build_combined_payment,
    build_mock_payment_session,
    build_order_description,
    compute_remain_fen,
    dumps_payment,
    extract_openid,
    loads_payment,
    now_text,
    status_value,
)
from app.service.stored_value.member import MemberBalanceService
from app.utils import yuan_to_fen


class StoredValueOrderPaymentService:
    """负责用储值余额支付订单（全额或组合差额）。"""

    def __init__(
        self,
        order_repo: OrderRepo | None = None,
        member_service: MemberBalanceService | None = None,
        wechat_pay_service: WechatPayIntegrationService | None = None,
    ) -> None:
        self._order_repo = order_repo or OrderRepo(None)
        self._member_service = member_service or MemberBalanceService()
        self._wechat_pay_service = wechat_pay_service or WechatPayIntegrationService()

    async def pay_order_with_balance(self, order_id: str, *, user_id: str) -> dict:
        """订单全额使用储值余额支付（防超扣，幂等）。"""
        async with self._order_repo.transaction():
            order = await self._owned_order(order_id, user_id)
            if status_value(order) == OrderStatus.CANCELLED.value:
                raise ValueError("订单已取消")
            payment = loads_payment(order.payment)
            payment_status = str(payment.get("status", PAYMENT_STATUS_UNPAID))
            if payment_status == PAYMENT_STATUS_PAID:
                from app.service.coupon import CouponService
                from app.service.points.payment import PointsPaymentService

                await CouponService(order_repo=self._order_repo).consume_on_payment(
                    order
                )
                await PointsPaymentService(
                    order_repo=self._order_repo
                ).award_on_payment(order)
                return self._serialize_order_payment(order, payment)
            if (
                payment_status == PAYMENT_STATUS_PARTIAL
                and int(payment.get("balanceFen", 0) or 0) > 0
            ):
                raise ValueError("订单已部分支付，请完成剩余支付")
            total_fen = self._total_fen(order)
            coupon_fen = int(payment.get("couponFen", 0) or 0)
            points_fen = int(payment.get("pointsFen", 0) or 0)
            pay_fen = compute_remain_fen(total_fen, coupon_fen, 0, points_fen)
            mobile = await self._member_service.resolve_mobile(user_id)
            if pay_fen > 0:
                deducted = await self._member_service.deduct(
                    user_id=user_id,
                    mobile=mobile,
                    amount_fen=pay_fen,
                    biz_type=BalanceBizType.ORDER_PAY,
                    biz_id=order.id,
                    unique_id=f"order_pay:{order.id}",
                    source=BalanceSource.ORDER,
                )
                if deducted is None:
                    raise ValueError("储值余额不足")
            now = now_text()
            paid_payment = build_balance_payment(now, pay_fen)
            # 快照合并顺序不敏感：保留券/积分字段，支付核销与发分依赖它们
            paid_payment["couponId"] = str(payment.get("couponId", "") or "")
            paid_payment["couponFen"] = int(payment.get("couponFen", 0) or 0)
            paid_payment["pointsFen"] = int(payment.get("pointsFen", 0) or 0)
            paid_payment["pointsUsed"] = int(payment.get("pointsUsed", 0) or 0)
            updated = await self._order_repo.update_payment_to_paid_if_unpaid_or_partial_active(
                order.id,
                dumps_payment(paid_payment),
                now,
            )
            if updated is None:
                raise ValueError("订单支付状态更新冲突")
            from app.service.coupon import CouponService
            from app.service.points.payment import PointsPaymentService

            await CouponService(order_repo=self._order_repo).consume_on_payment(updated)
            await PointsPaymentService(order_repo=self._order_repo).award_on_payment(
                updated
            )
            return self._serialize_order_payment(updated, paid_payment)

    async def prepare_combined_payment(
        self,
        order_id: str,
        *,
        user_id: str,
        balance_fen: int,
    ) -> dict:
        """组合支付：先扣储值余额，再返回差额支付会话。

        剩余支付会话在扣款事务外预先构造：预下单失败时不扣款、
        不写部分支付快照，整体回滚语义由“先会话后扣款”保证。
        """
        order = await self._owned_order(order_id, user_id)
        if status_value(order) == OrderStatus.CANCELLED.value:
            raise ValueError("订单已取消")
        payment = loads_payment(order.payment)
        payment_status = str(payment.get("status", PAYMENT_STATUS_UNPAID))
        if payment_status == PAYMENT_STATUS_PAID:
            raise ValueError("订单已支付")
        if (
            payment_status == PAYMENT_STATUS_PARTIAL
            and int(payment.get("balanceFen", 0) or 0) > 0
        ):
            raise ValueError("订单已部分支付，请完成剩余支付")
        total_fen = self._total_fen(order)
        coupon_fen = int(payment.get("couponFen", 0) or 0)
        points_fen = int(payment.get("pointsFen", 0) or 0)
        remain_before_balance = compute_remain_fen(total_fen, coupon_fen, 0, points_fen)
        if balance_fen <= 0 or balance_fen >= remain_before_balance:
            raise ValueError(
                "组合支付余额部分必须大于 0 且小于订单总额（券/积分后以剩余应付为准）"
            )
        remain_fen = compute_remain_fen(total_fen, coupon_fen, balance_fen, points_fen)
        outer_payment = dict(payment)
        # 扣款提交前先构造剩余支付会话：微信预下单、openid、配置任一失败
        # 都直接抛错，此时余额未动、订单仍为未支付，可自然重试。
        # 微信预下单以订单号为幂等键，中止后重发起可复用或由微信侧去重。
        remainder = await self._build_remainder_session(order, remain_fen)
        async with self._order_repo.transaction():
            order = await self._owned_order(order_id, user_id)
            if status_value(order) == OrderStatus.CANCELLED.value:
                raise ValueError("订单已取消")
            payment = loads_payment(order.payment)
            payment_status = str(payment.get("status", PAYMENT_STATUS_UNPAID))
            if payment_status == PAYMENT_STATUS_PAID:
                raise ValueError("订单已支付")
            if (
                payment_status == PAYMENT_STATUS_PARTIAL
                and int(payment.get("balanceFen", 0) or 0) > 0
            ):
                raise ValueError("订单已部分支付，请完成剩余支付")
            # 并发快照一致性：事务内按最新订单重算全部金额，会话金额
            # 与重算不一致说明券/积分快照在会话生成后发生变化，
            # 必须回滚本次扣款并要求重新发起，禁止写入旧快照。
            # 支付快照整体亦做全等比对：任何并发改动（状态/方式/腿）
            # 都触发中止；微信预下单按订单号幂等，重发起可复用。
            if dumps_payment(payment) != dumps_payment(outer_payment):
                raise ValueError("订单支付快照发生变化，请重新发起支付")
            fresh_total_fen = self._total_fen(order)
            fresh_coupon_fen = int(payment.get("couponFen", 0) or 0)
            fresh_points_fen = int(payment.get("pointsFen", 0) or 0)
            fresh_remain_before = compute_remain_fen(
                fresh_total_fen, fresh_coupon_fen, 0, fresh_points_fen
            )
            fresh_remain_fen = compute_remain_fen(
                fresh_total_fen, fresh_coupon_fen, balance_fen, fresh_points_fen
            )
            if (
                fresh_total_fen != total_fen
                or fresh_coupon_fen != coupon_fen
                or fresh_points_fen != points_fen
                or fresh_remain_fen != remain_fen
            ):
                raise ValueError("订单支付金额发生变化，请重新发起支付")
            if balance_fen <= 0 or balance_fen >= fresh_remain_before:
                raise ValueError(
                    "组合支付余额部分必须大于 0 且小于订单总额（券/积分后以剩余应付为准）"
                )
            # 同连接固化：余额扣款必须复用订单仓储当前事务连接，
            # 否则扣款与订单更新不在同一事务，回滚无法覆盖扣款。
            if self._member_service.db_handle is not self._order_repo._db:
                raise ValueError("储值服务与订单仓储不在同一事务连接，拒绝扣款")
            mobile = await self._member_service.resolve_mobile(user_id)
            deducted = await self._member_service.deduct(
                user_id=user_id,
                mobile=mobile,
                amount_fen=balance_fen,
                biz_type=BalanceBizType.ORDER_PAY,
                biz_id=order.id,
                unique_id=f"combined_pay:{order.id}",
                source=BalanceSource.ORDER,
            )
            if deducted is None:
                raise ValueError("储值余额不足")
            now = now_text()
            partial_payment = build_combined_payment(now, balance_fen, remain_fen)
            partial_payment["couponId"] = str(payment.get("couponId", "") or "")
            partial_payment["couponFen"] = int(payment.get("couponFen", 0) or 0)
            partial_payment["pointsFen"] = int(payment.get("pointsFen", 0) or 0)
            partial_payment["pointsUsed"] = int(payment.get("pointsUsed", 0) or 0)
            updated = await self._order_repo.update_payment_to_partial_if_unpaid_or_partial_active(
                order.id,
                dumps_payment(partial_payment),
                now,
            )
            if updated is None:
                raise ValueError("订单支付状态更新冲突")
        return {
            "orderId": order.id,
            "payment": {
                "status": PAYMENT_STATUS_PARTIAL,
                "method": PAYMENT_METHOD_COMBINED,
                "balanceFen": balance_fen,
                "remainFen": remain_fen,
            },
            "remainderPayment": remainder,
        }

    async def refund_order_balance(self, order: Order) -> None:
        """按订单支付 JSON 中的余额部分原路退回（组合支付取消/超时）。"""
        payment = loads_payment(order.payment)
        balance_fen = int(payment.get("balanceFen", 0) or 0)
        if balance_fen <= 0:
            return
        mobile = await self._member_service.resolve_mobile(order.user_id)
        await self._member_service.credit(
            user_id=order.user_id,
            mobile=mobile,
            amount_fen=balance_fen,
            biz_type=BalanceBizType.ORDER_REFUND,
            biz_id=order.id,
            unique_id=f"order_refund:{order.id}",
            source=BalanceSource.ORDER,
        )

    async def _owned_order(self, order_id: str, user_id: str) -> Order:
        order = await self._order_repo.get_order(order_id)
        if order is None or order.user_id != user_id:
            raise ValueError("订单不存在")
        return order

    async def _build_remainder_session(
        self,
        order: Order,
        remain_fen: int,
    ) -> dict:
        if self._wechat_pay_service.is_ready():
            payer_openid = extract_openid(order.user_id)
            if not payer_openid:
                raise ValueError("当前用户未绑定微信 openid")
            prepay = await self._wechat_pay_service.create_jsapi_prepay(
                order_id=order.id,
                total_fen=remain_fen,
                description=build_order_description(order),
                payer_openid=payer_openid,
            )
            return {
                "mode": "wechat",
                "orderId": order.id,
                "paymentMethod": "wechat",
                "paymentStatus": PAYMENT_STATUS_UNPAID,
                "paymentParams": self._wechat_pay_service.build_payment_params(
                    prepay.prepay_id,
                    signer=self._wechat_pay_service.sign_with_rsa,
                ),
            }
        if not settings.ALLOW_MOCK_PAYMENT:
            raise ValueError("微信支付未配置，生产环境不提供 mock 支付")
        session = build_mock_payment_session(order.id)
        return self._serialize_session(session)

    @staticmethod
    def _serialize_session(session: PaymentSession) -> dict:
        return {
            "mode": session.mode,
            "orderId": session.order_id,
            "paymentMethod": session.payment_method,
            "paymentStatus": session.payment_status,
            "paymentParams": session.payload,
        }

    @staticmethod
    def _total_fen(order: Order) -> int:
        return yuan_to_fen(order.total_amount)

    @staticmethod
    def _serialize_order_payment(order: Order, payment: dict) -> dict:
        return {
            "orderId": order.id,
            "status": status_value(order),
            "paymentStatus": payment.get("status", ""),
            "paymentMethod": payment.get("method", ""),
            "balanceFen": payment.get("balanceFen", 0),
            "paidAt": payment.get("paidAt", ""),
        }
