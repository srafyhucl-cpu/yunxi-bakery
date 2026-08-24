"""商品向量同步静态合同测试。"""

from scripts.check_product_vector_sync_contract import check, check_source


def test_product_vector_sync_contract_passes_for_current_sources() -> None:
    assert check() == []


def test_product_vector_sync_contract_rejects_early_success() -> None:
    failures = check_source(
        """
class Repo:
    async def upsert_product_knowledge(self):
        return "success"
    async def claim_product_vector_sync(self):
        pass
    async def mark_product_vector_sync_success(self):
        pass
    async def mark_product_vector_sync_failed(self):
        pass
    async def list_product_vector_sync_candidates(self):
        return []
""",
        "fixture/knowledge_product_repo.py",
    )

    assert any("不得提前写入 success" in failure for failure in failures)


def test_product_vector_sync_contract_rejects_wrong_sync_order() -> None:
    failures = check_source(
        """
async def sync_product_to_rag(repo, searcher):
    await repo.upsert_product_knowledge()
    await repo.mark_product_vector_sync_success()
    await repo.claim_product_vector_sync()
    await searcher.upsert_one()
    await repo.mark_product_vector_sync_failed()
""",
        "fixture/product_sync.py",
    )

    assert any("顺序必须为" in failure for failure in failures)


def test_product_vector_sync_contract_requires_event_failure_raise() -> None:
    failures = check_source(
        """
async def handle_item_event():
    if knowledge_result == WriteResult.FAILED:
        logger.error("failed")
""",
        "fixture/event_item.py",
    )

    assert any("未阻止 Webhook" in failure for failure in failures)
