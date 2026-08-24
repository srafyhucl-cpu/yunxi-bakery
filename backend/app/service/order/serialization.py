"""订单序列化。"""

import json

from app.models.order import Order, OrderEvent
from app.utils import yuan_to_fen


class OrderSerializationService:
    """把订单模型转成前后端通用展示字典。"""

    def serialize(
        self, order: Order, *, events: list[OrderEvent] | None = None
    ) -> dict:
        products = self._loads_list(order.products)
        delivery = self._loads_dict(order.delivery)
        payment = self._loads_dict(getattr(order, "payment", "{}"))
        first_item = products[0] if products else {}
        status = (
            order.status.value if hasattr(order.status, "value") else str(order.status)
        )
        timeline = self._serialize_events(events or [], order=order, status=status)
        return {
            "id": order.id,
            "status": status,
            "totalFen": yuan_to_fen(order.total_amount),
            "createdAt": order.created_at,
            "updatedAt": order.updated_at,
            "itemTitle": str(first_item.get("title", "")),
            "itemCount": sum(int(item.get("quantity", 0) or 0) for item in products),
            "items": products,
            "receiverName": str(delivery.get("receiverName", "")),
            "receiverPhone": str(delivery.get("receiverPhone", "")),
            "deliveryType": str(delivery.get("deliveryType", "")),
            "deliveryAddress": str(delivery.get("deliveryAddress", "")),
            "expectTime": str(delivery.get("expectTime", "")),
            "remark": order.remark,
            "paymentStatus": str(payment.get("status", "unpaid")),
            "paymentMethod": str(payment.get("method", "")),
            "paymentPaidAt": str(payment.get("paidAt", "")),
            "paymentExpiredAt": str(payment.get("expiredAt", "")),
            "paymentExpiredReason": str(payment.get("expiredReason", "")),
            "timeline": timeline,
        }

    def _serialize_events(
        self,
        events: list[OrderEvent],
        *,
        order: Order,
        status: str,
    ) -> list[dict]:
        if events:
            return [
                {
                    "id": event.id,
                    "status": event.status,
                    "operator": event.operator,
                    "note": event.note,
                    "createdAt": event.created_at,
                }
                for event in events
            ]
        return [
            {
                "id": 0,
                "status": status,
                "operator": "system",
                "note": "订单当前状态",
                "createdAt": order.created_at or order.updated_at,
            }
        ]

    def _loads_list(self, raw: str) -> list[dict]:
        try:
            value = json.loads(raw or "[]")
        except json.JSONDecodeError:
            return []
        return value if isinstance(value, list) else []

    def _loads_dict(self, raw: str) -> dict:
        try:
            value = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}


__all__ = ["OrderSerializationService"]
