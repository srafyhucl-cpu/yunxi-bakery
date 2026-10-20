"""店员快捷开单测试公共造数与真实服务装配。"""

import aiosqlite

from app.models.customer_master import (
    CustomerIdentityLinkCreate,
    CustomerIdentityType,
    CustomerMasterCreate,
)
from app.models.staff import StaffPrincipal
from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.cake_slot_repo import CakeSlotRepo
from app.repository.config_repo import ConfigRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.session_repo import SessionRepo
from app.repository.staff_quick_order_repo import StaffQuickOrderRequestRepo
from app.repository.staff_repo import StaffAuditRepo
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_order_repo import YouzanOrderRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.channels.storefront.auth import StorefrontAuthService
from app.service.order import OrderApplicationService
from app.service.order.cake_slots import CakeSlotCapacityService
from app.service.staff_quick_order import (
    MODE_STORED_VALUE_DIRECT,
    StaffQuickOrderService,
)
from app.service.stored_value import (
    MemberBalanceService,
    StoredValueOrderPaymentService,
    StoredValueService,
)
from tests.helpers.catalog_seed import seed_catalog_product

PHONE = "13800000031"
OPENID = "openid_quick_create"
USER_ID = f"wx_{OPENID}"
PRODUCT_ID = 92001
PRODUCT_PRICE_FEN = 5000
EXPECT_TIME = "2099-06-18 12:00"


def principal(staff_id: str = "staff_quick_create_001") -> StaffPrincipal:
    return StaffPrincipal(
        id=staff_id,
        name="收银员小王",
        phone="13800000001",
        role="cashier",
        tenant_id="yunxi",
    )


async def seed_member(
    db: aiosqlite.Connection,
    *,
    phone: str = PHONE,
    user_id: str = USER_ID,
    balance_fen: int = 0,
) -> None:
    """使用真实前台认领链路创建已绑定小程序的会员。"""
    await StorefrontAuthService(
        customer_repo=CustomerMasterRepo(db),
        member_balance_repo=MemberBalanceRepo(db),
        db=db,
    ).claim_member_by_phone(user_id=user_id, phone=phone)
    balance_repo = MemberBalanceRepo(db)
    await balance_repo.upsert_identity(
        mobile=phone,
        display_name="张三",
        is_member=1,
    )
    if balance_fen:
        await balance_repo.credit_stored_value(phone, amount_fen=balance_fen)
    await db.commit()


async def seed_unbound_member(db: aiosqlite.Connection, *, phone: str) -> None:
    """只登记手机号、不绑定小程序 openid 的会员。"""
    repo = CustomerMasterRepo(db)
    master = await repo.create_master(
        CustomerMasterCreate(
            tenant_id="yunxi",
            primary_phone=phone,
            phone_verified=1,
            display_name="李四",
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
    await db.commit()


async def seed_product(
    db: aiosqlite.Connection,
    *,
    item_id: int = PRODUCT_ID,
    price_fen: int = PRODUCT_PRICE_FEN,
) -> None:
    await seed_catalog_product(
        db,
        item_id=item_id,
        title="现烤可颂",
        price_fen=price_fen,
        stock=10,
    )
    await db.commit()


def build_stack(
    db: aiosqlite.Connection,
) -> tuple[StaffQuickOrderService, OrderRepo, StaffAuditRepo]:
    """用真实内存库仓储与服务装配快捷开单栈。"""
    order_repo = OrderRepo(db)
    member_service = MemberBalanceService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=BalanceLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
    )
    stored_value_service = StoredValueService(
        member_service=member_service,
        payment_service=StoredValueOrderPaymentService(
            order_repo=order_repo,
            member_service=member_service,
        ),
    )
    order_service = OrderApplicationService(
        order_repo=order_repo,
        event_repo=OrderEventRepo(db),
        session_repo=SessionRepo(db),
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
        config_repo=ConfigRepo(db),
        stored_value_service=stored_value_service,
        slot_service=CakeSlotCapacityService(CakeSlotRepo(db)),
    )
    audit_repo = StaffAuditRepo(db)
    service = StaffQuickOrderService(
        customer_repo=CustomerMasterRepo(db),
        member_balance_repo=MemberBalanceRepo(db),
        youzan_order_repo=YouzanOrderRepo(db),
        order_service=order_service,
        stored_value_service=stored_value_service,
        order_repo=order_repo,
        request_repo=StaffQuickOrderRequestRepo(db),
        staff_audit_repo=audit_repo,
    )
    return service, order_repo, audit_repo


def create_payload(
    request_id: str,
    *,
    mode: str = MODE_STORED_VALUE_DIRECT,
    phone: str = PHONE,
    fulfillment_method: str = "pickup",
    item_id: int = PRODUCT_ID,
) -> dict:
    return {
        "requestId": request_id,
        "mode": mode,
        "phone": phone,
        "items": [
            {
                "productId": str(item_id),
                "quantity": 1,
                "fulfillmentType": "DAILY_READY",
            }
        ],
        "fulfillmentMethod": fulfillment_method,
        "expectTime": EXPECT_TIME,
        "remark": "门店开单",
    }


async def order_count(db: aiosqlite.Connection) -> int:
    rows = await db.execute_fetchall("SELECT COUNT(*) AS total FROM orders")
    return int(rows[0]["total"])


async def balance_fen(db: aiosqlite.Connection, phone: str = PHONE) -> int:
    return await MemberBalanceRepo(db).get_stored_value_fen(phone)


async def pay_ledger_count(db: aiosqlite.Connection, phone: str = PHONE) -> int:
    rows = await db.execute_fetchall(
        "SELECT COUNT(*) AS total FROM balance_ledger "
        "WHERE mobile = ? AND biz_type = 'order_pay'",
        (phone,),
    )
    return int(rows[0]["total"])


__all__ = [
    "PHONE",
    "PRODUCT_ID",
    "balance_fen",
    "build_stack",
    "create_payload",
    "order_count",
    "pay_ledger_count",
    "principal",
    "seed_member",
    "seed_product",
    "seed_unbound_member",
]
