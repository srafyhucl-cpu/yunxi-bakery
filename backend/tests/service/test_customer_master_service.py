import aiosqlite
import pytest

from app.models.customer_master import CustomerMasterCreate, CustomerSourceSystem
from app.repository.customer_master_repo import CustomerMasterRepo
from app.service.customer import CustomerMasterService


@pytest.fixture
def service(db: aiosqlite.Connection) -> CustomerMasterService:
    return CustomerMasterService(CustomerMasterRepo(db))


async def test_create_customer_and_attach_phone_identity(
    service: CustomerMasterService,
) -> None:
    customer = await service.create_customer(
        CustomerMasterCreate(
            tenant_id="tenant-yunxi",
            primary_phone="18800000003",
            phone_verified=1,
            display_name="主档客户",
            first_source=CustomerSourceSystem.YOUZAN.value,
            has_youzan_identity=1,
        )
    )

    identity = await service.attach_identity(
        service.build_phone_identity(
            customer_id=customer["id"],
            tenant_id="tenant-yunxi",
            phone="18800000003",
            source_system=CustomerSourceSystem.YOUZAN.value,
            source_record_id="youzan-customer-002",
        )
    )
    items = await service.list_customer_identities(customer["id"])

    assert customer["displayName"] == "主档客户"
    assert identity["customerId"] == customer["id"]
    assert identity["identityValueNormalized"] == "18800000003"
    assert [item["id"] for item in items] == [identity["id"]]


async def test_find_customer_by_phone_and_reject_missing_customer(
    service: CustomerMasterService,
) -> None:
    customer = await service.create_customer(
        CustomerMasterCreate(
            tenant_id="tenant-yunxi",
            primary_phone="18800000004",
            display_name="手机号客户",
        )
    )

    matches = await service.find_customer_by_phone("tenant-yunxi", "18800000004")

    assert [item["id"] for item in matches] == [customer["id"]]
    with pytest.raises(ValueError, match="客户不存在"):
        await service.attach_identity(
            service.build_phone_identity(
                customer_id="missing-customer",
                tenant_id="tenant-yunxi",
                phone="18800000005",
                source_system=CustomerSourceSystem.YOUZAN.value,
            )
        )


async def test_list_customer_snapshots_and_batch_snapshots(
    db: aiosqlite.Connection,
) -> None:
    from app.repository.customer_master_repo import CustomerMasterRepo
    from app.service.customer.importer import (
        CustomerImportPayload,
        CustomerImportService,
    )

    repo = CustomerMasterRepo(db)
    service = CustomerMasterService(repo)
    importer = CustomerImportService(repo, service)
    result = await importer.import_record(
        CustomerImportPayload(
            tenant_id="tenant-yunxi",
            source_record_id="customer-row-3",
            source_batch_id="batch-xyz",
            proposed_bucket="new_master",
            confidence_level="low",
            source_system=CustomerSourceSystem.YOUZAN.value,
            source_channel="有赞后台",
            source_method="外部导入",
            display_name="快照客户",
            snapshot_payload={"客户昵称": "快照客户"},
            normalized_payload={"display_name": "快照客户"},
        )
    )

    customer_snapshots = await service.list_customer_snapshots(result.customer_id)
    batch_snapshots = await service.list_batch_snapshots("batch-xyz")

    assert [item["id"] for item in customer_snapshots] == [result.snapshot_id]
    assert [item["id"] for item in batch_snapshots] == [result.snapshot_id]


async def test_list_merge_reviews(
    db: aiosqlite.Connection,
) -> None:
    from app.repository.customer_master_repo import CustomerMasterRepo
    from app.service.customer.importer import (
        CustomerImportPayload,
        CustomerImportService,
    )

    repo = CustomerMasterRepo(db)
    service = CustomerMasterService(repo)
    importer = CustomerImportService(repo, service)
    await importer.import_record(
        CustomerImportPayload(
            tenant_id="tenant-yunxi",
            source_record_id="customer-row-4",
            source_batch_id="batch-review",
            proposed_bucket="pending_review",
            confidence_level="low",
            source_system=CustomerSourceSystem.YOUZAN.value,
            source_channel="微信小程序",
            source_method="登录创建客户",
            primary_phone="18800000021",
            display_name="复核客户",
            conflict_flags=("name_conflict_same_phone",),
            snapshot_payload={"客户昵称": "复核客户"},
            normalized_payload={"primary_phone": "18800000021"},
        )
    )

    reviews = await service.list_merge_reviews(
        tenant_id="tenant-yunxi",
        review_status="open",
    )

    assert len(reviews) == 1
    assert reviews[0]["reviewStatus"] == "open"
