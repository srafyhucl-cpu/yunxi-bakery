"""储值余额域应用服务门面。"""

from app.models.order import Order
from app.service.stored_value.member import MemberBalanceService
from app.service.stored_value.payment import StoredValueOrderPaymentService
from app.service.stored_value.recharge import RechargeService


class StoredValueService:
    """储值余额域组合服务（充值 / 余额 / 订单储值支付）。"""

    def __init__(
        self,
        member_service: MemberBalanceService | None = None,
        recharge_service: RechargeService | None = None,
        payment_service: StoredValueOrderPaymentService | None = None,
    ) -> None:
        self._member_service = member_service or MemberBalanceService()
        self._recharge_service = recharge_service or RechargeService(
            member_service=self._member_service
        )
        self._payment_service = payment_service or StoredValueOrderPaymentService(
            member_service=self._member_service
        )

    @property
    def payment_service(self) -> StoredValueOrderPaymentService:
        """订单储值支付服务（供订单取消/超时退款复用）。"""
        return self._payment_service

    async def create_recharge(self, user_id: str, amount_fen: int) -> dict:
        """创建充值单。"""
        return await self._recharge_service.create_recharge(user_id, amount_fen)

    async def cancel_unpaid_recharge(
        self,
        recharge_id: str,
        *,
        user_id: str,
    ) -> dict:
        """取消未支付充值单。"""
        return await self._recharge_service.cancel_unpaid_recharge(
            recharge_id,
            user_id=user_id,
        )

    async def confirm_mock_recharge_payment(
        self,
        recharge_id: str,
        *,
        user_id: str,
    ) -> dict:
        """mock 支付确认充值。"""
        return await self._recharge_service.confirm_mock_recharge_payment(
            recharge_id,
            user_id=user_id,
        )

    async def list_user_recharges(self, user_id: str) -> list[dict]:
        """读取当前用户充值单列表。"""
        return await self._recharge_service.list_user_recharges(user_id)

    async def get_user_balance(self, user_id: str) -> dict:
        """读取会员储值余额与最近流水。"""
        return await self._member_service.get_balance(user_id)

    async def pay_order_with_balance(self, order_id: str, *, user_id: str) -> dict:
        """订单全额使用储值余额支付。"""
        return await self._payment_service.pay_order_with_balance(
            order_id,
            user_id=user_id,
        )

    async def prepare_combined_payment(
        self,
        order_id: str,
        *,
        user_id: str,
        balance_fen: int,
    ) -> dict:
        """组合支付：先扣余额部分，返回差额支付会话。"""
        return await self._payment_service.prepare_combined_payment(
            order_id,
            user_id=user_id,
            balance_fen=balance_fen,
        )

    async def refund_order_balance(self, order: Order) -> None:
        """按订单余额部分原路退回（组合支付取消/超时）。"""
        await self._payment_service.refund_order_balance(order)


__all__ = [
    "MemberBalanceService",
    "RechargeService",
    "StoredValueOrderPaymentService",
    "StoredValueService",
]
