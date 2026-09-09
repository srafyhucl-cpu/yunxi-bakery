"""前台配送报价 API。"""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.channels.storefront._user import (
    authenticate_storefront_request,
    require_storefront_user_id,
)
from app.models.delivery import FulfillmentMethod
from app.service.delivery.application import DeliveryApplicationService
from app.service.delivery.provider import (
    DeliveryQuoteItem,
    DeliveryQuoteRequest,
    normalize_delivery_quote_items,
)


def create_storefront_delivery_router(
    service: DeliveryApplicationService,
) -> APIRouter:
    """创建小程序配送报价路由。"""
    router = APIRouter(
        prefix="/api/v1/miniapp/delivery",
        tags=["miniapp-delivery"],
        dependencies=[Depends(authenticate_storefront_request)],
    )

    @router.post("/quotes")
    async def create_quote(
        payload: dict[str, Any],
        x_miniapp_user_id: str | None = Header(default=None, alias="x-miniapp-user-id"),
    ) -> dict[str, Any]:
        user_id = require_storefront_user_id(x_miniapp_user_id)
        try:
            fulfillment_method = FulfillmentMethod(
                str(payload.get("fulfillmentMethod", ""))
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="不支持的履约方式") from exc

        if fulfillment_method is FulfillmentMethod.PICKUP:
            return {
                "code": 0,
                "data": {
                    "status": "not_applicable",
                    "deliveryFeeFen": 0,
                    "message": "门店自取不产生闪送费",
                },
            }

        required_fields = (
            "requestId",
            "pickupAddress",
            "receiverName",
            "receiverPhone",
            "receiverAddress",
            "expectTime",
        )
        missing = [
            field
            for field in required_fields
            if not str(payload.get(field, "")).strip()
        ]
        if missing:
            raise HTTPException(status_code=400, detail="配送报价信息不完整")

        try:
            items = normalize_delivery_quote_items(
                DeliveryQuoteItem(
                    product_id=str(item.get("productId", "")),
                    quantity=int(item.get("quantity", 0)),
                )
                for item in payload.get("items", [])
                if isinstance(item, dict)
            )
            quote = await service.quote(
                DeliveryQuoteRequest(
                    request_id=str(payload["requestId"]),
                    user_id=user_id,
                    pickup_address=str(payload["pickupAddress"]),
                    receiver_name=str(payload["receiverName"]),
                    receiver_phone=str(payload["receiverPhone"]),
                    receiver_address=str(payload["receiverAddress"]),
                    expect_time=str(payload["expectTime"]),
                    item_count=sum(item.quantity for item in items),
                    goods_total_fen=max(0, int(payload.get("goodsTotalFen", 0))),
                    items=items,
                )
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="配送报价参数无效") from exc

        return {
            "code": 0,
            "data": {
                "quoteId": quote.quote_id,
                "status": quote.status.value,
                "deliveryFeeFen": quote.delivery_fee_fen,
                "quoteTotalFen": quote.quote_total_fen,
                "expiresAt": quote.expires_at,
                "message": quote.message,
            },
        }

    return router
