"""后台打印队列与补打 API。"""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.api.admin import verify_token
from app.service.order.print_job_service import PrintJobService


def create_admin_print_jobs_router(service: PrintJobService) -> APIRouter:
    """创建后台打印队列路由。"""
    router = APIRouter(
        prefix="/api/v1/admin",
        tags=["admin-print-jobs"],
        dependencies=[Depends(verify_token)],
    )

    @router.get("/print-jobs")
    async def list_print_jobs(
        status: str = "",
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, Any]:
        try:
            items = await service.list_jobs(status=status, limit=limit)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"code": 0, "data": {"items": items}}

    @router.post("/print-jobs/process-pending")
    async def process_pending_print_jobs(
        limit: int = Query(default=20, ge=1, le=200),
    ) -> dict[str, Any]:
        """手动触发一轮待打印消费。"""
        return {"code": 0, "data": await service.process_pending(limit)}

    @router.post("/print-jobs/{job_id}/retry")
    async def retry_print_job(job_id: str) -> dict[str, Any]:
        result = await service.process_job(job_id)
        if result.get("status") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail=str(result.get("error", "")))
        if result.get("skipped"):
            raise HTTPException(
                status_code=400,
                detail=str(result.get("error", "打印作业已被领取或已结束")),
            )
        return {"code": 0, "data": result}

    @router.post("/print-jobs/{job_id}/mark-printed")
    async def mark_print_job_printed(job_id: str) -> dict[str, Any]:
        """人工确认真实出纸。"""
        try:
            updated = await service.mark_printed(job_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not updated:
            raise HTTPException(
                status_code=400, detail="打印作业不存在或状态不允许确认"
            )
        return {"code": 0, "data": {"jobId": job_id, "status": "PRINTED"}}

    @router.get("/orders/{order_id}/print-jobs")
    async def list_order_print_jobs(order_id: str) -> dict[str, Any]:
        items = await service.list_for_order(order_id)
        return {"code": 0, "data": {"items": items}}

    @router.post("/orders/{order_id}/print-jobs/{ticket_type}/reprint")
    async def reprint_order_ticket(
        order_id: str,
        ticket_type: str,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        try:
            result = await service.reprint(
                order_id,
                ticket_type,
                _admin_operator(authorization),
            )
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "不存在" in message else 400
            raise HTTPException(status_code=status_code, detail=message) from exc
        return {"code": 0, "data": result}

    return router


def _admin_operator(authorization: str | None) -> str:
    token = (authorization or "").replace("Bearer ", "", 1).strip()
    return f"admin:{token[:8]}" if token else "admin"
