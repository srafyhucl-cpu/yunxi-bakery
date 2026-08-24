"""前台积分 API 路由。"""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.channels.storefront._user import (
    authenticate_storefront_request,
    require_storefront_user_id,
)
from app.service.points import PointsService


def create_storefront_points_router(service: PointsService) -> APIRouter:
    """创建前台积分公开路由。"""
    router = APIRouter(
        prefix="/api/v1/miniapp",
        tags=["miniapp-points"],
        dependencies=[Depends(authenticate_storefront_request)],
    )

    @router.get("/points")
    async def get_points(
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        try:
            points = await service.get_points(
                require_storefront_user_id(x_miniapp_user_id),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": points}

    @router.post("/orders/{order_id}/points-preview")
    async def points_preview(
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

    @router.post("/orders/{order_id}/apply-points")
    async def apply_points(
        order_id: str,
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        try:
            applied = await service.apply_points(
                order_id,
                user_id=require_storefront_user_id(x_miniapp_user_id),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": applied}

    return router
