"""后台每日库存 API 测试。"""

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.api.admin.daily_stock import create_admin_daily_stock_router
from app.config import settings
from app.repository.product_daily_stock_repo import ProductDailyStockRepo
from app.service.catalog.daily_stock import ProductDailyStockService

STOCK_DATE = "2026-10-20"
NEXT_DATE = "2026-10-21"


@pytest.fixture
def service(db: aiosqlite.Connection) -> ProductDailyStockService:
    """构建后台每日库存 API 使用的真实服务。"""
    return ProductDailyStockService(ProductDailyStockRepo(db))


@pytest.fixture
def app(service: ProductDailyStockService) -> FastAPI:
    """构建只包含后台每日库存路由的测试应用。"""
    test_app = FastAPI()
    test_app.include_router(create_admin_daily_stock_router(service))
    return test_app


@pytest.fixture
def headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}


async def _seed_product(
    db: aiosqlite.Connection,
    item_id: int,
    *,
    is_active: int = 1,
    stock: int = 20,
) -> None:
    await db.execute(
        "INSERT INTO youzan_products "
        "(item_id, title, alias, price_fen, stock, is_active, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
        (item_id, f"现烤面包{item_id}", f"daily-{item_id}", 1200, stock, is_active),
    )
    await db.commit()


async def _list_items(
    app: FastAPI,
    headers: dict[str, str],
    stock_date: str = STOCK_DATE,
) -> list[dict]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/admin/daily-stock",
            params={"date": stock_date},
            headers=headers,
        )
    assert response.status_code == 200
    return response.json()["data"]["items"]


@pytest.mark.asyncio
async def test_admin_daily_stock_requires_token(app: FastAPI) -> None:
    """后台每日库存接口必须校验管理员 Token。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/admin/daily-stock")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_returns_active_products_without_records(
    app: FastAPI,
    db: aiosqlite.Connection,
    service: ProductDailyStockService,
    headers: dict[str, str],
) -> None:
    """首次查询返回全部在售商品；已下架但当天有记录的商品继续保留。"""
    await _seed_product(db, 101)
    await _seed_product(db, 102, is_active=0)
    await _seed_product(db, 103, is_active=0)
    await service.set_total(STOCK_DATE, "103", 4, "admin:test")

    items = await _list_items(app, headers)

    assert [item["product_id"] for item in items] == ["101", "103"]
    assert items[0]["total_qty"] == 0
    assert items[0]["reserved_qty"] == 0
    assert items[0]["available_qty"] == 0
    assert items[0]["configured"] is False
    assert items[0]["youzan_stock"] == 20
    assert items[1]["configured"] is True
    assert items[1]["is_active"] == 0


@pytest.mark.asyncio
async def test_put_saves_total_and_list_shows_configured(
    app: FastAPI,
    db: aiosqlite.Connection,
    headers: dict[str, str],
) -> None:
    """保存总量后列表可见，且可售量按总量减预占计算。"""
    await _seed_product(db, 101)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.put(
            "/api/v1/admin/daily-stock/101",
            json={"date": STOCK_DATE, "totalQty": 8},
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json()["data"]["total_qty"] == 8
    items = await _list_items(app, headers)
    assert items[0]["configured"] is True
    assert items[0]["total_qty"] == 8
    assert items[0]["available_qty"] == 8
    assert items[0]["updated_by"].startswith("admin:")


@pytest.mark.asyncio
async def test_put_rejects_total_below_reserved(
    app: FastAPI,
    db: aiosqlite.Connection,
    service: ProductDailyStockService,
    headers: dict[str, str],
) -> None:
    """录入总量低于已预占数量时返回 400，且不改变原总量。"""
    await _seed_product(db, 101)
    await service.set_total(STOCK_DATE, "101", 5, "admin:test")
    await service.reserve("101", STOCK_DATE, 3)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.put(
            "/api/v1/admin/daily-stock/101",
            json={"date": STOCK_DATE, "totalQty": 2},
            headers=headers,
        )

    assert response.status_code == 400
    assert "不能低于已预占" in response.json()["detail"]
    items = await _list_items(app, headers)
    assert items[0]["total_qty"] == 5
    assert items[0]["reserved_qty"] == 3


@pytest.mark.asyncio
async def test_cross_day_list_copies_previous_total(
    app: FastAPI,
    db: aiosqlite.Connection,
    headers: dict[str, str],
) -> None:
    """跨日查询复制昨日总量，预占量从零开始。"""
    await _seed_product(db, 101)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        await client.put(
            "/api/v1/admin/daily-stock/101",
            json={"date": STOCK_DATE, "totalQty": 6},
            headers=headers,
        )

    items = await _list_items(app, headers, NEXT_DATE)
    assert items[0]["total_qty"] == 6
    assert items[0]["reserved_qty"] == 0
    assert items[0]["configured"] is True
    assert items[0]["updated_by"] == "system_copy"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_total", [8.5, "8.5", "8.0", True, None, "", "abc"])
async def test_put_rejects_non_integer_total(
    app: FastAPI,
    db: aiosqlite.Connection,
    headers: dict[str, str],
    bad_total: object,
) -> None:
    """总量只接受整数或纯数字字符串，小数、布尔和空值必须拒绝。"""
    await _seed_product(db, 101)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.put(
            "/api/v1/admin/daily-stock/101",
            json={"date": STOCK_DATE, "totalQty": bad_total},
            headers=headers,
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "每日库存总量必须是整数"


@pytest.mark.asyncio
async def test_put_accepts_numeric_string_total(
    app: FastAPI,
    db: aiosqlite.Connection,
    headers: dict[str, str],
) -> None:
    """纯数字字符串（如前端的输入框值）正常保存。"""
    await _seed_product(db, 101)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.put(
            "/api/v1/admin/daily-stock/101",
            json={"date": STOCK_DATE, "totalQty": "008"},
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json()["data"]["total_qty"] == 8


@pytest.mark.asyncio
async def test_put_does_not_change_youzan_stock(
    app: FastAPI,
    db: aiosqlite.Connection,
    headers: dict[str, str],
) -> None:
    """保存每日库存只写 product_daily_stock，不改有赞库存。"""
    await _seed_product(db, 101, stock=20)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        await client.put(
            "/api/v1/admin/daily-stock/101",
            json={"date": STOCK_DATE, "totalQty": 5},
            headers=headers,
        )

    rows = await db.execute_fetchall(
        "SELECT stock FROM youzan_products WHERE item_id = 101"
    )
    assert rows[0]["stock"] == 20


@pytest.mark.asyncio
async def test_put_unknown_product_returns_404(
    app: FastAPI,
    headers: dict[str, str],
) -> None:
    """非法商品返回 404。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.put(
            "/api/v1/admin/daily-stock/999",
            json={"date": STOCK_DATE, "totalQty": 5},
            headers=headers,
        )
    assert response.status_code == 404
