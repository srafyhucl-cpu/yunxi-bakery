"""积分服务测试：账本幂等、预览试算。"""

import aiosqlite
import pytest

from app.repository.config_repo import ConfigRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_event_repo import OrderEventRepo
from app.repository.order_repo import OrderRepo
from app.repository.points_ledger_repo import PointsLedgerRepo
from app.repository.session_repo import SessionRepo
from app.repository.youzan_inventory_repo import YouzanInventoryRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.order import OrderApplicationService
from app.service.points import PointsService

MOBILE = "13800000002"
OPENID = "openid_m3_001"
USER_ID = f"wx_{OPENID}"


async def _seed_member(db: aiosqlite.Connection, *, points: int = 0) -> None:
    await db.execute(
        "INSERT INTO customer_master (id, tenant_id, status, primary_phone, "
        "phone_verified, display_name, identity_confidence, has_miniapp_identity) "
        "VALUES (?, 'yunxi', 'active', ?, 1, '积分测试会员', 'high', 1)",
        (f"cm_{OPENID}", MOBILE),
    )
    await db.execute(
        "INSERT INTO customer_identity_links (id, tenant_id, customer_id, "
        "identity_type, identity_value, identity_value_normalized, source_system, "
        "link_status, verification_status, confidence_score) "
        "VALUES (?, 'yunxi', ?, 'miniapp_openid', ?, ?, 'miniapp', 'active', "
        "'verified', 100)",
        (f"cil_{OPENID}", f"cm_{OPENID}", OPENID, OPENID),
    )
    if points:
        await db.execute(
            "INSERT INTO member_balance (mobile, points) VALUES (?, ?)",
            (MOBILE, points),
        )
    await db.commit()


@pytest.fixture
def points_service(db: aiosqlite.Connection) -> PointsService:
    return PointsService(
        balance_repo=MemberBalanceRepo(db),
        ledger_repo=PointsLedgerRepo(db),
        customer_repo=CustomerMasterRepo(db),
        order_repo=OrderRepo(db),
    )


@pytest.fixture
def order_service(db: aiosqlite.Connection) -> OrderApplicationService:
    return OrderApplicationService(
        order_repo=OrderRepo(db),
        event_repo=OrderEventRepo(db),
        session_repo=SessionRepo(db),
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
        config_repo=ConfigRepo(db),
    )


async def _create_order(
    order_service: OrderApplicationService, price_fen: int = 10_000
) -> str:
    created = await order_service.create_order(
        {
            "items": [
                {
                    "productId": "p_m3_001",
                    "title": "M3 积分测试蛋糕",
                    "priceFen": price_fen,
                    "quantity": 1,
                }
            ],
            "receiverName": "积分测试",
            "receiverPhone": MOBILE,
            "deliveryType": "delivery",
            "deliveryAddress": "积分测试地址",
            "expectTime": "2026-08-20 19:00",
        },
        user_id=USER_ID,
    )
    return created["orderId"]


@pytest.mark.asyncio
async def test_get_points_requires_member(
    db: aiosqlite.Connection, points_service: PointsService
) -> None:
    """未识别会员查询积分应报错。"""
    with pytest.raises(ValueError, match="当前用户未识别为会员"):
        await points_service.get_points("wx_unknown_openid")


@pytest.mark.asyncio
async def test_get_points_balance_and_ledger(
    db: aiosqlite.Connection,
    points_service: PointsService,
) -> None:
    """已识别会员返回余额与流水。"""
    await _seed_member(db, points=2000)
    result = await points_service.get_points(USER_ID)
    assert result["pointsBalance"] == 2000
    assert result["mobile"] == MOBILE
    assert isinstance(result["ledger"], list)


@pytest.mark.asyncio
async def test_redeem_preview_caps(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """预览按 50% 上限与余额约束计算。"""
    await _seed_member(db, points=100_000)
    order_id = await _create_order(order_service, price_fen=10_000)
    preview = await points_service.redeem_preview(order_id, user_id=USER_ID)
    assert preview["pointsFen"] == 5000
    assert preview["pointsUsed"] == 5000
    assert preview["remainFen"] == 5000


@pytest.mark.asyncio
async def test_redeem_preview_not_enough_points(
    db: aiosqlite.Connection,
    points_service: PointsService,
    order_service: OrderApplicationService,
) -> None:
    """积分不足 100 分预览返回 0。"""
    await _seed_member(db, points=50)
    order_id = await _create_order(order_service, price_fen=10_000)
    preview = await points_service.redeem_preview(order_id, user_id=USER_ID)
    assert preview["pointsFen"] == 0
    assert preview["pointsUsed"] == 0
