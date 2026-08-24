from __future__ import annotations

from typing import Any

from app.models.content_change_history import ContentChangeHistoryCreate
from app.service.youzan.product_reconciler import (
    ProductReconcileService,
    _ITEM_BASE_BATCH_SIZE,
)


class FakeYouzanClient:
    def __init__(
        self,
        onsale_ids: set[int],
        product_payloads: dict[int, dict[str, Any]] | None = None,
    ) -> None:
        self._onsale_ids = onsale_ids
        self._product_payloads = product_payloads or {}
        self.requested_product_ids: list[int] = []

    async def list_onsale_items(self) -> list[dict[str, Any]]:
        return [
            {
                "item_id": item_id,
                "tag_ids": [f"tag-{item_id}"],
            }
            for item_id in sorted(self._onsale_ids)
        ]

    async def list_product_tags(self) -> list[dict[str, Any]]:
        return [
            {
                "id": f"tag-{item_id}",
                "name": f"分组 {item_id}",
            }
            for item_id in sorted(self._onsale_ids)
        ]

    async def search_item_classifications(self) -> list[dict[str, Any]]:
        return []

    async def get_product(self, item_id: int) -> dict[str, Any]:
        self.requested_product_ids.append(item_id)
        if item_id not in self._product_payloads:
            raise RuntimeError("product missing")
        return self._product_payloads[item_id]


class FakeProductRepo:
    def __init__(self, active_ids: list[int], all_ids: list[int]) -> None:
        self._active_ids = active_ids
        self._all_ids = all_ids
        self.deleted: list[tuple[int, str, str, str]] = []
        self.sold_updates: dict[int, tuple[int, str]] = {}
        self.category_updates: dict[int, list[str]] = {}
        self.item_base_category_updates: dict[int, dict[str, list[str]]] = {}
        self.categories: list[tuple[str, str, int, int, int]] = []

    async def list_active_item_ids(self) -> list[int]:
        return self._active_ids

    async def list_all_item_ids(self) -> list[int]:
        return self._all_ids

    async def delete_product(
        self,
        item_id: int,
        event_time: str,
        *,
        sync_source: str,
        sync_ref: str,
    ) -> str:
        self.deleted.append((item_id, event_time, sync_source, sync_ref))
        return "deactivated"

    async def bulk_update_sold_and_no(
        self,
        sold_num_map: dict[int, tuple[int, str]],
    ) -> int:
        self.sold_updates = sold_num_map
        return len(sold_num_map)

    async def upsert_category(
        self,
        *,
        tag_id: str,
        title: str,
        sort: int = 0,
        product_count: int = 0,
        is_public: int = 1,
    ) -> None:
        self.categories.append((tag_id, title, sort, product_count, is_public))

    async def bulk_update_tag_ids(self, tag_ids_map: dict[int, list[str]]) -> int:
        self.category_updates = tag_ids_map
        return len(tag_ids_map)

    async def bulk_update_item_base_categories(
        self,
        category_map: dict[int, dict[str, list[str]]],
    ) -> int:
        self.item_base_category_updates = category_map
        return len(category_map)


class FakeHistoryRepo:
    def __init__(self) -> None:
        self.records: list[ContentChangeHistoryCreate] = []

    async def add(self, record: ContentChangeHistoryCreate) -> None:
        self.records.append(record)


class FakeKnowledgeProductRepo:
    def __init__(self) -> None:
        self.deleted_item_ids: list[str] = []

    async def delete_product_knowledge(
        self,
        item_id: str,
        *,
        sync_source: str,
        sync_ref: str,
    ) -> str:
        self.deleted_item_ids.append(item_id)
        return f"{sync_source}:{sync_ref}"


class FakeVectorKnowledgeRepo:
    def __init__(self, candidates: list[dict[str, Any]]) -> None:
        self.candidates = candidates
        self.claimed: list[tuple[str, str]] = []
        self.successful: list[tuple[str, str]] = []
        self.failed: list[tuple[str, str, str]] = []
        self.allow_success = True

    async def list_product_vector_sync_candidates(
        self,
        *,
        stale_before: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        assert stale_before
        return self.candidates[:limit]

    async def claim_product_vector_sync(
        self,
        item_id: str,
        revision: str,
        *,
        stale_before: str | None = None,
    ) -> bool:
        self.claimed.append((item_id, revision))
        return True

    async def mark_product_vector_sync_success(
        self,
        item_id: str,
        revision: str,
    ) -> bool:
        self.successful.append((item_id, revision))
        return self.allow_success

    async def mark_product_vector_sync_failed(
        self,
        item_id: str,
        revision: str,
        error: str,
    ) -> bool:
        self.failed.append((item_id, revision, error))
        return True


class FakeVectorSearcher:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.upserted: list[str] = []
        self.deleted: list[str] = []

    def _get_model(self) -> Any:
        return self

    def encode(self, texts: list[str], normalize_embeddings: bool = True) -> list[Any]:
        assert texts
        assert normalize_embeddings is True
        return [[0.1, 0.2, 0.3]]

    async def upsert_one(self, item_id: str, vector: list[float]) -> None:
        self.upserted.append(item_id)
        if self.fail:
            raise RuntimeError("retry vector failure")
        assert vector

    async def delete_one(self, item_id: str) -> None:
        self.deleted.append(item_id)


def _vector_candidate(
    item_id: str,
    *,
    status: str = "pending",
    retry_count: int = 0,
    is_active: int = 1,
) -> dict[str, Any]:
    return {
        "youzan_item_id": item_id,
        "title": f"商品 {item_id}",
        "content": "商品正文",
        "is_active": is_active,
        "updated_at": "2026-08-07 10:00:00",
        "vector_sync_status": status,
        "vector_sync_retry_count": retry_count,
        "vector_synced_at": "",
    }


async def test_product_reconcile_deactivates_missing_items_and_syncs_sold_num() -> None:
    product_payloads = {
        101: {"response": {"item": {"sold_num": 7, "item_no": "SKU-101"}}},
        202: {"data": {"item": {"sold_num": 0, "item_no": "SKU-202"}}},
        303: {"data": {"item": {"sold_num": 2, "item_no": "SKU-303"}}},
    }
    youzan_client = FakeYouzanClient({101, 303}, product_payloads)
    product_repo = FakeProductRepo(active_ids=[101, 202, 303], all_ids=[101, 202, 303])
    history_repo = FakeHistoryRepo()
    knowledge_repo = FakeKnowledgeProductRepo()
    service = ProductReconcileService(
        youzan_client=youzan_client,  # type: ignore[arg-type]
        product_repo=product_repo,  # type: ignore[arg-type]
        history_repo=history_repo,  # type: ignore[arg-type]
        knowledge_product_repo=knowledge_repo,  # type: ignore[arg-type]
    )

    summary = await service.run()

    assert summary["checked"] == 3
    assert summary["onsale_from_youzan"] == 2
    assert summary["deactivated"] == 1
    assert summary["deactivated_ids"] == [202]
    assert summary["sold_num_synced"] == 2
    assert summary["category_synced"] == 2
    assert summary["errors"] == []
    assert product_repo.deleted[0][0] == 202
    assert product_repo.deleted[0][2:] == ("product_reconcile", "daily_reconcile")
    assert knowledge_repo.deleted_item_ids == ["202"]
    assert product_repo.sold_updates == {101: (7, "SKU-101"), 303: (2, "SKU-303")}
    assert product_repo.category_updates == {101: ["tag-101"], 303: ["tag-303"]}
    assert product_repo.categories[0][-1] == 1
    assert len(history_repo.records) == 1
    assert history_repo.records[0].action == "deactivate"
    assert history_repo.records[0].status == "success"


async def test_product_reconcile_keeps_running_when_deactivate_fails() -> None:
    class FailingProductRepo(FakeProductRepo):
        async def delete_product(
            self,
            item_id: int,
            event_time: str,
            *,
            sync_source: str,
            sync_ref: str,
        ) -> str:
            raise RuntimeError("database locked")

    youzan_client = FakeYouzanClient({101}, {101: {"data": {"item": {"sold_num": 1}}}})
    product_repo = FailingProductRepo(active_ids=[101, 202], all_ids=[101])
    history_repo = FakeHistoryRepo()
    service = ProductReconcileService(
        youzan_client=youzan_client,  # type: ignore[arg-type]
        product_repo=product_repo,  # type: ignore[arg-type]
        history_repo=history_repo,  # type: ignore[arg-type]
    )

    summary = await service.run()

    assert summary["checked"] == 2
    assert summary["deactivated"] == 0
    assert summary["deactivated_ids"] == []
    assert summary["sold_num_synced"] == 1
    assert summary["category_synced"] == 1
    assert summary["errors"] == ["item_id=202: database locked"]
    assert history_repo.records == []


async def test_fetch_sold_nums_ignores_api_errors_and_zero_sales() -> None:
    youzan_client = FakeYouzanClient(
        set(),
        {
            1: {"data": {"item": {"sold_num": 0, "item_no": "ZERO"}}},
            2: {"response": {"item": {"sold_num": 5, "item_no": "SKU-2"}}},
        },
    )
    service = ProductReconcileService(
        youzan_client=youzan_client,  # type: ignore[arg-type]
        product_repo=FakeProductRepo([], []),  # type: ignore[arg-type]
        history_repo=FakeHistoryRepo(),  # type: ignore[arg-type]
    )

    sold_nums = await service._fetch_sold_nums([1, 2, 3])  # noqa: SLF001

    assert sold_nums == {2: (5, "SKU-2")}
    assert sorted(youzan_client.requested_product_ids) == [1, 2, 3]


async def test_product_reconcile_syncs_item_base_categories() -> None:
    class ItemBaseClient(FakeYouzanClient):
        async def search_item_base(self, item_ids: list[int]) -> list[dict[str, Any]]:
            return [
                {
                    "item_id": item_ids[0],
                    "classification_id": 67,
                    "group_ids": [1001],
                    "second_group_ids": [2001],
                    "leaf_category_id": 3001,
                }
            ]

        async def search_item_classifications(self) -> list[dict[str, Any]]:
            return [
                {
                    "classification_id": 67,
                    "name": "生日蛋糕",
                    "parent_classification_id": 0,
                }
            ]

    youzan_client = ItemBaseClient(
        {101},
        {101: {"data": {"item": {"sold_num": 1, "item_no": "SKU-101"}}}},
    )
    product_repo = FakeProductRepo(active_ids=[101], all_ids=[101])
    service = ProductReconcileService(
        youzan_client=youzan_client,  # type: ignore[arg-type]
        product_repo=product_repo,  # type: ignore[arg-type]
        history_repo=FakeHistoryRepo(),  # type: ignore[arg-type]
    )

    summary = await service.run()

    assert summary["category_synced"] == 2
    assert product_repo.item_base_category_updates == {
        101: {
            "classification_ids": ["67"],
            "group_ids": ["1001"],
            "second_group_ids": ["2001"],
            "leaf_category_ids": ["3001"],
        }
    }
    assert ("classification-67", "生日蛋糕", 1000, 1, 1) in product_repo.categories


async def test_product_reconcile_batches_item_base_search_by_ten() -> None:
    class BatchLimitedClient(FakeYouzanClient):
        def __init__(self, onsale_ids: set[int], all_ids: list[int]) -> None:
            super().__init__(
                onsale_ids,
                {
                    item_id: {
                        "data": {"item": {"sold_num": 1, "item_no": f"SKU-{item_id}"}}
                    }
                    for item_id in all_ids
                },
            )
            self.batch_sizes: list[int] = []

        async def search_item_base(self, item_ids: list[int]) -> list[dict[str, Any]]:
            self.batch_sizes.append(len(item_ids))
            return [
                {
                    "item_id": item_id,
                    "classification_id": item_id + 1000,
                }
                for item_id in item_ids[:10]
            ]

        async def search_item_classifications(self) -> list[dict[str, Any]]:
            return []

    all_ids = list(range(1, 21))
    youzan_client = BatchLimitedClient(set(all_ids), all_ids)
    product_repo = FakeProductRepo(active_ids=all_ids, all_ids=all_ids)
    service = ProductReconcileService(
        youzan_client=youzan_client,  # type: ignore[arg-type]
        product_repo=product_repo,  # type: ignore[arg-type]
        history_repo=FakeHistoryRepo(),  # type: ignore[arg-type]
    )

    summary = await service.run()

    assert _ITEM_BASE_BATCH_SIZE == 10
    assert youzan_client.batch_sizes == [10, 10]
    assert summary["category_synced"] == 40
    assert len(product_repo.item_base_category_updates) == 20


async def test_product_reconcile_item_base_only_uses_onsale_ids() -> None:
    class OnsaleOnlyClient(FakeYouzanClient):
        def __init__(self) -> None:
            super().__init__(
                {101, 303},
                {
                    101: {"data": {"item": {"sold_num": 1, "item_no": "SKU-101"}}},
                    202: {"data": {"item": {"sold_num": 0, "item_no": "SKU-202"}}},
                    303: {"data": {"item": {"sold_num": 2, "item_no": "SKU-303"}}},
                },
            )
            self.item_base_batches: list[list[int]] = []

        async def search_item_base(self, item_ids: list[int]) -> list[dict[str, Any]]:
            self.item_base_batches.append(item_ids)
            return [
                {"item_id": item_id, "classification_id": item_id + 1000}
                for item_id in item_ids
            ]

        async def search_item_classifications(self) -> list[dict[str, Any]]:
            return []

    client = OnsaleOnlyClient()
    product_repo = FakeProductRepo(active_ids=[101, 202, 303], all_ids=[101, 202, 303])
    service = ProductReconcileService(
        youzan_client=client,  # type: ignore[arg-type]
        product_repo=product_repo,  # type: ignore[arg-type]
        history_repo=FakeHistoryRepo(),  # type: ignore[arg-type]
    )

    await service.run()

    assert client.item_base_batches == [[101, 303]]
    assert sorted(product_repo.item_base_category_updates) == [101, 303]


async def test_product_reconcile_retries_failed_vector_and_reports_counts() -> None:
    knowledge_repo = FakeVectorKnowledgeRepo(
        [_vector_candidate("10001", status="failed", retry_count=1)]
    )
    searcher = FakeVectorSearcher()
    service = ProductReconcileService(
        youzan_client=FakeYouzanClient(set()),  # type: ignore[arg-type]
        product_repo=FakeProductRepo([], []),  # type: ignore[arg-type]
        history_repo=FakeHistoryRepo(),  # type: ignore[arg-type]
        knowledge_product_repo=knowledge_repo,  # type: ignore[arg-type]
        embedding_searcher=searcher,  # type: ignore[arg-type]
    )

    summary = await service.reconcile_product_vectors()

    assert summary == {
        "claimed": 1,
        "succeeded": 1,
        "failed": 0,
        "skipped_stale": 0,
        "exhausted": 0,
    }
    assert knowledge_repo.claimed == [("10001", "2026-08-07 10:00:00")]
    assert searcher.upserted == ["10001"]


async def test_product_reconcile_marks_vector_failure_and_skips_exhausted() -> None:
    knowledge_repo = FakeVectorKnowledgeRepo(
        [
            _vector_candidate("10002", status="pending"),
            _vector_candidate("10003", status="failed", retry_count=3),
        ]
    )
    searcher = FakeVectorSearcher(fail=True)
    service = ProductReconcileService(
        youzan_client=FakeYouzanClient(set()),  # type: ignore[arg-type]
        product_repo=FakeProductRepo([], []),  # type: ignore[arg-type]
        history_repo=FakeHistoryRepo(),  # type: ignore[arg-type]
        knowledge_product_repo=knowledge_repo,  # type: ignore[arg-type]
        embedding_searcher=searcher,  # type: ignore[arg-type]
    )

    summary = await service.reconcile_product_vectors()

    assert summary == {
        "claimed": 1,
        "succeeded": 0,
        "failed": 1,
        "skipped_stale": 0,
        "exhausted": 1,
    }
    assert len(knowledge_repo.failed) == 1
    assert "retry vector failure" in knowledge_repo.failed[0][2]


async def test_product_reconcile_does_not_overwrite_stale_completion() -> None:
    knowledge_repo = FakeVectorKnowledgeRepo([_vector_candidate("10004")])
    knowledge_repo.allow_success = False
    service = ProductReconcileService(
        youzan_client=FakeYouzanClient(set()),  # type: ignore[arg-type]
        product_repo=FakeProductRepo([], []),  # type: ignore[arg-type]
        history_repo=FakeHistoryRepo(),  # type: ignore[arg-type]
        knowledge_product_repo=knowledge_repo,  # type: ignore[arg-type]
        embedding_searcher=FakeVectorSearcher(),  # type: ignore[arg-type]
    )

    summary = await service.reconcile_product_vectors()

    assert summary["claimed"] == 1
    assert summary["succeeded"] == 0
    assert summary["skipped_stale"] == 1
