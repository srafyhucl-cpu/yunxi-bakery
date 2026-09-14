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
    assert product["imageUrl"] == "https://img.example/strawberry.jpg"
    assert product["stock"] == 6
    assert product["isPurchasable"] is True
    assert product["soldText"] == "已售 12"
    assert product["categoryId"] == "youzan-tag-281476346"
    assert product["categoryName"] == "生日蛋糕"
    assert product["tags"] == ["生日蛋糕", "草莓"]
    assert "当季草莓" in product["subtitle"]
    assert product["notices"]


async def test_display_only_products_are_serialized_as_non_purchasable(
    db: aiosqlite.Connection,
    service: CatalogApplicationService,
) -> None:
    """原料与展示条目标记仅供展示，不允许前台直接下单。"""
    await seed_catalog_product(
        db,
        item_id=61003,
        title="新西兰安佳动物奶油（非卖品仅展示）",
        price_fen=9999900,
        stock=99999,
        updated_at="2026-06-16 10:00:00",
    )

    product = await service.get_product("61003")

    assert product is not None
    assert product["isPurchasable"] is False


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
        "https://img.example/forest.jpg",
        "https://img.example/mango.jpg",
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
    assert by_youzan_id["imageUrl"] == "https://img.example/chocolate.jpg"
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


async def test_list_products_popular_sort_uses_real_sales_instead_of_updated_at(
    db: aiosqlite.Connection,
    service: CatalogApplicationService,
) -> None:
    """sort=popular 应按真实销量排序，不能退化为更新时间或标签推测。"""
    await seed_catalog_product(
        db,
        item_id=67001,
        title="最新上架但销量最低",
        sold_num=3,
        updated_at="2026-06-20 10:00:00",
    )
    await seed_catalog_product(
        db,
        item_id=67002,
        title="销量最高但更新时间最早",
        sold_num=900,
        updated_at="2026-06-10 10:00:00",
    )
    await seed_catalog_product(
        db,
        item_id=67003,
        title="销量居中",
        sold_num=120,
        updated_at="2026-06-15 10:00:00",
    )

    default_products = await service.list_products()
    popular_products = await service.list_products(sort="popular")

    assert [product["id"] for product in default_products] == [
        "67001",
        "67003",
        "67002",
    ]
    assert [product["id"] for product in popular_products] == [
        "67002",
        "67003",
        "67001",
    ]


async def test_list_products_popular_sort_applies_to_youzan_category(
    db: aiosqlite.Connection,
    service: CatalogApplicationService,
) -> None:
    """分类懒加载传 sort=popular 时，有赞分类路径同样按真实销量排序。"""
    await seed_catalog_product(
        db,
        item_id=67101,
        title="分类内低销量",
        sold_num=5,
        updated_at="2026-06-20 10:00:00",
        tag_ids=["281476346"],
        category_title="生日蛋糕",
    )
    await seed_catalog_product(
        db,
        item_id=67102,
        title="分类内高销量",
        sold_num=800,
        updated_at="2026-06-10 10:00:00",
        tag_ids=["281476346"],
        category_title="生日蛋糕",
    )

    products = await service.list_products(
        category_id="youzan-tag-281476346", sort="popular"
    )

    assert [product["id"] for product in products] == ["67102", "67101"]


async def test_public_categories_only_list_categories_with_real_products(
    db: aiosqlite.Connection,
    service: CatalogApplicationService,
) -> None:
    """分类列表必须现场统计在售商品，空分类不得进入侧栏也不得导出错误命名空间。"""
    await seed_catalog_product(
        db,
        item_id=68001,
        title="分类命中蛋糕",
        tag_ids=["70001"],
        category_title="生日蛋糕",
        updated_at="2026-06-16 10:00:00",
    )
    await YouzanProductRepo(db).upsert_category(
        tag_id="70002",
        title="空分类",
        sort=20,
        product_count=99,
    )

    categories = await service.list_categories()
    products = await service.list_products(category_id="youzan-tag-70001")

    assert [category["id"] for category in categories] == ["youzan-tag-70001"]
    assert categories[0]["productCount"] == 1
    assert [product["id"] for product in products] == ["68001"]


async def test_product_customer_fields_hide_youzan_import_noise(
    db: aiosqlite.Connection,
    service: CatalogApplicationService,
) -> None:
    """商品描述与规格只输出顾客可读内容，不泄露同步字段、库存明细和导出链接。"""
    noisy_content = "\n".join(
        [
            "商品名称：数字蜡烛",
            "在售状态：在售",
            "商品规格及秒级实时库存明细：",
            "- 规格型号【数字:1】：售价 ￥5.00 元，当前可用库存 730 件",
            "可定制口味、蛋糕胚、夹心及甜度选项（SPU 自定义属性）：",
            "- 定制加料选项：暂无特殊定制属性",
            "商品特征与配方属性标签：在售, 8, 3",
            "直购下单链接：https://h5.youzan.com/v2/showcase/goods?alias=abc",
            "原料配方、保质期及夹心介绍：",
            "生日蛋糕都有配套赠送普通蜡烛（10根）如需数字蜡烛单拍此项",
            "[UMP: type=card&id=3610295088&src=https%3A//img.yzcdn.cn/a.jpg]",
        ]
    )
    await seed_catalog_product(
        db,
        item_id=68011,
        title="数字蜡烛",
        content=noisy_content,
        keywords="商品,价格,推荐,蛋糕,数字蜡烛,在售,8,3,9,6,4,0,5,1,2,7",
        updated_at="2026-06-16 10:00:00",
    )
    await seed_catalog_product(
        db,
        item_id=68012,
        title="水果盛宴",
        content="当季水果与动物奶油搭配。",
        keywords="商品,推荐,蛋糕,水果盛宴,在售,6寸,8寸,木糖醇",
        updated_at="2026-06-16 10:00:00",
    )

    noisy_product = await service.get_product("68011")
    clean_product = await service.get_product("68012")

    assert noisy_product is not None and clean_product is not None
    assert "商品名称" not in noisy_product["description"]
    assert "当前可用库存" not in noisy_product["description"]
    assert "h5.youzan.com" not in noisy_product["description"]
    assert "[UMP" not in noisy_product["description"]
    assert "生日蛋糕都有配套赠送普通蜡烛" in noisy_product["description"]
    assert noisy_product["subtitle"].startswith("生日蛋糕都有配套赠送普通蜡烛")
    assert noisy_product["specs"] == []
    assert clean_product["specs"] == ["6寸", "8寸", "木糖醇"]


async def test_category_namespace_prefers_classification_when_both_match(
    db: aiosqlite.Connection,
    service: CatalogApplicationService,
) -> None:
    """分类键同时命中 tag 与 classification 时，公开 ID 与计数必须指向同一批商品。"""
    await seed_catalog_product(
        db,
        item_id=69001,
        title="标签命中蛋糕",
        tag_ids=["70003"],
        updated_at="2026-06-16 10:00:00",
    )
    await seed_catalog_product(
        db,
        item_id=69002,
        title="分类命中蛋糕",
        classification_ids=["70003"],
        updated_at="2026-06-16 11:00:00",
    )
    await YouzanProductRepo(db).upsert_category(
        tag_id="70003",
        title="共用键分类",
        sort=10,
        product_count=99,
    )

    categories = await service.list_categories()
    matched = [item for item in categories if item["title"] == "共用键分类"]
    assert matched == [
        {
            "id": "youzan-classification-70003",
            "title": "共用键分类",
            "sort": 10,
            "productCount": 1,
        }
    ]
    products = await service.list_products(category_id=matched[0]["id"])
    assert [product["id"] for product in products] == ["69002"]


async def test_list_products_page_supports_keyword_search_and_offset(
    db: aiosqlite.Connection,
    service: CatalogApplicationService,
) -> None:
    """服务端搜索必须覆盖全目录，并用 offset/limit 返回稳定分页。"""
    await seed_catalog_product(
        db,
        item_id=70001,
        title="海盐曲奇",
        keywords="伴手礼,曲奇,饼干",
        sold_num=90,
    )
    await seed_catalog_product(
        db,
        item_id=70002,
        title="黄油曲奇",
        keywords="曲奇,黄油",
        sold_num=60,
    )
    await seed_catalog_product(
        db,
        item_id=70003,
        title="巧克力蛋糕",
        keywords="蛋糕,巧克力",
        sold_num=120,
    )

    first_page = await service.list_products_page(
        keyword="曲奇", limit=1, offset=0, sort="popular"
    )
    second_page = await service.list_products_page(
        keyword="曲奇", limit=1, offset=1, sort="popular"
    )

    assert first_page.total == 2
    assert first_page.has_more is True
    assert [product["id"] for product in first_page.items] == ["70001"]
    assert second_page.has_more is False
    assert [product["id"] for product in second_page.items] == ["70002"]
