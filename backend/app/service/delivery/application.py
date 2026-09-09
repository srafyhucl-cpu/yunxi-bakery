"""前台配送报价应用服务。"""

from datetime import datetime, timezone

from app.models.delivery import DeliveryQuote, DeliveryQuoteStatus, FulfillmentMethod
from app.repository.delivery_quote_repo import DeliveryQuoteRepo
from app.service.delivery.provider import (
    DeliveryProvider,
    DeliveryQuoteRequest,
    build_delivery_request_hash,
)


class DeliveryApplicationService:
    """编排配送报价并持久化报价快照。"""

    def __init__(
        self, provider: DeliveryProvider, quote_repo: DeliveryQuoteRepo
    ) -> None:
        self._provider = provider
        self._quote_repo = quote_repo

    async def quote(self, request: DeliveryQuoteRequest) -> DeliveryQuote:
        quote = await self._provider.quote(request)
        quote = self._with_request_hash(quote, request)
        await self._quote_repo.create(quote)
        return quote

    async def require_payable_quote(
        self,
        quote_id: str,
        user_id: str,
        goods_total_fen: int = 0,
    ) -> DeliveryQuote:
        """读取并校验可用于当前订单的配送报价。"""
        quote = await self._quote_repo.get_for_user(quote_id, user_id)
        if quote is None:
            raise ValueError("配送报价不存在")
        if quote.fulfillment_method is not FulfillmentMethod.BEIJING_DELIVERY:
            raise ValueError("配送报价履约方式不匹配")
        if (
            quote.status is not DeliveryQuoteStatus.QUOTED
            or quote.delivery_fee_fen is None
        ):
            raise ValueError("配送报价尚未确认，不能支付")
        if quote.delivery_fee_fen < 0:
            raise ValueError("配送报价金额无效，请重新报价")
        if quote.quote_total_fen != quote.goods_total_fen + quote.delivery_fee_fen:
            raise ValueError("配送报价金额无效，请重新报价")
        if quote.goods_total_fen != goods_total_fen:
            raise ValueError("配送报价与当前商品金额不一致，请重新报价")
        if self._is_expired(quote.expires_at):
            raise ValueError("配送报价已过期，请重新报价")
        return quote

    @staticmethod
    def _with_request_hash(
        quote: DeliveryQuote, request: DeliveryQuoteRequest
    ) -> DeliveryQuote:
        from dataclasses import replace

        return replace(quote, request_hash=build_delivery_request_hash(request))

    @staticmethod
    def _is_expired(expires_at: str) -> bool:
        try:
            value = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("配送报价有效期无效，请重新报价") from exc
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value <= datetime.now(timezone.utc)
