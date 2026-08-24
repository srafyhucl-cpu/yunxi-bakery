"""优惠券管理后台 API 路由。"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.admin import verify_token
from app.service.coupon.admin import AdminCouponService


class TemplatePayload(BaseModel):
    """券模板请求体。"""

    name: str = ""
    couponType: str = ""
    thresholdFen: int = 0
    valueFen: int = 0
    discountBp: int = 0
    capFen: int = 0
    validFrom: str = ""
    validUntil: str = ""
    status: str = "active"


class StatusPayload(BaseModel):
    """模板启停请求体。"""

    status: str


class GrantPayload(BaseModel):
    """local 发券请求体。"""

    templateId: str
    mobile: str


def create_admin_coupons_router(service: AdminCouponService) -> APIRouter:
    """创建优惠券管理 API 路由。"""
    router = APIRouter(
        prefix="/api/v1/admin/coupons",
        tags=["admin-coupons"],
        dependencies=[Depends(verify_token)],
    )

    @router.get("/templates")
    async def list_templates(status: str = "") -> dict[str, Any]:
        return {"code": 0, "data": await service.list_templates(status=status)}

    @router.post("/templates")
    async def create_template(body: TemplatePayload) -> dict[str, Any]:
        try:
            return {"code": 0, "data": await service.create_template(body.model_dump())}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.put("/templates/{template_id}")
    async def update_template(
        template_id: str, body: TemplatePayload
    ) -> dict[str, Any]:
        try:
            return {
                "code": 0,
                "data": await service.update_template(template_id, body.model_dump()),
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.post("/templates/{template_id}/status")
    async def set_template_status(
        template_id: str, body: StatusPayload
    ) -> dict[str, Any]:
        try:
            return {
                "code": 0,
                "data": await service.set_template_status(template_id, body.status),
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/records")
    async def list_records(
        mobile: str = "", status: str = "", template_id: str = ""
    ) -> dict[str, Any]:
        return {
            "code": 0,
            "data": await service.list_records(
                mobile=mobile, status=status, template_id=template_id
            ),
        }

    @router.post("/grants")
    async def grant_coupon(body: GrantPayload) -> dict[str, Any]:
        try:
            return {
                "code": 0,
                "data": await service.grant_coupon(
                    template_id=body.templateId, mobile=body.mobile
                ),
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
