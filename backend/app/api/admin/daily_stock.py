"""后台每日现烤库存 API。"""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.api.admin import verify_token
from app.api.admin.addresses import _admin_operator
from app.service.catalog.daily_stock import ProductDailyStockService


def create_admin_daily_stock_router(service: ProductDailyStockService) -> APIRouter:
    """创建后台每日库存路由。"""
    router = APIRouter(
        prefix="/api/v1/admin/daily-stock",
        tags=["admin-daily-stock"],
        dependencies=[Depends(verify_token)],
    )

    @router.get("")
    async def list_daily_stock(
        date: str = Query(default=""),
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """按日期查看每日库存：未录入的商品也会返回，便于首次初始化。"""
        stock_date = date.strip() or service.current_stock_date()
        try:
            items = await service.list_for_date(stock_date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": {"date": stock_date, "items": items}}

    @router.put("/{product_id}")
    async def set_daily_stock(
        product_id: str,
        payload: dict[str, Any],
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """录入单个商品当日总量，只写 product_daily_stock，不改有赞库存。"""
        stock_date, total_qty = _parse_stock_payload(payload, service)
        try:
            items = await service.list_for_date(stock_date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not any(item["product_id"] == product_id for item in items):
            raise HTTPException(status_code=404, detail="商品不存在")
        try:
            await service.set_total(
                stock_date,
                product_id,
                total_qty,
                _admin_operator(authorization),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        updated_items = await service.list_for_date(stock_date)
        updated = next(
            (item for item in updated_items if item["product_id"] == product_id),
            None,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="商品不存在")
        return {"code": 0, "data": updated}

    return router


def _parse_stock_payload(
    payload: dict[str, Any],
    service: ProductDailyStockService,
) -> tuple[str, int]:
    """解析日期与总量参数，非法输入统一按 400 处理。"""
    stock_date = str(payload.get("date") or "").strip() or service.current_stock_date()
    raw_total = payload.get("totalQty")
    # 只接受真正的整数或纯数字字符串，避免 8.5 被 int() 静默截断。
    if isinstance(raw_total, bool):
        raise HTTPException(status_code=400, detail="每日库存总量必须是整数")
    if isinstance(raw_total, int):
        total_qty = raw_total
    elif isinstance(raw_total, str):
        normalized = raw_total.strip()
        if not normalized.isdigit():
            raise HTTPException(status_code=400, detail="每日库存总量必须是整数")
        try:
            total_qty = int(normalized)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail="每日库存总量必须是整数",
            ) from exc
    else:
        raise HTTPException(status_code=400, detail="每日库存总量必须是整数")
    if total_qty < 0:
        raise HTTPException(status_code=400, detail="每日库存总量不能为负数")
    return stock_date, total_qty
