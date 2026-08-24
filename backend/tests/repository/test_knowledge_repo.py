"""
KnowledgeRepo 数据访问层单元测试。

覆盖：关键词搜索、分类查询、upsert 时序防线、软下架、
get_by_youzan_item_ids 混合 key 路由。
"""

import aiosqlite
import pytest

from app.repository.knowledge_product_repo import KnowledgeProductRepo
from app.repository.knowledge_repo import KnowledgeRepo

_TS_OLD = "2026-01-01 00:00:00"
_TS_NEW = "2026-06-01 00:00:00"


@pytest.fixture
def repo(db: aiosqlite.Connection) -> KnowledgeRepo:
    return KnowledgeRepo(db)


async def _seed(
    repo: KnowledgeRepo,
    youzan_item_id: str,
    title: str,
    content: str,
    keywords: str = "",
    priority: int = 0,
    updated_at: str = _TS_NEW,
) -> None:
    """辅助：插入一条商品知识条目。"""
    prod_repo = KnowledgeProductRepo(repo._db)
    await prod_repo.upsert_product_knowledge(
        youzan_item_id=youzan_item_id,
        title=title,
        content=content,
        keywords=keywords,
        priority=priority,
        updated_at=updated_at,
    )


async def test_search_finds_by_title(repo: KnowledgeRepo) -> None:
    """search 应通过标题关键词找到对应条目。"""
    await _seed(repo, "yz-001", "草莓鲜奶蛋糕", "使用新鲜草莓，安佳奶油", "草莓 蛋糕")
    results = await repo.search("草莓")
    assert any(r.title == "草莓鲜奶蛋糕" for r in results)


async def test_search_finds_by_content(repo: KnowledgeRepo) -> None:
    """search 应通过正文内容找到条目。"""
    await _seed(repo, "yz-002", "提拉米苏", "含有咖啡、马斯卡彭芝士", "提拉米苏")
    results = await repo.search("马斯卡彭")
    assert any(r.title == "提拉米苏" for r in results)


async def test_search_returns_empty_for_no_match(repo: KnowledgeRepo) -> None:
    """search 找不到匹配时应返回空列表。"""
    results = await repo.search("不存在的关键词xyz")
    assert results == []


async def test_get_by_category_returns_only_product(repo: KnowledgeRepo) -> None:
    """get_by_category('product') 只返回商品类知识。"""
    await _seed(repo, "yz-003", "芒果班戟", "新鲜芒果 + 手工班戟皮")
    results = await repo.get_by_category("product")
    assert all(r.category == "product" for r in results)
    assert len(results) >= 1


async def test_upsert_newer_timestamp_overwrites(repo: KnowledgeRepo) -> None:
    """更新的时间戳应覆盖旧内容（时序防线：写新）。"""
    await _seed(repo, "yz-004", "旧标题", "旧内容", updated_at=_TS_OLD)
    await _seed(repo, "yz-004", "新标题", "新内容", updated_at=_TS_NEW)

    results = await repo.search("新标题")
    assert any(r.title == "新标题" for r in results)

    results_old = await repo.search("旧标题")
    assert not any(r.title == "旧标题" for r in results_old)


async def test_upsert_older_timestamp_does_not_overwrite(repo: KnowledgeRepo) -> None:
    """旧时间戳的 upsert 不应覆盖新数据（时序防线：拒旧）。"""
    await _seed(repo, "yz-005", "当前标题", "当前内容", updated_at=_TS_NEW)
    await _seed(repo, "yz-005", "过时推送", "过时内容", updated_at=_TS_OLD)

    results = await repo.search("当前标题")
    assert any(r.title == "当前标题" for r in results)


async def test_delete_product_knowledge_soft_deactivates(repo: KnowledgeRepo) -> None:
    """delete_product_knowledge 应软下架，search 不再返回该条目。"""
    await _seed(repo, "yz-006", "待下架商品", "下架内容")
    await KnowledgeProductRepo(repo._db).delete_product_knowledge("yz-006")

    results = await repo.search("待下架商品")
    assert not any(r.title == "待下架商品" for r in results)


async def test_get_by_youzan_item_ids_with_yz_key(repo: KnowledgeRepo) -> None:
    """get_by_youzan_item_ids 应能用有赞 ID 路由返回正确条目。"""
    await _seed(repo, "yz-007", "熔岩巧克力", "经典法式熔岩")
    results = await repo.get_by_youzan_item_ids(["yz-007"])
    assert any(r.title == "熔岩巧克力" for r in results)


async def test_get_by_youzan_item_ids_with_kb_key(repo: KnowledgeRepo) -> None:
    """get_by_youzan_item_ids 应能用 kb_ 前缀的自增 ID 路由返回正确条目。"""
    await _seed(repo, "yz-008", "红丝绒蛋糕", "奶油芝士夹心")
    all_entries = await repo.get_all_titles()
    assert len(all_entries) >= 1

    # 取刚插入的 auto-increment id
    count = await repo.count_all()
    assert count >= 1

    all_with_keys = await repo.get_all_titles_with_keys()
    entry_key = next((k for k, t, _ in all_with_keys if t == "红丝绒蛋糕"), None)
    assert entry_key is not None

    results = await repo.get_by_youzan_item_ids([entry_key])
    assert any(r.title == "红丝绒蛋糕" for r in results)


async def test_count_all_increments(repo: KnowledgeRepo) -> None:
    """count_all 应随插入增加。"""
    before = await repo.count_all()
    await _seed(repo, "yz-009", "数量测试蛋糕", "内容")
    after = await repo.count_all()
    assert after == before + 1


async def test_search_hides_draft_archived_and_expired_entries(
    repo: KnowledgeRepo,
) -> None:
    """search 应只返回已发布且当前有效的知识。"""
    visible_id = await repo.insert_entry(
        category="faq",
        title="治理可见知识",
        content="这条知识已发布且有效",
        keywords="治理",
        priority=10,
        sync_source="test",
    )
    draft_id = await repo.insert_entry(
        category="faq",
        title="治理草稿知识",
        content="这条知识不应进入检索",
        keywords="治理",
        priority=10,
        sync_source="test",
        review_status="draft",
    )
    archived_id = await repo.insert_entry(
        category="faq",
        title="治理归档知识",
        content="这条知识不应进入检索",
        keywords="治理",
        priority=10,
        sync_source="test",
        review_status="archived",
    )
    expired_id = await repo.insert_entry(
        category="faq",
        title="治理过期知识",
        content="这条知识不应进入检索",
        keywords="治理",
        priority=10,
        sync_source="test",
        valid_until="2000-01-01 00:00:00",
    )

    results = await repo.search("治理", limit=10)
    result_ids = {entry.id for entry in results}

    assert visible_id in result_ids
    assert draft_id not in result_ids
    assert archived_id not in result_ids
    assert expired_id not in result_ids


async def test_search_filters_by_audience(repo: KnowledgeRepo) -> None:
    """指定 audience 时应同时返回 all 和目标 audience。"""
    shared_id = await repo.insert_entry(
        category="faq",
        title="共同可见知识",
        content="客户和员工都能看到",
        keywords="受众",
        priority=10,
        sync_source="test",
    )
    customer_id = await repo.insert_entry(
        category="faq",
        title="客户可见知识",
        content="只有客户机器人能看到",
        keywords="受众",
        priority=10,
        sync_source="test",
        audience="customer",
    )
    employee_id = await repo.insert_entry(
        category="faq",
        title="员工可见知识",
        content="只有员工助手能看到",
        keywords="受众",
        priority=10,
        sync_source="test",
        audience="employee",
    )

    default_ids = {entry.id for entry in await repo.search("受众", limit=10)}
    customer_ids = {
        entry.id for entry in await repo.search("受众", limit=10, audience="customer")
    }
    employee_ids = {
        entry.id for entry in await repo.search("受众", limit=10, audience="employee")
    }

    assert default_ids == {shared_id}
    assert customer_ids == {shared_id, customer_id}
    assert employee_ids == {shared_id, employee_id}


async def test_get_all_titles_with_keys_applies_governance_filter(
    repo: KnowledgeRepo,
) -> None:
    """向量索引构建入口应排除草稿知识。"""
    await repo.insert_entry(
        category="faq",
        title="向量可见知识",
        content="可以进入向量索引",
        keywords="向量治理",
        priority=10,
        sync_source="test",
    )
    await repo.insert_entry(
        category="faq",
        title="向量草稿知识",
        content="不应进入向量索引",
        keywords="向量治理",
        priority=10,
        sync_source="test",
        review_status="draft",
    )

    titles = {title for _, title, _ in await repo.get_all_titles_with_keys()}

    assert "向量可见知识" in titles
    assert "向量草稿知识" not in titles
