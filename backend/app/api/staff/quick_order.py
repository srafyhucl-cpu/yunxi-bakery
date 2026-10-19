"""店员快捷开单查询 API（本阶段只读）。"""

from fastapi import APIRouter, Depends, HTTPException

from app.api.staff._auth import build_staff_dependency
from app.models.staff import StaffPrincipal
from app.service.staff_auth import StaffAuthService
from app.service.staff_quick_order import StaffQuickOrderService


def _member_lookup_error(exc: ValueError) -> HTTPException:
    """会员查询错误按“未找到 / 参数不合法”区分状态码。"""
    message = str(exc)
    status_code = 404 if message == "未找到该会员" else 400
    return HTTPException(status_code=status_code, detail=message)


def create_staff_quick_order_router(
    service: StaffQuickOrderService,
    auth_service: StaffAuthService,
) -> APIRouter:
    """创建店员快捷开单会员与商品查询路由。"""
    router = APIRouter(prefix="/api/v1/staff", tags=["staff-quick-order"])
    require_staff = build_staff_dependency(auth_service)

    @router.get("/quick-order/member-lookup")
    async def lookup_member(
        phone: str = "",
        principal: StaffPrincipal = Depends(require_staff),
    ) -> dict:
        try:
            data = await service.lookup_member(phone, principal)
        except ValueError as exc:
            raise _member_lookup_error(exc) from exc
        return {"ok": True, "data": data}

    @router.get("/quick-order/products")
    async def list_products(
        keyword: str = "",
        limit: int = 20,
        principal: StaffPrincipal = Depends(require_staff),
    ) -> dict:
        try:
            data = await service.list_products(
                keyword,
                limit,
                staff=principal,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "data": data}

    return router


__all__ = ["create_staff_quick_order_router"]
