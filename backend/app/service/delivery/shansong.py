"""闪送适配器占位实现，仅用于内部契约和开发环境。"""

from datetime import datetime, timedelta, timezone

from app.models.delivery import (
    DeliveryOrder,
    DeliveryQuote,
    DeliveryQuoteStatus,
    FulfillmentMethod,
)
from app.service.delivery.provider import DeliveryQuoteRequest


class ShansongProvider:
    """真实开放平台资料取得前的不可用适配器。"""

    provider_name = "shansong"

    async def quote(self, request: DeliveryQuoteRequest) -> DeliveryQuote:
        """未配置真实平台时返回不可用，不伪造配送费。"""
        return DeliveryQuote(
            quote_id=request.request_id,
            user_id=request.user_id,
            fulfillment_method=FulfillmentMethod.BEIJING_DELIVERY,
            request_hash=request.request_id,
            goods_total_fen=request.goods_total_fen,
            delivery_fee_fen=None,
            quote_total_fen=None,
            status=DeliveryQuoteStatus.PROVIDER_UNAVAILABLE,
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            provider=self.provider_name,
            message="闪送开放平台尚未配置，请联系客服确认配送费用",
        )

    async def create_order(
        self, request: DeliveryQuoteRequest, quote: DeliveryQuote
    ) -> DeliveryOrder:
        raise RuntimeError("闪送开放平台尚未配置")

    async def cancel_order(self, provider_order_id: str, reason: str) -> DeliveryOrder:
        raise RuntimeError("闪送开放平台尚未配置")
