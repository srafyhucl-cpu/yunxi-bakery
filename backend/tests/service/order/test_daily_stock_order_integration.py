"""日常现烤每日库存与订单下单/取消集成测试。"""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import aiosqlite
import pytest

from app.repository.config_repo import ConfigRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.product_daily_stock_repo import ProductDailyStockRepo
from app.repository.session_repo import SessionRepo
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.catalog.daily_stock import ProductDailyStockService
from app.service.order.application import OrderApplicationService
from app.service.order.creation import OrderCreationService
from app.service.order.fulfillment_dual_track import OrderFulfillmentDualTrackService
from app.service.order.inventory import OrderInventoryService
from app.service.order.schedule import OrderScheduleService
from app.service.order.timeline import OrderTimelineService
from app.service.shop_operations import ShopOperationsService
from tests.helpers.catalog_seed import seed_catalog_product

STOCK_DATE = "2026-06-18"
EXPECT_TIME = "2026-06-18 15:00"
BEIJING_TZ = ZoneInfo("Asia/Shanghai")
FROZEN_NOW = datetime(2026, 6, 17, 12, 0, tzinfo=BEIJING_TZ)


def _build_daily_service(db: aiosqlite.Connection) -> ProductDailyStockService:
    return ProductDailyStockService(ProductDailyStockRepo(db))


def _build_order_service(
    db: aiosqlite.Connection,
) -> tuple[OrderApplicationService, ProductDailyStockService]:
    daily_service = _build_daily_service(db)
    service = OrderApplicationService(
        order_repo=OrderRepo(db),
        event_repo=OrderEventRepo(db),
        session_repo=SessionRepo(db),
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
        config_repo=ConfigRepo(db),
        daily_stock_service=daily_service,
    )
    return service, daily_service


def _build_creation_service(
    db: aiosqlite.Connection,
    daily_service: ProductDailyStockService,
) -> OrderCreationService:
    order_repo = OrderRepo(db)
    inventory_service = OrderInventoryService(
        YouzanProductRepo(db),
        YouzanInventoryRepo(db),
        daily_stock_service=daily_service,
    )
    return OrderCreationService(
        order_repo=order_repo,
        session_repo=SessionRepo(db),
        inventory_service=inventory_service,
        schedule_service=OrderScheduleService(
            ShopOperationsService(ConfigRepo(db)),
            now_provider=lambda: FROZEN_NOW,
        ),
        timeline_service=OrderTimelineService(order_repo, OrderEventRepo(db)),
        dual_track_service=OrderFulfillmentDualTrackService(
            order_repo=order_repo,
            now_provider=lambda: FROZEN_NOW,
        ),
    )


async def test_daily_ready_order_reserves_daily_stock_not_youzan_stock(
    db: aiosqlite.Connection,
) -> None:
    """日常现烤下单只预占每日库存，不改动有赞商品库存。"""
    await seed_catalog_product(
        db,
        item_id=90001,
        title="现烤法棍",
        price_fen=1500,
        stock=10,
    )
    service, daily_service = _build_order_service(db)
    await daily_service.set_total(STOCK_DATE, "90001", 5, "admin")

    created = await service.create_order(
        {
            "items": [{"productId": "90001", "quantity": 2}],
            "receiverName": "现烤测试",
            "receiverPhone": "18800000021",
            "expectTime": EXPECT_TIME,
        },
        user_id="daily-stock-user",
    )

    product = await YouzanProductRepo(db).get_by_id(90001)
    daily_row = await ProductDailyStockRepo(db).get_for_date("90001", STOCK_DATE)
    order = await OrderRepo(db).get_order(created["orderId"])
    saved_items = json.loads(order.products)

    assert product["stock"] == 10
    assert daily_row["reserved_qty"] == 2
    assert saved_items[0]["fulfillment_type"] == "DAILY_READY"
    assert saved_items[0]["stock_date"] == STOCK_DATE
    assert saved_items[0]["daily_stock_reserved"] is True
    assert saved_items[0]["inventory_reserved"] is False


async def test_cancel_daily_ready_order_releases_daily_stock(
    db: aiosqlite.Connection,
) -> None:
    """取消日常现烤订单时释放每日库存，不触碰有赞库存。"""
    await seed_catalog_product(
        db,
        item_id=90001,
        title="现烤法棍",
        price_fen=1500,
        stock=10,
    )
    service, daily_service = _build_order_service(db)
    await daily_service.set_total(STOCK_DATE, "90001", 5, "admin")
    created = await service.create_order(
        {
            "items": [{"productId": "90001", "quantity": 2}],
            "receiverName": "现烤取消",
            "receiverPhone": "18800000022",
            "expectTime": EXPECT_TIME,
        },
        user_id="daily-cancel-user",
    )

    cancelled = await service.cancel_user_order(
        created["orderId"],
        user_id="daily-cancel-user",
    )

    daily_row = await ProductDailyStockRepo(db).get_for_date("90001", STOCK_DATE)
    product = await YouzanProductRepo(db).get_by_id(90001)
    assert cancelled["status"] == "cancelled"
    assert daily_row["reserved_qty"] == 0
    assert product["stock"] == 10


async def test_preorder_cake_still_reserves_youzan_stock(
    db: aiosqlite.Connection,
) -> None:
    """定制蛋糕继续预占有赞商品库存，不进入每日库存。"""
    await seed_catalog_product(
        db,
        item_id=90002,
        title="生日定制蛋糕",
        price_fen=19800,
        stock=10,
    )
    daily_service = _build_daily_service(db)
    creation_service = _build_creation_service(db, daily_service)

    await creation_service.create_order(
        {
            "items": [
                {
                    "productId": "90002",
                    "quantity": 1,
                    "fulfillmentType": "PREORDER_CAKE",
                    "customization": {
                        "size": "8寸",
                        "filling": "草莓",
                        "greeting": "生日快乐",
                        "accessories": "餐具+蜡烛",
                    },
                }
            ],
            "receiverName": "定制测试",
            "receiverPhone": "18800000023",
            "expectTime": EXPECT_TIME,
        },
        user_id="preorder-cake-user",
    )

    product = await YouzanProductRepo(db).get_by_id(90002)
    daily_row = await ProductDailyStockRepo(db).get_for_date("90002", STOCK_DATE)
    assert product["stock"] == 9
    assert daily_row is None


async def test_daily_ready_ignores_youzan_stock_when_daily_stock_configured(
    db: aiosqlite.Connection,
) -> None:
    """每日库存是权威：有赞库存为 0 时，每日库存充足仍可下单。"""
    await seed_catalog_product(
        db,
        item_id=90003,
        title="现烤吐司",
        price_fen=1800,
        stock=0,
    )
    service, daily_service = _build_order_service(db)
    await daily_service.set_total(STOCK_DATE, "90003", 2, "admin")

    created = await service.create_order(
        {
            "items": [{"productId": "90003", "quantity": 1}],
            "receiverName": "每日权威",
            "receiverPhone": "18800000025",
            "expectTime": EXPECT_TIME,
        },
        user_id="daily-authority-user",
    )

    product = await YouzanProductRepo(db).get_by_id(90003)
    daily_row = await ProductDailyStockRepo(db).get_for_date("90003", STOCK_DATE)
    assert created["orderId"]
    assert product["stock"] == 0
    assert daily_row["reserved_qty"] == 1


async def test_daily_ready_without_daily_record_fails_without_order(
    db: aiosqlite.Connection,
) -> None:
    """每日库存服务存在但商品未录入时，下单必须报错且不回退有赞库存。"""
    await seed_catalog_product(
        db,
        item_id=90004,
        title="现烤贝果",
        price_fen=1200,
        stock=10,
    )
    service, _daily_service = _build_order_service(db)

    with pytest.raises(ValueError, match="未配置每日库存"):
        await service.create_order(
            {
                "items": [{"productId": "90004", "quantity": 1}],
                "receiverName": "漏录守卫",
                "receiverPhone": "18800000026",
                "expectTime": EXPECT_TIME,
            },
            user_id="daily-missing-user",
        )

    product = await YouzanProductRepo(db).get_by_id(90004)
    daily_rows = await db.execute_fetchall(
        "SELECT stock_date FROM product_daily_stock WHERE product_id = ?",
        ("90004",),
    )
    order_rows = await db.execute_fetchall("SELECT id FROM orders")
    assert product["stock"] == 10
    assert daily_rows == []
    assert order_rows == []


async def test_preorder_cake_still_blocked_by_zero_youzan_stock(
    db: aiosqlite.Connection,
) -> None:
    """定制蛋糕不接受每日库存兜底，有赞库存为 0 时必须失败。"""
    await seed_catalog_product(
        db,
        item_id=90005,
        title="生日定制蛋糕",
        price_fen=19800,
        stock=0,
    )
    creation_service = _build_creation_service(db, _build_daily_service(db))

    with pytest.raises(ValueError, match="商品已售罄"):
        await creation_service.create_order(
            {
                "items": [
                    {
                        "productId": "90005",
                        "quantity": 1,
                        "fulfillmentType": "PREORDER_CAKE",
                        "customization": {
                            "size": "8寸",
                            "filling": "草莓",
                            "greeting": "生日快乐",
                            "accessories": "餐具+蜡烛",
                        },
                    }
                ],
                "receiverName": "定制零库存",
                "receiverPhone": "18800000027",
                "expectTime": EXPECT_TIME,
            },
            user_id="preorder-zero-stock-user",
        )


async def test_insufficient_daily_stock_writes_no_order(
    db: aiosqlite.Connection,
) -> None:
    """每日库存不足时下单失败，不写订单也不预占其他库存。"""
    await seed_catalog_product(
        db,
        item_id=90001,
        title="现烤法棍",
        price_fen=1500,
        stock=10,
    )
    service, daily_service = _build_order_service(db)
    await daily_service.set_total(STOCK_DATE, "90001", 1, "admin")

    with pytest.raises(ValueError, match="今日库存不足"):
        await service.create_order(
            {
                "items": [{"productId": "90001", "quantity": 2}],
                "receiverName": "现烤不足",
                "receiverPhone": "18800000024",
                "expectTime": EXPECT_TIME,
            },
            user_id="daily-short-user",
        )

    daily_row = await ProductDailyStockRepo(db).get_for_date("90001", STOCK_DATE)
    product = await YouzanProductRepo(db).get_by_id(90001)
    order_rows = await db.execute_fetchall("SELECT id FROM orders")
    assert daily_row["reserved_qty"] == 0
    assert product["stock"] == 10
    assert order_rows == []
