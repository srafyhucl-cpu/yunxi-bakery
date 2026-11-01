"""订单规格与定制选项：服务端定价、必选项校验与订单行标题。"""

import json

import aiosqlite
import pytest

from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.order.inventory import OrderInventoryService
from tests.helpers.catalog_seed import seed_catalog_product

PRODUCT_ID = 92001


def _sku(sku_id: int, size: str, price_fen: int, quantity: int = 3) -> dict:
    return {
        "sku_id": sku_id,
        "price": price_fen,
        "quantity": quantity,
        "properties_name_json": json.dumps(
            [{"k": "尺寸", "v": size}], ensure_ascii=False
        ),
    }


def _filling_prop() -> list[dict]:
    return [
        {
            "prop_name": "夹心",
            "is_necessary": True,
            "is_multiple": False,
            "text_models": [
                {"prop_text_id": 1, "prop_text_name": "芒果", "price": 0},
                {"prop_text_id": 2, "prop_text_name": "奥利奥", "price": 2000},
            ],
        }
    ]


async def _seed_cake(db: aiosqlite.Connection) -> None:
    """写入一个带尺寸 SKU 与夹心属性的预订蛋糕。"""
    await seed_catalog_product(
        db,
        item_id=PRODUCT_ID,
        title="足球之星",
        price_fen=25800,
        stock=5,
    )
    await db.execute(
        "UPDATE youzan_products SET skus_json = ?, item_props_json = ? WHERE item_id = ?",
        (
            json.dumps(
                [_sku(1, "6寸", 25800), _sku(2, "8寸", 35800)],
                ensure_ascii=False,
            ),
            json.dumps(_filling_prop(), ensure_ascii=False),
            PRODUCT_ID,
        ),
    )
    await db.commit()


def _service(db: aiosqlite.Connection) -> OrderInventoryService:
    return OrderInventoryService(
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
    )


async def test_sku_price_and_option_surcharge(db: aiosqlite.Connection) -> None:
    await _seed_cake(db)
    items = await _service(db).normalize_items(
        [
            {
                "productId": PRODUCT_ID,
                "quantity": 1,
                "skuId": "2",
                "optionChoiceIds": ["2"],
            }
        ]
    )

    assert len(items) == 1
    item = items[0]
    assert item.price_fen == 35800 + 2000
    assert item.fulfillment_type == "PREORDER_CAKE"
    assert item.customization["size"] == "8寸"
    assert item.customization["filling"] == "奥利奥"
    assert "8寸" in item.title


async def test_required_option_missing_rejected(db: aiosqlite.Connection) -> None:
    await _seed_cake(db)
    with pytest.raises(ValueError, match="请选择夹心"):
        await _service(db).normalize_items(
            [{"productId": PRODUCT_ID, "quantity": 1, "skuId": "1"}]
        )


async def test_sold_out_variant_rejected(db: aiosqlite.Connection) -> None:
    await seed_catalog_product(
        db, item_id=PRODUCT_ID, title="足球之星", price_fen=25800, stock=5
    )
    await db.execute(
        "UPDATE youzan_products SET skus_json = ?, item_props_json = ? WHERE item_id = ?",
        (
            json.dumps([_sku(1, "6寸", 25800, quantity=0)], ensure_ascii=False),
            "[]",
            PRODUCT_ID,
        ),
    )
    await db.commit()
    with pytest.raises(ValueError, match="该规格已售罄"):
        await _service(db).normalize_items(
            [{"productId": PRODUCT_ID, "quantity": 1, "skuId": "1"}]
        )
