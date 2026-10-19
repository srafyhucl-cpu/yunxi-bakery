"""店员快捷开单查询 API 测试。"""

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.api.staff.auth import create_staff_auth_router
from app.api.staff.quick_order import create_staff_quick_order_router
from app.models.customer_master import (
    CustomerIdentityLinkCreate,
    CustomerIdentityType,
    CustomerMasterCreate,
)
from app.repository.config_repo import ConfigRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.knowledge_product_repo import KnowledgeProductRepo
from app.repository.knowledge_repo import KnowledgeRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.staff_repo import StaffAuditRepo, StaffRepo
from app.repository.youzan_order_repo import YouzanOrderRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.catalog import CatalogApplicationService
from app.service.staff_auth import StaffAuthService
from app.service.staff_quick_order import StaffQuickOrderService
from tests.helpers.miniapp_catalog_seed import seed_miniapp_product


@pytest.fixture(autouse=True)
def isolate_login_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """隔离真实边缘防护库，避免登录测试写入磁盘数据库。"""

    async def allow(_key: str) -> bool:
        return True

    async def noop(_key: str) -> None:
        return None

    monkeypatch.setattr("app.api.staff.auth.attempt_admin_login", allow)
    monkeypatch.setattr("app.api.staff.auth.clear_admin_login_failures", noop)


@pytest.fixture
def auth_service(db: aiosqlite.Connection) -> StaffAuthService:
    return StaffAuthService(
        staff_repo=StaffRepo(db),
        audit_repo=StaffAuditRepo(db),
    )


@pytest.fixture
def quick_order_service(
    db: aiosqlite.Connection,
) -> StaffQuickOrderService:
    return StaffQuickOrderService(
        customer_repo=CustomerMasterRepo(db),
        member_balance_repo=MemberBalanceRepo(db),
        youzan_order_repo=YouzanOrderRepo(db),
        catalog_service=CatalogApplicationService(
            product_repo=KnowledgeProductRepo(db),
            knowledge_repo=KnowledgeRepo(db),
            config_repo=ConfigRepo(db),
            youzan_product_repo=YouzanProductRepo(db),
        ),
        audit_repo=StaffAuditRepo(db),
    )


@pytest.fixture
def app(
    auth_service: StaffAuthService,
    quick_order_service: StaffQuickOrderService,
) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(create_staff_auth_router(auth_service))
    test_app.include_router(
        create_staff_quick_order_router(quick_order_service, auth_service)
    )
    return test_app


async def _bind_member(
    db: aiosqlite.Connection,
    *,
    phone: str,
    openid: str,
) -> str:
    repo = CustomerMasterRepo(db)
    master = await repo.create_master(
        CustomerMasterCreate(
            tenant_id="yunxi",
            primary_phone=phone,
            phone_verified=1,
            display_name="张三",
            has_miniapp_identity=1,
        )
    )
    await repo.create_identity_link(
        CustomerIdentityLinkCreate(
            tenant_id="yunxi",
            customer_id=master.id,
            identity_type=CustomerIdentityType.PHONE.value,
            identity_value=phone,
        )
    )
    await repo.create_identity_link(
        CustomerIdentityLinkCreate(
            tenant_id="yunxi",
            customer_id=master.id,
            identity_type=CustomerIdentityType.MINIAPP_OPENID.value,
            identity_value=openid,
        )
    )
    return master.id


@pytest.mark.asyncio
async def test_staff_quick_order_requires_login(app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        member_response = await client.get(
            "/api/v1/staff/quick-order/member-lookup",
            params={"phone": "13800000011"},
        )
        products_response = await client.get("/api/v1/staff/quick-order/products")

    assert member_response.status_code == 401
    assert products_response.status_code == 401


@pytest.mark.asyncio
async def test_staff_member_lookup_and_product_search_after_login(
    db: aiosqlite.Connection,
    app: FastAPI,
    auth_service: StaffAuthService,
) -> None:
    await auth_service.create_staff("小王", "13800000001", "cashier", "2468")
    phone = "13800000011"
    customer_id = await _bind_member(db, phone=phone, openid="openid_api_member")
    balance_repo = MemberBalanceRepo(db)
    await balance_repo.upsert_identity(
        mobile=phone,
        yz_open_id="yz_openid_api_member",
        display_name="张三",
        is_member=1,
    )
    await balance_repo.credit_stored_value(phone, amount_fen=15000, bonus_fen=5000)
    await balance_repo.credit_points(phone, 80)
    await seed_miniapp_product(
        db,
        item_id=82001,
        title="API 快捷开单草莓蛋糕",
        keywords="草莓,蛋糕",
        price_fen=26800,
        stock=4,
    )
    await db.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        login_response = await client.post(
            "/api/v1/staff/auth/login",
            json={"phone": "13800000001", "pin": "2468"},
        )
        member_response = await client.get(
            "/api/v1/staff/quick-order/member-lookup",
            params={"phone": phone},
        )
        products_response = await client.get(
            "/api/v1/staff/quick-order/products",
            params={"keyword": "草莓"},
        )

    assert login_response.status_code == 200
    assert member_response.status_code == 200
    member = member_response.json()["data"]
    assert member["customerId"] == customer_id
    assert member["userId"] == "wx_openid_api_member"
    assert member["principalFen"] == 10000
    assert member["bonusFen"] == 5000
    assert member["points"] == 80

    assert products_response.status_code == 200
    products = products_response.json()["data"]
    assert products == [
        {
            "productId": "82001",
            "title": "API 快捷开单草莓蛋糕",
            "priceFen": 26800,
            "stock": 4,
            "isPurchasable": True,
            "imageUrl": "https://img.example/product.jpg",
        }
    ]


@pytest.mark.asyncio
async def test_staff_member_lookup_maps_missing_and_unbound_errors(
    db: aiosqlite.Connection,
    app: FastAPI,
    auth_service: StaffAuthService,
) -> None:
    await auth_service.create_staff("小李", "13800000002", "manager", "1357")
    unbound_phone = "13800000012"
    repo = CustomerMasterRepo(db)
    master = await repo.create_master(
        CustomerMasterCreate(
            tenant_id="yunxi",
            primary_phone=unbound_phone,
            phone_verified=1,
        )
    )
    await repo.create_identity_link(
        CustomerIdentityLinkCreate(
            tenant_id="yunxi",
            customer_id=master.id,
            identity_type=CustomerIdentityType.PHONE.value,
            identity_value=unbound_phone,
        )
    )
    await db.commit()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        await client.post(
            "/api/v1/staff/auth/login",
            json={"phone": "13800000002", "pin": "1357"},
        )
        missing_response = await client.get(
            "/api/v1/staff/quick-order/member-lookup",
            params={"phone": "13900000000"},
        )
        unbound_response = await client.get(
            "/api/v1/staff/quick-order/member-lookup",
            params={"phone": unbound_phone},
        )
        invalid_response = await client.get(
            "/api/v1/staff/quick-order/member-lookup",
            params={"phone": "1380000"},
        )

    assert missing_response.status_code == 404
    assert unbound_response.status_code == 400
    assert invalid_response.status_code == 400
