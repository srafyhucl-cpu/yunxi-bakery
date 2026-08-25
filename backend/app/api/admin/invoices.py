"""发票请求后台管理 API 路由。

依据 docs/specs/2026-08-25-invoice-mvp-plan.md：后台人工登记的三个最小端点
（登记 / 列表 / 标记已开）。电子发票直连、miniapp 入口、开票通知均不做。
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.admin import verify_token
from app.service.invoice.admin import AdminInvoiceService


class InvoiceCreatePayload(BaseModel):
    """发票登记请求体。"""

    orderNo: str | None = None
    customerName: str = ""
    companyTitle: str = ""
    taxNo: str = ""
    email: str = ""
    amountFen: int | None = None


class MarkIssuedPayload(BaseModel):
    """标记已开票请求体。"""

    issueNote: str = ""


def create_admin_invoices_router(service: AdminInvoiceService) -> APIRouter:
    """创建发票管理 API 路由。"""
    router = APIRouter(
        prefix="/api/v1/admin/invoices",
        tags=["admin-invoices"],
        dependencies=[Depends(verify_token)],
    )

    @router.post("")
    async def create_invoice(payload: InvoiceCreatePayload) -> dict[str, Any]:
        """登记一条发票请求。"""
        try:
            record = await service.create_invoice(payload.model_dump())
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": record}

    @router.get("")
    async def list_invoices(status: str = "") -> dict[str, Any]:
        """发票请求列表。"""
        records = await service.list_invoices(status=status)
        return {"code": 0, "data": records}

    @router.post("/{invoice_id}/mark-issued")
    async def mark_issued(
        invoice_id: int, payload: MarkIssuedPayload
    ) -> dict[str, Any]:
        """标记已开发票。"""
        try:
            record = await service.mark_issued(invoice_id, payload.issueNote)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"code": 0, "data": record}

    return router
