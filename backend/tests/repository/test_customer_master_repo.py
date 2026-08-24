import aiosqlite

from app.models.customer_master import (
    CustomerIdentityLinkCreate,
    CustomerIdentityType,
    CustomerMasterCreate,
    CustomerSourceSystem,
)
from app.repository.customer_master_repo import CustomerMasterRepo


async def test_customer_master_repo_create_and_query_by_phone(
    db: aiosqlite.Connection,
) -> None:
    repo = CustomerMasterRepo(db)

    created = await repo.create_master(
        CustomerMasterCreate(
            tenant_id="tenant-yunxi",
            primary_phone="18800000001",
            phone_verified=1,
            display_name="芸熙客户",
            first_source=CustomerSourceSystem.YOUZAN.value,
            has_youzan_identity=1,
        )
    )

    fetched = await repo.get_master(created.id)
    same_phone = await repo.get_by_phone("tenant-yunxi", "18800000001")

    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.display_name == "芸熙客户"
    assert [item.id for item in same_phone] == [created.id]


async def test_customer_master_repo_create_and_list_identity_links(
    db: aiosqlite.Connection,
) -> None:
    repo = CustomerMasterRepo(db)
    customer = await repo.create_master(
        CustomerMasterCreate(
            tenant_id="tenant-yunxi",
            primary_phone="18800000002",
            display_name="身份客户",
        )
    )

    created = await repo.create_identity_link(
        CustomerIdentityLinkCreate(
            customer_id=customer.id,
            tenant_id="tenant-yunxi",
            identity_type=CustomerIdentityType.PHONE.value,
            identity_value="18800000002",
            identity_value_normalized="18800000002",
            source_system=CustomerSourceSystem.YOUZAN.value,
            source_record_id="youzan-customer-001",
            confidence_score=100,
            verification_status="verified",
        )
    )

    fetched = await repo.get_identity_by_value(
        "tenant-yunxi",
        CustomerIdentityType.PHONE.value,
        "18800000002",
    )
    items = await repo.list_identity_links(customer.id)

    assert fetched is not None
    assert fetched.id == created.id
    assert len(items) == 1
    assert items[0].customer_id == customer.id
