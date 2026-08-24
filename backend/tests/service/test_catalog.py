"""小程序商品目录服务测试。"""

import aiosqlite
import pytest

from app.models.config import FEATURED_PRODUCTS_KEY
from app.repository.config_repo import ConfigRepo
from app.repository.knowledge_product_repo import KnowledgeProductRepo
from app.repository.knowledge_repo import KnowledgeRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.catalog import CatalogApplicationService
from tests.helpers.catalog_seed import seed_catalog_product


@pytest.fixture
def service(db: aiosqlite.Connection) -> CatalogApplicationService:
    """使用真实内存库仓储构建商品目录服务。"""
    return CatalogApplicationService(
        product_repo=KnowledgeProductRepo(db),
        knowledge_repo=KnowledgeRepo(db),
        config_repo=ConfigRepo(db),
        youzan_product_repo=YouzanProductRepo(db),
    )


async def test_list_products_returns_sellable_miniapp_shape(
    db: aiosqlite.Connection,
    service: CatalogApplicationService,
) -> None:
    """商品列表应只返回启用商品，并带上小程序需要的价格、库存、标签和描述。"""
    await seed_catalog_product(
        db,
        item_id=61001,
        title="草莓奶油蛋糕",
        content="当季草莓搭配动物奶油，适合生日和家庭聚会。",
        keywords="生日蛋糕,草莓",
        price_fen=26800,
        stock=6,
        sold_num=12,
        image="https://img.example/strawberry.jpg",
        updated_at="2026-06-16 10:00:00",
        tag_ids=["281476346"],
        category_title="生日蛋糕",
    )
    await seed_catalog_product(
        db,
        item_id=61002,
        title="已下架蛋糕",
        keywords="下架测试",
        is_active=0,
        updated_at="2026-06-16 10:00:00",
    )

    products = await service.list_products()

    assert [product["id"] for product in products] == ["61001"]
    product = products[0]
    assert product["title"] == "草莓奶油蛋糕"
    assert product["priceFen"] == 26800
    assert product["imageUrl"] == "/api/v1/miniapp/products/61001/image"
    assert product["stock"] == 6
    assert product["soldText"] == "已售 12"
    assert product["categoryId"] == "youzan-tag-281476346"
    assert product["categoryName"] == "生日蛋糕"
    assert product["tags"] == ["生日蛋糕", "草莓"]
    assert "当季草莓" in product["subtitle"]
    assert product["notices"]


async def test_list_products_by_ids_preserves_requested_order_and_dedupes(
    db: aiosqlite.Connection,
    service: CatalogApplicationService,
) -> None:
    """装修货架按商品 ID 拉取时，应按配置顺序返回并跳过重复或无效 ID。"""
    await seed_catalog_product(
        db,
        item_id=62001,
        title="芒果千层",
        image="https://img.example/mango.jpg",
        updated_at="2026-06-16 10:00:00",
    )
    await seed_catalog_product(
        db,
        item_id=62002,
        title="黑森林蛋糕",
        image="https://img.example/forest.jpg",
        updated_at="2026-06-16 10:00:00",
    )

    products = await service.list_products(ids="62002, missing, 62001, 62002")

    assert [product["id"] for product in products] == ["62002", "62001"]
    assert [product["title"] for product in products] == ["黑森林蛋糕", "芒果千层"]
    assert [product["imageUrl"] for product in products] == [
        "/api/v1/miniapp/products/62002/image",
        "/api/v1/miniapp/products/62001/image",
    ]


async def test_featured_products_use_admin_configured_titles(
    db: aiosqlite.Connection,
    service: CatalogApplicationService,
) -> None:
    """小程序主推商品应使用后台配置的主推标题过滤。"""
    await seed_catalog_product(
        db,
        item_id=63001,
        title="今日主推蛋糕",
        updated_at="2026-06-16 10:00:00",
    )
    await seed_catalog_product(
        db,
        item_id=63002,
        title="普通在售蛋糕",
        updated_at="2026-06-16 10:00:00",
    )
    await ConfigRepo(db).set_list(FEATURED_PRODUCTS_KEY, ["今日主推蛋糕"])

    featured_products = await service.list_products(featured=True)

    assert [product["title"] for product in featured_products] == ["今日主推蛋糕"]


async def test_get_product_supports_youzan_item_id_and_local_knowledge_id(
    db: aiosqlite.Connection,
    service: CatalogApplicationService,
) -> None:
    """商品详情应支持有赞 item_id，以及小程序兜底使用的本地知识 ID。"""
    await seed_catalog_product(
        db,
        item_id=64001,
        title="巧克力慕斯",
        image="https://img.example/chocolate.jpg",
        updated_at="2026-06-16 10:00:00",
    )
    entry = await KnowledgeRepo(db).get_by_youzan_item_ids(["64001"])
    assert entry

    by_youzan_id = await service.get_product("64001")
    by_knowledge_id = await service.get_product(str(entry[0].id))
    missing = await service.get_product("not-a-product")

    assert by_youzan_id is not None
    assert by_youzan_id["title"] == "巧克力慕斯"
    assert by_youzan_id["imageUrl"] == "/api/v1/miniapp/products/64001/image"
    assert by_knowledge_id is not None
    assert by_knowledge_id["id"] == "64001"
    assert missing is None


async def test_product_without_image_keeps_empty_image_url(
    db: aiosqlite.Connection,
    service: CatalogApplicationService,
) -> None:
    """没有原始商品图时，小程序仍拿到空图片地址并走页面兜底。"""
    await seed_catalog_product(
        db,
        item_id=65001,
        title="无图商品",
        image="",
        updated_at="2026-06-16 10:00:00",
    )

    product = await service.get_product("65001")

    assert product is not None
    assert product["imageUrl"] == ""


async def test_generic_youzan_tags_do_not_leak_as_category(
    db: aiosqlite.Connection,
    service: CatalogApplicationService,
) -> None:
    """有赞同步噪声标签不应作为小程序商品分类返回。"""
    await seed_catalog_product(
        db,
        item_id=65002,
        title="泛化标签商品",
        keywords="商品,价格,在售",
        updated_at="2026-06-16 10:00:00",
    )

    product = await service.get_product("65002")

    assert product is not None
    assert product["categoryId"] == "youzan-products"
    assert product["categoryName"] == "有赞同步商品"


async def test_list_categories_and_filter_by_youzan_tag(
    db: aiosqlite.Connection,
    service: CatalogApplicationService,
) -> None:
    """商品分类应来自有赞 tag 映射，并支持精确过滤。"""
    await seed_catalog_product(
        db,
        item_id=66001,
        title="分类生日蛋糕",
        tag_ids=["281476346"],
        category_title="生日蛋糕",
        updated_at="2026-06-16 10:00:00",
    )
    await seed_catalog_product(
        db,
        item_id=66002,
        title="分类下午茶",
        tag_ids=["281476346", "254005045"],
        category_title="下午茶甜品",
        updated_at="2026-06-16 10:00:00",
    )
    await YouzanProductRepo(db).upsert_category(
        tag_id="254005045",
        title="下午茶甜品",
        sort=5,
        product_count=1,
    )

    categories = await service.list_categories()
    products = await service.list_products(category_id="youzan-tag-254005045")

    assert [category["id"] for category in categories] == [
        "youzan-tag-254005045",
        "youzan-tag-281476346",
    ]
    assert [product["id"] for product in products] == ["66002"]
    assert products[0]["categoryName"] == "下午茶甜品"
