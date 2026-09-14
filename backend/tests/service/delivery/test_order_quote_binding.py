"""配送报价与订单金额快照绑定测试。"""

from datetime import datetime, timedelta, timezone

import aiosqlite
import pytest

from app.models.delivery import (
    DeliveryOrder,
    DeliveryQuote,
    DeliveryQuoteStatus,
    FulfillmentMethod,
)
from app.repository.config_repo import ConfigRepo
from app.repository.delivery_quote_repo import DeliveryQuoteRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.session_repo import SessionRepo
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.delivery.application import DeliveryApplicationService
from app.service.delivery.provider import DeliveryQuoteItem, DeliveryQuoteRequest
from app.service.order import OrderApplicationService
from tests.helpers.catalog_seed import seed_catalog_product


class QuotedDeliveryProvider:
    """用于验证报价绑定的确定性配送平台替身。"""

    async def quote(self, request: DeliveryQuoteRequest) -> DeliveryQuote:
        delivery_fee_fen = 2600
        return DeliveryQuote(
            quote_id=request.request_id,
            user_id=request.user_id,
            fulfillment_method=FulfillmentMethod.BEIJING_DELIVERY,
            request_hash="",
            goods_total_fen=request.goods_total_fen,
            delivery_fee_fen=delivery_fee_fen,
            quote_total_fen=request.goods_total_fen + delivery_fee_fen,
            status=DeliveryQuoteStatus.QUOTED,
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            provider="quoted-test",
        )

    async def create_order(
        self, request: DeliveryQuoteRequest, quote: DeliveryQuote
    ) -> DeliveryOrder:
        raise AssertionError("本测试不创建外部配送单")

    async def cancel_order(self, provider_order_id: str, reason: str) -> DeliveryOrder:
        raise AssertionError("本测试不取消外部配送单")


@pytest.fixture
def delivery_service(db: aiosqlite.Connection) -> DeliveryApplicationService:
    return DeliveryApplicationService(
        QuotedDeliveryProvider(),
        DeliveryQuoteRepo(db),
    )


@pytest.fixture
def order_service(
    db: aiosqlite.Connection,
    delivery_service: DeliveryApplicationService,
) -> OrderApplicationService:
    return OrderApplicationService(
        order_repo=OrderRepo(db),
        event_repo=OrderEventRepo(db),
        session_repo=SessionRepo(db),
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
        config_repo=ConfigRepo(db),
        delivery_service=delivery_service,
    )


def build_delivery_payload(quote_id: str = "") -> dict:
    return {
        "receiverName": "配送测试",
        "receiverPhone": "18800000001",
        "deliveryType": "delivery",
        "fulfillmentMethod": "beijing_delivery",
        "pickupAddress": "北京市东城区南竹杆胡同2号银河SOHO",
        "deliveryAddress": "北京市朝阳区测试路 1 号",
        "expectTime": "2026-09-10 15:00",
        "deliveryQuoteId": quote_id,
    }


def build_order_payload(quote_id: str = "", product_id: str = "91001") -> dict:
    return {
        "items": [
            {
                "productId": product_id,
                "title": "报价绑定蛋糕",
                "priceFen": 1,
                "quantity": 1,
            }
        ],
        **build_delivery_payload(quote_id),
        "deliveryFeeFen": 1,
    }


async def create_quote(
    delivery_service: DeliveryApplicationService,
    *,
    user_id: str,
    product_id: str = "91001",
) -> DeliveryQuote:
    payload = build_delivery_payload()
    return await delivery_service.quote(
        DeliveryQuoteRequest(
            request_id=f"quote-{user_id}-{product_id}",
            user_id=user_id,
            pickup_address=payload["pickupAddress"],
            receiver_name=payload["receiverName"],
            receiver_phone=payload["receiverPhone"],
            receiver_address=payload["deliveryAddress"],
            expect_time=payload["expectTime"],
            item_count=1,
            goods_total_fen=19800,
            items=(DeliveryQuoteItem(product_id=product_id, quantity=1),),
        )
    )


async def test_pickup_order_ignores_client_delivery_fee(
    order_service: OrderApplicationService,
) -> None:
    payload = {
        "items": [{"productId": "p_pickup", "quantity": 1, "priceFen": 19800}],
        "expectTime": "2026-09-10 15:00",
        "deliveryType": "pickup",
        "deliveryFeeFen": 99999,
    }

    created = await order_service.create_order(payload, user_id="pickup-user")

    assert created["goodsTotalFen"] == 19800
    assert created["deliveryFeeFen"] == 0
    assert created["totalFen"] == 19800


async def test_pickup_order_returns_pickup_address_snapshot(
    order_service: OrderApplicationService,
) -> None:
    pickup_address = "北京市东城区南竹杆胡同2号银河SOHO"
    payload = {
        "items": [{"productId": "p_pickup_address", "quantity": 1, "priceFen": 19800}],
        "expectTime": "2026-09-10 15:00",
        "deliveryType": "pickup",
        "fulfillmentMethod": "pickup",
        "pickupAddress": pickup_address,
    }

    created = await order_service.create_order(payload, user_id="pickup-address-user")
    detail = await order_service.get_user_order(
        created["orderId"], user_id="pickup-address-user"
    )

    assert detail["fulfillmentMethod"] == "pickup"
    assert detail["deliveryFeeFen"] == 0
    assert detail["pickupAddress"] == pickup_address


async def test_delivery_order_requires_quote_before_inventory_reservation(
    db: aiosqlite.Connection,
    order_service: OrderApplicationService,
) -> None:
    await seed_catalog_product(
        db, item_id=91001, title="报价前库存蛋糕", price_fen=19800, stock=1
    )

    with pytest.raises(ValueError, match="必须先取得有效配送报价"):
        await order_service.create_order(build_order_payload(), user_id="delivery-user")

    product = await YouzanProductRepo(db).get_by_id(91001)
    assert product is not None
    assert product["stock"] == 1


async def test_delivery_order_uses_quote_fee_and_binds_normalized_items(
    db: aiosqlite.Connection,
    delivery_service: DeliveryApplicationService,
    order_service: OrderApplicationService,
) -> None:
    user_id = "bound-delivery-user"
    await seed_catalog_product(
        db, item_id=91001, title="报价绑定蛋糕", price_fen=19800, stock=2
    )
    quote = await create_quote(delivery_service, user_id=user_id)

    created = await order_service.create_order(
        build_order_payload(quote.quote_id), user_id=user_id
    )
    detail = await order_service.get_user_order(created["orderId"], user_id=user_id)

    assert created["goodsTotalFen"] == 19800
    assert created["deliveryFeeFen"] == 2600
    assert created["totalFen"] == 22400
    assert detail["totalFen"] == 22400
    assert detail["goodsTotalFen"] == 19800
    assert detail["deliveryFeeFen"] == 2600
    assert detail["payableFen"] == 22400
    assert detail["deliveryQuoteId"] == quote.quote_id
    assert detail["pickupAddress"] == "北京市东城区南竹杆胡同2号银河SOHO"


async def test_delivery_order_rejects_quote_for_other_user(
    delivery_service: DeliveryApplicationService,
    order_service: OrderApplicationService,
) -> None:
    quote = await create_quote(delivery_service, user_id="quote-owner")

    with pytest.raises(ValueError, match="配送报价不存在"):
        await order_service.create_order(
            build_order_payload(quote.quote_id), user_id="other-user"
        )


async def test_delivery_order_rejects_same_total_different_product_quote(
    db: aiosqlite.Connection,
    delivery_service: DeliveryApplicationService,
    order_service: OrderApplicationService,
) -> None:
    user_id = "different-product-user"
    await seed_catalog_product(
        db, item_id=91001, title="报价商品 A", price_fen=19800, stock=1
    )
    await seed_catalog_product(
        db, item_id=91002, title="报价商品 B", price_fen=19800, stock=1
    )
    quote = await create_quote(delivery_service, user_id=user_id, product_id="91001")

    with pytest.raises(ValueError, match="配送报价与当前收货信息不一致"):
        await order_service.create_order(
            build_order_payload(quote.quote_id, product_id="91002"),
            user_id=user_id,
        )

    product = await YouzanProductRepo(db).get_by_id(91002)
    assert product is not None
    assert product["stock"] == 1
