"""配送报价 Provider 和应用服务测试。"""

import pytest

from app.models.delivery import DeliveryQuoteStatus
from app.service.delivery.application import DeliveryApplicationService
from app.service.delivery.provider import DeliveryQuoteItem, DeliveryQuoteRequest
from app.service.delivery.shansong import ShansongProvider


class MemoryQuoteRepo:
    def __init__(self) -> None:
        self.items = {}

    async def create(self, quote):
        self.items[quote.quote_id] = quote

    async def get_for_user(self, quote_id: str, user_id: str):
        quote = self.items.get(quote_id)
        if quote is None or (quote.user_id and quote.user_id != user_id):
            return None
        return quote


@pytest.mark.asyncio
async def test_unconfigured_shansong_returns_provider_unavailable() -> None:
    request = DeliveryQuoteRequest(
        request_id="quote-1",
        pickup_address="北京门店",
        receiver_name="张三",
        receiver_phone="13800000000",
        receiver_address="北京市朝阳区",
        expect_time="2026-09-09 15:00",
        item_count=1,
        items=(DeliveryQuoteItem(product_id="p_001", quantity=1),),
    )
    quote = await ShansongProvider().quote(request)
    assert quote.status is DeliveryQuoteStatus.PROVIDER_UNAVAILABLE
    assert quote.delivery_fee_fen is None


@pytest.mark.asyncio
async def test_application_rejects_unavailable_quote_for_payment() -> None:
    request = DeliveryQuoteRequest(
        request_id="quote-2",
        pickup_address="北京门店",
        receiver_name="张三",
        receiver_phone="13800000000",
        receiver_address="北京市朝阳区",
        expect_time="2026-09-09 15:00",
        item_count=1,
        items=(DeliveryQuoteItem(product_id="p_001", quantity=1),),
    )
    service = DeliveryApplicationService(ShansongProvider(), MemoryQuoteRepo())
    quote = await service.quote(request)
    with pytest.raises(ValueError, match="不能支付"):
        await service.require_payable_quote(quote.quote_id, "user-1")
