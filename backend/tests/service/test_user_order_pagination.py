"""小程序订单列表分页测试：续加载合同与权限边界。"""

import aiosqlite
import pytest

from app.models.order import Order, OrderStatus
from app.repository.order_repo import OrderRepo
from app.service.order import OrderApplicationService


async def _seed_orders(
    db: aiosqlite.Connection,
    service: OrderApplicationService,
    user_id: str,
    count: int,
    product_id: str = "82002",
) -> None:
    """直写指定数量订单，创建时间相同考验排序稳定。"""
    await db.execute(
        "INSERT OR IGNORE INTO sessions (id, channel, user_id, status) "
        "VALUES (?, ?, ?, ?)",
        ("session-1", "miniapp", user_id, "active"),
    )
    for index in range(count):
        await OrderRepo(db).create_order(
            Order(
                id=f"page-order-{user_id}-{index:03d}",
                session_id="session-1",
                channel="miniapp",
                user_id=user_id,
                products="[]",
                total_amount=10.00,
                delivery="{}",
                payment='{"status": "unpaid"}',
                status=OrderStatus.PENDING,
                remark="",
                created_at="2026-06-18 19:00:00",
                updated_at="2026-06-18 19:00:00",
            )
        )
    await db.commit()


def _service(db: aiosqlite.Connection) -> OrderApplicationService:
    """构造订单应用服务。"""
    from app.repository.config_repo import ConfigRepo
    from app.repository.session_repo import SessionRepo
    from app.repository.youzan_inventory_repo import YouzanInventoryRepo
    from app.repository.youzan_repo import YouzanProductRepo

    return OrderApplicationService(
        order_repo=OrderRepo(db),
        session_repo=SessionRepo(db),
        product_repo=YouzanProductRepo(db),
        inventory_repo=YouzanInventoryRepo(db),
        config_repo=ConfigRepo(db),
    )


@pytest.mark.asyncio
async def test_user_order_pagination_contract(db: aiosqlite.Connection) -> None:
    """25 单按 20/页返回两页，续加载标记正确。"""
    service = _service(db)
    await _seed_orders(db, service, "page-user-1", 25)
    first = await service.list_user_orders(user_id="page-user-1", page=1, page_size=20)
    second = await service.list_user_orders(user_id="page-user-1", page=2, page_size=20)
    assert first["total"] == 25
    assert first["page"] == 1
    assert first["pageSize"] == 20
    assert first["hasMore"] is True
    assert len(first["items"]) == 20
    assert second["hasMore"] is False
    assert len(second["items"]) == 5
    first_ids = [item["id"] for item in first["items"]]
    second_ids = [item["id"] for item in second["items"]]
    assert len(set(first_ids) | set(second_ids)) == 25


@pytest.mark.asyncio
async def test_user_order_sort_is_stable(db: aiosqlite.Connection) -> None:
    """相同创建时间按主键倒序，翻页无重无漏。"""
    service = _service(db)
    await _seed_orders(db, service, "page-user-2", 5)
    page = await service.list_user_orders(user_id="page-user-2", page=1, page_size=10)
    ids = [item["id"] for item in page["items"]]
    assert ids == sorted(ids, reverse=True)


@pytest.mark.asyncio
async def test_user_order_empty_and_overflow_pages(db: aiosqlite.Connection) -> None:
    """空用户与超界页返回空列表且无续页。"""
    service = _service(db)
    empty = await service.list_user_orders(user_id="nobody", page=1, page_size=20)
    assert empty == {
        "items": [],
        "total": 0,
        "page": 1,
        "pageSize": 20,
        "hasMore": False,
    }
    await _seed_orders(db, service, "page-user-3", 3)
    overflow = await service.list_user_orders(
        user_id="page-user-3", page=9, page_size=20
    )
    assert overflow["items"] == []
    assert overflow["hasMore"] is False


@pytest.mark.asyncio
async def test_user_order_page_params_clamped(db: aiosqlite.Connection) -> None:
    """非法分页参数钳制到合法范围，页大小封顶 50。"""
    service = _service(db)
    await _seed_orders(db, service, "page-user-4", 3)
    first = await service.list_user_orders(user_id="page-user-4", page=0, page_size=0)
    assert (first["page"], first["pageSize"]) == (1, 20)
    capped = await service.list_user_orders(
        user_id="page-user-4", page=1, page_size=5000
    )
    assert capped["pageSize"] == 50


@pytest.mark.asyncio
async def test_user_order_list_is_permission_scoped(
    db: aiosqlite.Connection,
) -> None:
    """用户只能看到自己的订单。"""
    service = _service(db)
    await _seed_orders(db, service, "page-user-5", 2)
    await _seed_orders(db, service, "page-user-6", 1)
    mine = await service.list_user_orders(user_id="page-user-5", page=1, page_size=20)
    assert mine["total"] == 2
    assert {item["id"] for item in mine["items"]} == {
        "page-order-page-user-5-000",
        "page-order-page-user-5-001",
    }


@pytest.mark.asyncio
async def test_user_order_pagination_beyond_fifty(
    db: aiosqlite.Connection,
) -> None:
    """55 单分三页取完，无重无漏，末页正确收尾。"""
    service = _service(db)
    await _seed_orders(db, service, "page-user-7", 55)
    seen: list[str] = []
    page_number = 1
    while True:
        page = await service.list_user_orders(
            user_id="page-user-7", page=page_number, page_size=20
        )
        seen.extend(item["id"] for item in page["items"])
        if not page["hasMore"]:
            break
        page_number += 1
        assert page_number <= 10
    assert len(seen) == 55
    assert len(set(seen)) == 55
    assert page["total"] == 55
    assert page["page"] == 3


@pytest.mark.asyncio
async def test_user_order_repeat_page_is_idempotent(
    db: aiosqlite.Connection,
) -> None:
    """重复请求同一页返回一致结果。"""
    service = _service(db)
    await _seed_orders(db, service, "page-user-8", 5)
    first = await service.list_user_orders(user_id="page-user-8", page=1, page_size=20)
    second = await service.list_user_orders(user_id="page-user-8", page=1, page_size=20)
    assert first == second


@pytest.mark.asyncio
async def test_user_order_inserted_order_visible_on_first_page(
    db: aiosqlite.Connection,
) -> None:
    """新订单出现在首页，旧页数据不受影响语义由排序保证。"""
    service = _service(db)
    await _seed_orders(db, service, "page-user-9", 2)
    await OrderRepo(db).create_order(
        Order(
            id="page-order-page-user-9-999",
            session_id="session-1",
            channel="miniapp",
            user_id="page-user-9",
            products="[]",
            total_amount=10.00,
            delivery="{}",
            payment='{"status": "unpaid"}',
            status=OrderStatus.PENDING,
            remark="",
            created_at="2026-06-19 19:00:00",
            updated_at="2026-06-19 19:00:00",
        )
    )
    await db.commit()
    first = await service.list_user_orders(user_id="page-user-9", page=1, page_size=20)
    assert first["total"] == 3
    assert first["hasMore"] is False
    assert first["items"][0]["id"] == "page-order-page-user-9-999"
