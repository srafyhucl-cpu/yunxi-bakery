import aiosqlite

from app.models.customer_master import CustomerIdentityType, CustomerSourceSystem
from app.repository.customer_master_repo import CustomerMasterRepo
from app.service.customer import CustomerImportService, CustomerMasterService
from app.service.customer.importer import CustomerImportPayload


async def test_import_service_auto_merge_creates_master_identity_and_snapshot(
    db: aiosqlite.Connection,
) -> None:
    repo = CustomerMasterRepo(db)
    service = CustomerImportService(repo, CustomerMasterService(repo))

    result = await service.import_record(
        CustomerImportPayload(
            tenant_id="tenant-yunxi",
            source_record_id="customer-row-1",
            source_batch_id="batch-001",
            proposed_bucket="auto_merge",
            confidence_level="high",
            source_system=CustomerSourceSystem.YOUZAN.value,
            source_channel="有赞后台",
            source_method="外部导入",
            primary_phone="18800000011",
            display_name="自动归并客户",
            snapshot_payload={"客户昵称": "自动归并客户"},
            normalized_payload={"primary_phone": "18800000011"},
        )
    )

    customer = await repo.get_master(result.customer_id)
    identities = await repo.list_identity_links(result.customer_id)
    snapshots = await repo.list_source_snapshots(customer_id=result.customer_id)

    assert result.resolved_bucket == "auto_merge"
    assert result.merge_review_id is None
    assert customer is not None
    assert customer.primary_phone == "18800000011"
    assert len(identities) == 2
    assert {identity.identity_type for identity in identities} == {
        CustomerIdentityType.PHONE.value,
        CustomerIdentityType.YOUZAN_CUSTOMER.value,
    }
    assert len(snapshots) == 1


async def test_import_service_pending_review_creates_review_record(
    db: aiosqlite.Connection,
) -> None:
    repo = CustomerMasterRepo(db)
    service = CustomerImportService(repo, CustomerMasterService(repo))

    result = await service.import_record(
        CustomerImportPayload(
            tenant_id="tenant-yunxi",
            source_record_id="customer-row-2",
            source_batch_id="batch-001",
            proposed_bucket="pending_review",
            confidence_level="low",
            source_system=CustomerSourceSystem.YOUZAN.value,
            source_channel="微信小程序",
            source_method="登录创建客户",
            primary_phone="18800000012",
            display_name="待复核客户",
            conflict_flags=("name_conflict_same_phone",),
            matched_order_phone="18800000012",
            snapshot_payload={"客户昵称": "待复核客户"},
            normalized_payload={"primary_phone": "18800000012"},
        )
    )

    review = await repo.get_merge_review(result.merge_review_id or "")
    identities = await repo.list_identity_links(result.customer_id)

    assert result.resolved_bucket == "pending_review"
    assert result.merge_review_id
    assert review is not None
    assert review.source_customer_id == result.customer_id
    assert len(identities) == 2
    assert {identity.link_status for identity in identities} == {"pending_review"}


async def test_import_service_skip_same_batch_duplicate_snapshot(
    db: aiosqlite.Connection,
) -> None:
    repo = CustomerMasterRepo(db)
    service = CustomerImportService(repo, CustomerMasterService(repo))
    payload = CustomerImportPayload(
        tenant_id="tenant-yunxi",
        source_record_id="customer-row-3",
        source_batch_id="batch-001",
        proposed_bucket="auto_merge",
        confidence_level="high",
        source_system=CustomerSourceSystem.YOUZAN.value,
        source_channel="有赞后台",
        source_method="外部导入",
        primary_phone="18800000013",
        display_name="重复批次客户",
        snapshot_payload={"客户昵称": "重复批次客户"},
        normalized_payload={
            "primary_phone": "18800000013",
            "proposed_bucket": "auto_merge",
        },
    )

    first_result = await service.import_record(payload)
    second_result = await service.import_record(payload)

    identities = await repo.list_identity_links(first_result.customer_id)
    snapshots = await repo.list_source_snapshots(customer_id=first_result.customer_id)

    assert second_result.action == "skip_existing_batch_row"
    assert second_result.customer_id == first_result.customer_id
    assert second_result.snapshot_id == first_result.snapshot_id
    assert second_result.identity_link_id == first_result.identity_link_id
    assert len(identities) == 2
    assert len(snapshots) == 1


async def test_import_service_reuses_source_identity_across_batches(
    db: aiosqlite.Connection,
) -> None:
    repo = CustomerMasterRepo(db)
    service = CustomerImportService(repo, CustomerMasterService(repo))
    base_payload = {
        "tenant_id": "tenant-yunxi",
        "source_record_id": "customer-row-4",
        "proposed_bucket": "new_master",
        "confidence_level": "low",
        "source_system": CustomerSourceSystem.YOUZAN.value,
        "source_channel": "有赞后台",
        "source_method": "外部导入",
        "display_name": "跨批次客户",
        "snapshot_payload": {"客户昵称": "跨批次客户"},
        "normalized_payload": {"proposed_bucket": "new_master"},
    }

    first_result = await service.import_record(
        CustomerImportPayload(
            **base_payload,
            source_batch_id="batch-001",
        )
    )
    second_result = await service.import_record(
        CustomerImportPayload(
            **base_payload,
            source_batch_id="batch-002",
        )
    )

    identities = await repo.list_identity_links(first_result.customer_id)
    snapshots = await repo.list_source_snapshots(customer_id=first_result.customer_id)

    assert second_result.action == "reuse_source_identity"
    assert second_result.customer_id == first_result.customer_id
    assert len(identities) == 1
    assert identities[0].identity_type == CustomerIdentityType.YOUZAN_CUSTOMER.value
    assert len(snapshots) == 2


async def test_import_service_pending_review_reuses_review_across_batches(
    db: aiosqlite.Connection,
) -> None:
    repo = CustomerMasterRepo(db)
    service = CustomerImportService(repo, CustomerMasterService(repo))
    base_payload = {
        "tenant_id": "tenant-yunxi",
        "source_record_id": "customer-row-5",
        "proposed_bucket": "pending_review",
        "confidence_level": "low",
        "source_system": CustomerSourceSystem.YOUZAN.value,
        "source_channel": "微信小程序",
        "source_method": "登录创建客户",
        "primary_phone": "18800000015",
        "display_name": "复核复用客户",
        "conflict_flags": ("name_conflict_same_phone",),
        "matched_order_phone": "18800000015",
        "snapshot_payload": {"客户昵称": "复核复用客户"},
        "normalized_payload": {
            "primary_phone": "18800000015",
            "proposed_bucket": "pending_review",
        },
    }

    first_result = await service.import_record(
        CustomerImportPayload(
            **base_payload,
            source_batch_id="batch-001",
        )
    )
    second_result = await service.import_record(
        CustomerImportPayload(
            **base_payload,
            source_batch_id="batch-002",
        )
    )

    reviews = await repo.list_merge_reviews(tenant_id="tenant-yunxi")
    snapshots = await repo.list_source_snapshots(customer_id=first_result.customer_id)

    assert second_result.action == "reuse_review_customer"
    assert second_result.customer_id == first_result.customer_id
    assert second_result.merge_review_id == first_result.merge_review_id
    assert len(reviews) == 1
    assert len(snapshots) == 2
