"""数据观察台后台路由。"""

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.admin import verify_token
from app.service.observability import ObservabilityService

PAGE_SIZE = 30


def create_observability_router(service: ObservabilityService) -> APIRouter:
    """创建数据观察台路由。"""
    root_router = APIRouter()
    api_router = _create_api_router()
    _register_summary_route(api_router, service)
    _register_current_route(api_router, service)
    _register_history_routes(api_router, service)
    _register_webhook_routes(api_router, service)
    root_router.include_router(api_router)
    return root_router


def _create_api_router() -> APIRouter:
    return APIRouter(
        prefix="/api/v1/admin/observability",
        tags=["admin-observability-api"],
        dependencies=[Depends(verify_token)],
    )


def _register_summary_route(
    api_router: APIRouter,
    service: ObservabilityService,
) -> None:

    @api_router.get("/summary")
    async def summary_api(
        authorization: str | None = Header(default=None),
    ) -> dict:
        summary = await service.get_summary()
        return {"code": 0, "data": summary}


def _register_current_route(
    api_router: APIRouter,
    service: ObservabilityService,
) -> None:

    @api_router.get("/current")
    async def current_api(
        authorization: str | None = Header(default=None),
        page: int = 1,
        view: str = "all",
        category: str = "",
        keyword: str = "",
        product_status: str = "",
    ) -> dict:

        limit = PAGE_SIZE
        offset = (page - 1) * limit
        items, total = await service.list_current_content(
            view=view,
            category=category,
            keyword=keyword,
            product_status=product_status,
            limit=limit,
            offset=offset,
        )
        return {"code": 0, "total": total, "data": items}


def _register_history_routes(
    api_router: APIRouter,
    service: ObservabilityService,
) -> None:

    @api_router.get("/history")
    async def history_api(
        authorization: str | None = Header(default=None),
        page: int = 1,
        date_from: str = "",
        date_to: str = "",
        source: str = "",
        status: str = "",
        entity_type: str = "",
        keyword: str = "",
    ) -> dict:

        limit = PAGE_SIZE
        offset = (page - 1) * limit
        items, total = await service.get_history(
            date_from=date_from,
            date_to=date_to,
            source=source,
            status=status,
            entity_type=entity_type,
            keyword=keyword,
            limit=limit,
            offset=offset,
        )
        return {"code": 0, "total": total, "data": items}

    @api_router.get("/history/{entry_id}")
    async def history_detail_api(
        entry_id: int,
        authorization: str | None = Header(default=None),
    ) -> dict:

        entry = await service.get_history_detail(entry_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Not Found")
        return {"code": 0, "data": entry}


def _register_webhook_routes(
    api_router: APIRouter,
    service: ObservabilityService,
) -> None:

    @api_router.get("/webhooks")
    async def webhooks_api(
        authorization: str | None = Header(default=None),
        page: int = 1,
        date_from: str = "",
        date_to: str = "",
        status: str = "",
        event_type: str = "",
        keyword: str = "",
    ) -> dict:

        limit = PAGE_SIZE
        offset = (page - 1) * limit
        items, total = await service.get_webhooks(
            date_from=date_from,
            date_to=date_to,
            status=status,
            event_type=event_type,
            keyword=keyword,
            limit=limit,
            offset=offset,
        )
        return {"code": 0, "total": total, "data": items}

    @api_router.get("/webhooks/{event_id}")
    async def webhook_detail_api(
        event_id: int,
        authorization: str | None = Header(default=None),
    ) -> dict:

        entry = await service.get_webhook_detail(event_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Not Found")
        return {"code": 0, "data": entry}
