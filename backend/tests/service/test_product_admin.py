"""商品后台履约方式覆盖：生效口径与参数校验。"""

import aiosqlite
import pytest

from app.config import settings
from app.repository.knowledge_product_repo import KnowledgeProductRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.catalog.product_admin import ProductAdminService
from tests.helpers.catalog_seed import seed_catalog_product

TITLE_ONLY_CAKE_ID = 93001
PLAIN_PRODUCT_ID = 93002


async def test_override_turns_title_cake_into_direct(db: aiosqlite.Connection) -> None:
    """没有规格数据的固定尺寸蛋糕，后台可以强制指定现货。"""
    await seed_catalog_product(
        db,
        item_id=TITLE_ONLY_CAKE_ID,
        title="Labubu定制蛋糕（固定6寸）",
        price_fen=25800,
    )
    service = ProductAdminService(YouzanProductRepo(db))

    before = await service.get_product(str(TITLE_ONLY_CAKE_ID))
    assert before is not None
    assert before["effectiveOrderMode"] == "preorder"

    await service.set_fulfillment_mode(str(TITLE_ONLY_CAKE_ID), "direct")
    after = await service.get_product(str(TITLE_ONLY_CAKE_ID))
    assert after is not None
    assert after["fulfillmentMode"] == "direct"
    assert after["effectiveOrderMode"] == "direct"

    await service.set_fulfillment_mode(str(TITLE_ONLY_CAKE_ID), "auto")
    restored = await service.get_product(str(TITLE_ONLY_CAKE_ID))
    assert restored is not None
    assert restored["fulfillmentMode"] == "auto"
    assert restored["effectiveOrderMode"] == "preorder"


async def test_invalid_mode_and_missing_product_rejected(
    db: aiosqlite.Connection,
) -> None:
    await seed_catalog_product(
        db, item_id=PLAIN_PRODUCT_ID, title="招牌牛奶吐司", price_fen=1800
    )
    service = ProductAdminService(YouzanProductRepo(db))

    with pytest.raises(ValueError, match="履约方式"):
        await service.set_fulfillment_mode(str(PLAIN_PRODUCT_ID), "whatever")
    with pytest.raises(ValueError, match="商品不存在"):
        await service.set_fulfillment_mode("999999", "preorder")
    with pytest.raises(ValueError, match="商品 ID"):
        await service.get_product("abc")


async def test_save_product_rebuilds_skus_and_syncs_knowledge(
    db: aiosqlite.Connection,
) -> None:
    """后台改规格表后：价格取最低规格、库存取合计、知识表标题同步。"""
    await seed_catalog_product(
        db, item_id=PLAIN_PRODUCT_ID, title="旧面包", price_fen=1800, stock=3
    )
    service = ProductAdminService(YouzanProductRepo(db), KnowledgeProductRepo(db))

    await service.save_product(
        str(PLAIN_PRODUCT_ID),
        {
            "title": "新面包",
            "variants": [
                {"name": "6寸", "priceFen": 25800, "stock": 2},
                {"name": "8寸", "priceFen": 35800, "stock": 3},
            ],
            "options": [
                {
                    "name": "夹心",
                    "required": True,
                    "choices": [{"name": "芒果", "priceDeltaFen": 0}],
                }
            ],
            "fulfillmentMode": "preorder",
        },
    )

    product = await service.get_product(str(PLAIN_PRODUCT_ID))
    assert product is not None
    assert product["title"] == "新面包"
    assert product["priceFen"] == 25800
    assert product["stock"] == 5
    assert [v["name"] for v in product["variants"]] == ["6寸", "8寸"]
    assert product["effectiveOrderMode"] == "preorder"

    rows = await db.execute_fetchall(
        "SELECT title FROM knowledge_base WHERE youzan_item_id = ?",
        (str(PLAIN_PRODUCT_ID),),
    )
    assert rows[0]["title"] == "新面包"


async def test_create_product_and_upload_image(
    db: aiosqlite.Connection, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """新建商品同时写入商品宽表与知识表，图片落到本地目录。"""
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "bot.db"))
    service = ProductAdminService(YouzanProductRepo(db), KnowledgeProductRepo(db))

    created = await service.create_product(
        {"title": "新品蛋糕", "priceFen": 19800, "stock": 4, "isActive": True}
    )
    item_id = created["itemId"]
    assert created["effectiveOrderMode"] == "direct"  # 只有"蛋糕"两个字不触发预订

    saved = await service.save_image(item_id, b"fake-image", "image/png")
    assert saved["imageLocal"].endswith(".png")
    assert (tmp_path / "product-images" / f"{item_id}.png").is_file()

    rows = await db.execute_fetchall(
        "SELECT image_local FROM youzan_products WHERE item_id = ?", (int(item_id),)
    )
    assert rows[0]["image_local"] == saved["imageLocal"]
