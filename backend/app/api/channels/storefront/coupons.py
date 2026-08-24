"""前台优惠券 API 路由。"""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.api.channels.storefront._user import (
    authenticate_storefront_request,
    require_storefront_user_id,
)
from app.service.coupon import CouponService


class ApplyCouponRequest(BaseModel):
    """应用券请求体。"""

    couponId: str


def create_storefront_coupons_router(service: CouponService) -> APIRouter:
    """创建前台优惠券公开路由。"""
    router = APIRouter(
        prefix="/api/v1/miniapp",
        tags=["miniapp-coupons"],
        dependencies=[Depends(authenticate_storefront_request)],
    )

    @router.get("/coupons")
    async def get_coupons(
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        try:
            data = await service.get_my_coupons(
                require_storefront_user_id(x_miniapp_user_id),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": data}

    @router.post("/orders/{order_id}/coupon-preview")
    async def coupon_preview(
        order_id: str,
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        try:
            preview = await service.redeem_preview(
                order_id,
                user_id=require_storefront_user_id(x_miniapp_user_id),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": preview}

    @router.post("/orders/{order_id}/apply-coupon")
    async def apply_coupon(
        order_id: str,
        body: ApplyCouponRequest,
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        try:
            applied = await service.apply_coupon(
                order_id,
                user_id=require_storefront_user_id(x_miniapp_user_id),
                coupon_id=body.couponId,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": applied}

    return router
