"""商品关键词检索跨知识库与有赞商品两侧字段的契约测试。

背景（r80，`M-20260926-032`）：`KnowledgeProductRepo._build_product_where` 的
`search` 子句跨了 `kb.*` 与 `yp.*` 两张表。该子句由 `get_all_products`（有 join）
与 `count_products`（原无 join）共用，此前存在两处独立缺陷——count 查询缺 join 报
`no such column: yp.title`、4 个占位符只传 3 个参数报 `Incorrect number of bindings`。

本文件锁定的是此前**无任何测试覆盖**的那部分意图：关键词要能命中只存在于有赞侧的
字段（`title` / `tags` / `item_no`），并且列表与计数必须给出同一个总数。
"""

import aiosqlite
import pytest

from app.repository.knowledge_product_repo import KnowledgeProductRepo
from tests.helpers.catalog_seed import seed_catalog_product


@pytest.fixture
async def repo(db: aiosqlite.Connection) -> KnowledgeProductRepo:
    await seed_catalog_product(
        db, item_id=70001, title="法式可颂", keywords="可颂,面包"
    )
    return KnowledgeProductRepo(db)


async def _only_youzan_side_matches(db: aiosqlite.Connection, item_id: int) -> None:
    """把知识库侧改成与关键词无关，只留有赞侧字段可命中。"""
    await db.execute(
        "UPDATE knowledge_base SET title = ?, content = ?, keywords = ? WHERE youzan_item_id = ?",
        ("ZkLQ4K", "无关正文", "无关关键词", str(item_id)),
    )


@pytest.mark.parametrize(
    ("column", "value", "keyword"),
    [
        ("title", "北海道吐司", "吐司"),
        ("tags", "面包,吐司", "吐司"),
        ("item_no", "SKU-70001", "SKU-70001"),
    ],
)
async def test_keyword_matches_youzan_only_fields_in_list_and_count(
    db: aiosqlite.Connection,
    repo: KnowledgeProductRepo,
    column: str,
    value: str,
    keyword: str,
) -> None:
    """只被有赞侧字段命中的商品，列表与计数都必须算进去且两者一致。"""
    await _only_youzan_side_matches(db, 70001)
    await db.execute(
        f"UPDATE youzan_products SET {column} = ? WHERE item_id = ?",
        (value, 70001),
    )

    rows = await repo.get_all_products(search=keyword, limit=10, offset=0)
    total = await repo.count_products(search=keyword)

    assert len(rows) == 1, f"按 yp.{column} 命中应返回 1 条，实际 {len(rows)}"
    assert total == 1, f"按 yp.{column} 命中的计数应为 1，实际 {total}"
    assert total == len(rows), "列表条数与计数不一致会让小程序分页 meta 显示错误总页数"


async def test_count_products_does_not_inflate_on_youzan_join(
    db: aiosqlite.Connection,
    repo: KnowledgeProductRepo,
) -> None:
    """count 查询为检索 join 了 youzan_products，但不得因此放大计数。"""
    await _only_youzan_side_matches(db, 70001)

    assert await repo.count_products() == 1
    assert await repo.count_products(is_active=1) == 1
