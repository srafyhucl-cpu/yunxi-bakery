"""店员快捷开单查询服务（仅查询，不创建订单、不扣储值）。"""

import json

from app.models.customer_master import CustomerIdentityType
from app.models.staff import StaffPrincipal
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.staff_repo import StaffAuditRepo, StaffRepo
from app.repository.youzan_order_repo import YouzanOrderRepo
from app.service.catalog.application import CatalogApplicationService
from app.service.staff_auth import STAFF_TENANT_ID, mask_phone

QUICK_ORDER_MEMBER_ORDER_LIMIT = 10
QUICK_ORDER_PRODUCT_DEFAULT_LIMIT = 20
QUICK_ORDER_PRODUCT_MAX_LIMIT = 50


class StaffQuickOrderService:
    """为店员快捷开单提供会员与商品查询读模型。"""

    def __init__(
        self,
        customer_repo: CustomerMasterRepo | None = None,
        member_balance_repo: MemberBalanceRepo | None = None,
        youzan_order_repo: YouzanOrderRepo | None = None,
        catalog_service: CatalogApplicationService | None = None,
        audit_repo: StaffRepo | StaffAuditRepo | None = None,
    ) -> None:
        # 启动期不读取数据库连接；未注入时由 db_session_scope 的 ContextVar 解析。
        self._customer_repo = customer_repo or CustomerMasterRepo(None)
        self._member_balance_repo = member_balance_repo or MemberBalanceRepo(None)
        self._youzan_order_repo = youzan_order_repo or YouzanOrderRepo(None)
        self._catalog_service = catalog_service
        self._audit_repo = audit_repo or StaffAuditRepo(None)

    async def lookup_member(
        self,
        phone: str,
        staff: StaffPrincipal,
    ) -> dict:
        """按手机号查询会员、储值拆分与最近有赞历史订单。"""
        clean_phone = self._normalize_phone(phone)
        phone_link = await self._customer_repo.get_identity_by_value(
            STAFF_TENANT_ID,
            CustomerIdentityType.PHONE.value,
            clean_phone,
        )
        customer = None
        if phone_link is not None:
            customer = await self._customer_repo.get_master(phone_link.customer_id)
        if customer is None:
            matches = await self._customer_repo.get_by_phone(
                STAFF_TENANT_ID, clean_phone
            )
            customer = matches[0] if matches else None
        if customer is None:
            raise ValueError("未找到该会员")

        openid = await self._resolve_miniapp_openid(customer.id)
        if not openid:
            raise ValueError("会员尚未绑定小程序")

        balance = await self._member_balance_repo.get_by_mobile(clean_phone) or {}
        stored_value_fen = int(balance.get("stored_value_fen", 0) or 0)
        principal_fen = int(balance.get("principal_fen", stored_value_fen) or 0)
        bonus_fen = int(balance.get("bonus_fen", 0) or 0)
        points = int(balance.get("points", 0) or 0)
        card_alias = str(balance.get("card_alias", "") or "")
        yz_open_id = str(balance.get("yz_open_id", "") or "").strip()

        order_rows = await self._youzan_order_repo.list_recent_for_identity(
            phone=clean_phone,
            yz_open_id=yz_open_id,
            limit=QUICK_ORDER_MEMBER_ORDER_LIMIT,
        )
        history_orders = [_format_history_order(row) for row in order_rows]

        await self._audit_repo.record_audit(
            staff.id,
            "lookup_member",
            target_type="customer",
            target_id=customer.id,
            detail_json=json.dumps(
                {"phone": mask_phone(clean_phone)}, ensure_ascii=False
            ),
        )
        return {
            "customerId": customer.id,
            "mobile": clean_phone,
            "userId": f"wx_{openid}",
            "displayName": str(
                customer.display_name or balance.get("display_name", "") or ""
            ),
            "isMember": bool(balance.get("is_member", 0)),
            "storedValueFen": stored_value_fen,
            "principalFen": principal_fen,
            "bonusFen": bonus_fen,
            "points": points,
            "cardAlias": card_alias,
            "historyOrders": history_orders,
        }

    async def list_products(
        self,
        keyword: str,
        limit: int = QUICK_ORDER_PRODUCT_DEFAULT_LIMIT,
        *,
        staff: StaffPrincipal,
    ) -> list[dict]:
        """按关键词返回快捷开单所需的最小商品字段。"""
        if self._catalog_service is None:
            raise ValueError("商品目录服务未就绪")
        normalized_keyword = str(keyword or "").strip()
        safe_limit = max(1, min(int(limit), QUICK_ORDER_PRODUCT_MAX_LIMIT))
        products = await self._catalog_service.list_products(
            keyword=normalized_keyword,
            limit=safe_limit,
        )
        items = [
            {
                "productId": str(product.get("id", "")),
                "title": str(product.get("title", "")),
                "priceFen": int(product.get("priceFen", 0) or 0),
                "stock": int(product.get("stock", 0) or 0),
                "isPurchasable": bool(product.get("isPurchasable", False)),
                "imageUrl": str(product.get("imageUrl", "") or ""),
            }
            for product in products
        ]
        await self._audit_repo.record_audit(
            staff.id,
            "list_products",
            target_type="catalog",
            target_id="",
            detail_json=json.dumps(
                {"keywordLength": len(normalized_keyword), "limit": safe_limit},
                ensure_ascii=False,
            ),
        )
        return items

    async def _resolve_miniapp_openid(self, customer_id: str) -> str:
        """从客户身份链接中取出已绑定的小程序 openid。"""
        links = await self._customer_repo.list_identity_links(customer_id)
        for link in links:
            if link.identity_type != CustomerIdentityType.MINIAPP_OPENID.value:
                continue
            value = str(link.identity_value or "").strip()
            if value:
                return value
        return ""

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        value = str(phone or "").strip()
        if len(value) != 11 or not value.isdigit() or not value.startswith("1"):
            raise ValueError("请输入有效的11位手机号")
        return value


def _format_history_order(row: dict) -> dict:
    """把有赞订单宽表行转换为店员可读的历史订单摘要。"""
    return {
        "orderNo": str(row.get("order_no", "") or ""),
        "status": str(row.get("status", "") or ""),
        "amountFen": int(row.get("amount_fen", 0) or 0),
        "productTitles": str(row.get("product_titles", "") or ""),
        "totalQuantity": int(row.get("total_quantity", 0) or 0),
        "payTime": str(row.get("pay_time", "") or ""),
        "createdAt": str(row.get("created_at", "") or ""),
    }


__all__ = ["StaffQuickOrderService"]
