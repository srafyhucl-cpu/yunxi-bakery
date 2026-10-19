"""店员快捷开单查询服务测试。"""

import aiosqlite
import pytest

from app.models.customer_master import (
    CustomerIdentityLinkCreate,
    CustomerIdentityType,
    CustomerMasterCreate,
)
from app.models.staff import StaffPrincipal
from app.repository.config_repo import ConfigRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.knowledge_product_repo import KnowledgeProductRepo
from app.repository.knowledge_repo import KnowledgeRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.staff_repo import StaffAuditRepo
from app.repository.youzan_order_repo import YouzanOrderRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.catalog import CatalogApplicationService
from app.service.staff_quick_order import StaffQuickOrderService
from tests.helpers.miniapp_catalog_seed import seed_miniapp_product


def _principal() -> StaffPrincipal:
    return StaffPrincipal(
        id="staff_test_001",
        name="收银员小王",
        phone="13800000001",
        role="cashier",
        tenant_id="yunxi",
    )


def _catalog_service(db: aiosqlite.Connection) -> CatalogApplicationService:
    return CatalogApplicationService(
        product_repo=KnowledgeProductRepo(db),
        knowledge_repo=KnowledgeRepo(db),
        config_repo=ConfigRepo(db),
        youzan_product_repo=YouzanProductRepo(db),
    )


def _quick_order_service(
    db: aiosqlite.Connection,
) -> tuple[StaffQuickOrderService, StaffAuditRepo]:
    audit_repo = StaffAuditRepo(db)
    service = StaffQuickOrderService(
        customer_repo=CustomerMasterRepo(db),
        member_balance_repo=MemberBalanceRepo(db),
        youzan_order_repo=YouzanOrderRepo(db),
        catalog_service=_catalog_service(db),
        audit_repo=audit_repo,
    )
    return service, audit_repo


async def _bind_miniapp_member(
    db: aiosqlite.Connection,
    *,
    phone: str,
    openid: str,
    customer_id: str = "",
    with_miniapp: bool = True,
) -> str:
    customer_repo = CustomerMasterRepo(db)
    master = await customer_repo.create_master(
        CustomerMasterCreate(
            tenant_id="yunxi",
            primary_phone=phone,
            phone_verified=1,
            display_name="张三",
            has_miniapp_identity=1 if with_miniapp else 0,
        )
    )
    resolved_id = customer_id or master.id
    await customer_repo.create_identity_link(
        CustomerIdentityLinkCreate(
            tenant_id="yunxi",
            customer_id=resolved_id,
            identity_type=CustomerIdentityType.PHONE.value,
            identity_value=phone,
        )
    )
    if with_miniapp:
        await customer_repo.create_identity_link(
            CustomerIdentityLinkCreate(
                tenant_id="yunxi",
                customer_id=resolved_id,
                identity_type=CustomerIdentityType.MINIAPP_OPENID.value,
                identity_value=openid,
            )
        )
    return resolved_id


@pytest.mark.asyncio
async def test_lookup_member_returns_balance_openid_and_history(
    db: aiosqlite.Connection,
) -> None:
    phone = "13800000011"
    customer_id = await _bind_miniapp_member(
        db, phone=phone, openid="openid_quick_order"
    )
    balance_repo = MemberBalanceRepo(db)
    await balance_repo.upsert_identity(
        mobile=phone,
        yz_open_id="yz_openid_quick_order",
        display_name="张三",
        is_member=1,
    )
    await balance_repo.credit_stored_value(phone, amount_fen=15000, bonus_fen=5000)
    await balance_repo.credit_points(phone, 200)
    await db.execute(
        "INSERT INTO youzan_orders (order_no, buyer_id, outer_user_id, status, "
        "amount_fen, product_titles, total_quantity, pay_time, created_at, updated_at) "
        "VALUES (?, ?, ?, 'TRADE_SUCCESS', 9900, '经典草莓蛋糕', 1, "
        "'2026-10-18 12:00:00', '2026-10-18 11:50:00', '2026-10-18 12:00:00')",
        ("EQ20261018001", "yz_openid_quick_order", phone),
    )
    await db.commit()

    service, audit_repo = _quick_order_service(db)
    result = await service.lookup_member(phone, _principal())

    assert result["customerId"] == customer_id
    assert result["mobile"] == phone
    assert result["userId"] == "wx_openid_quick_order"
    assert result["displayName"] == "张三"
    assert result["isMember"] is True
    assert result["storedValueFen"] == 15000
    assert result["principalFen"] == 10000
    assert result["bonusFen"] == 5000
    assert result["points"] == 200
    assert result["historyOrders"][0]["orderNo"] == "EQ20261018001"
    assert result["historyOrders"][0]["amountFen"] == 9900

    logs = await audit_repo.list_audit("staff_test_001")
    assert logs[0].action == "lookup_member"
    assert logs[0].target_id == customer_id
    assert phone not in logs[0].detail_json
    assert "138****0011" in logs[0].detail_json


@pytest.mark.asyncio
async def test_lookup_member_rejects_missing_or_unbound_member(
    db: aiosqlite.Connection,
) -> None:
    service, _audit_repo = _quick_order_service(db)

    with pytest.raises(ValueError, match="未找到该会员"):
        await service.lookup_member("13900000000", _principal())

    unbound_phone = "13800000012"
    await _bind_miniapp_member(
        db,
        phone=unbound_phone,
        openid="openid_unused",
        with_miniapp=False,
    )
    with pytest.raises(ValueError, match="尚未绑定小程序"):
        await service.lookup_member(unbound_phone, _principal())

    with pytest.raises(ValueError, match="11位手机号"):
        await service.lookup_member("1380000", _principal())


@pytest.mark.asyncio
async def test_list_products_returns_quick_order_fields_and_audits(
    db: aiosqlite.Connection,
) -> None:
    await seed_miniapp_product(
        db,
        item_id=81001,
        title="快捷开单草莓蛋糕",
        content="当季草莓搭配动物奶油。",
        keywords="草莓,蛋糕",
        price_fen=26800,
        stock=6,
        image="https://img.example/quick-order-strawberry.jpg",
    )
    await seed_miniapp_product(
        db,
        item_id=81002,
        title="快捷开单芒果千层",
        keywords="芒果,千层",
    )
    await db.commit()

    service, audit_repo = _quick_order_service(db)
    products = await service.list_products("草莓", staff=_principal())

    assert len(products) == 1
    product = products[0]
    assert product == {
        "productId": "81001",
        "title": "快捷开单草莓蛋糕",
        "priceFen": 26800,
        "stock": 6,
        "isPurchasable": True,
        "imageUrl": "https://img.example/quick-order-strawberry.jpg",
    }

    logs = await audit_repo.list_audit("staff_test_001")
    assert logs[0].action == "list_products"
    assert logs[0].detail_json == '{"keywordLength": 2, "limit": 20}'
