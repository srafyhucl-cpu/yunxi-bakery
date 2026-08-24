"""订单支付入口服务。"""

from app.constants.storefront import STOREFRONT_DEMO_USER_ID
from app.service.order.payment_runtime import OrderPaymentRuntimeService, PaymentSession


class OrderPaymentService:
    """负责订单支付相关公开入口。"""

    def __init__(self, payment_service: OrderPaymentRuntimeService) -> None:
        self._payment_service = payment_service

    async def confirm_mock_payment(
        self,
        order_id: str,
        *,
        user_id: str = STOREFRONT_DEMO_USER_ID,
    ) -> dict:
        """确认 mock 支付。"""
        return await self._payment_service.confirm_mock_payment(
            order_id, user_id=user_id
        )

    async def prepare_payment(
        self,
        order_id: str,
        *,
        user_id: str = STOREFRONT_DEMO_USER_ID,
    ) -> dict:
        """准备订单支付参数。"""
        session = await self._payment_service.prepare_payment(order_id, user_id=user_id)
        return self._serialize_session(session)

    async def handle_wechat_payment_notify(
        self,
        *,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> dict:
        """处理微信支付结果通知。"""
        return await self._payment_service.handle_wechat_payment_notify(
            raw_body=raw_body,
            headers=headers,
        )

    def _serialize_session(self, session: PaymentSession) -> dict:
        return {
            "mode": session.mode,
            "orderId": session.order_id,
            "paymentMethod": session.payment_method,
            "paymentStatus": session.payment_status,
            "paymentParams": session.payload,
        }


__all__ = ["OrderPaymentService"]
