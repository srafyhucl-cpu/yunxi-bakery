"""小程序 API 契约测试造数兼容入口。"""

import aiosqlite

from tests.helpers.catalog_seed import seed_catalog_product


async def seed_miniapp_product(
    db: aiosqlite.Connection,
    *,
    item_id: int,
    title: str,
    content: str = "手工现制，适合生日和聚会。",
    keywords: str = "生日蛋糕,奶油蛋糕",
    price_fen: int = 19800,
    stock: int = 8,
    sold_num: int = 0,
    image: str = "https://img.example/product.jpg",
    is_active: int = 1,
    priority: int = 10,
    updated_at: str = "2026-06-16 11:00:00",
    tag_ids: list[str] | None = None,
    classification_ids: list[str] | None = None,
    category_title: str = "",
) -> None:
    """写入一条可被小程序和后台商品接口读取的商品。"""
    await seed_catalog_product(
        db,
        item_id=item_id,
        title=title,
        content=content,
        keywords=keywords,
        price_fen=price_fen,
        stock=stock,
        sold_num=sold_num,
        image=image,
        is_active=is_active,
        priority=priority,
        updated_at=updated_at,
        tag_ids=tag_ids,
        classification_ids=classification_ids,
        category_title=category_title,
    )
