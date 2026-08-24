"""商品目录测试造数工具。"""

import json

import aiosqlite

from app.repository.knowledge_product_repo import KnowledgeProductRepo
from app.repository.youzan_repo import YouzanProductRepo


async def seed_catalog_product(
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
    """写入一条可被商品目录和前台接口读取的商品。"""
    await KnowledgeProductRepo(db).upsert_product_knowledge(
        youzan_item_id=str(item_id),
        title=title,
        content=content,
        keywords=keywords,
        priority=priority,
        updated_at=updated_at,
        sync_source="catalog_test",
        sync_ref=str(item_id),
    )
    await YouzanProductRepo(db).upsert_product(
        item_id=item_id,
        title=title,
        alias=f"alias-{item_id}",
        price_fen=price_fen,
        stock=stock,
        image=image,
        is_active=is_active,
        updated_at=updated_at,
        tag_ids_json=json.dumps(tag_ids or [], ensure_ascii=False),
        classification_ids_json=json.dumps(
            classification_ids or [], ensure_ascii=False
        ),
        sold_num=sold_num,
    )
    if tag_ids and category_title:
        await YouzanProductRepo(db).upsert_category(
            tag_id=tag_ids[0],
            title=category_title,
            sort=10,
            product_count=1,
        )
    if not is_active:
        await KnowledgeProductRepo(db).delete_product_knowledge(str(item_id))
