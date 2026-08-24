"""店铺运营配置服务。"""

import json

from app.models.config import DEFAULT_SHOP_OPERATIONS, SHOP_OPERATIONS_KEY
from app.repository.config_repo import ConfigRepo
from app.service.business_hours import parse_business_hours

DEFAULT_PAYMENT_MODE = "mock"


class ShopOperationsService:
    """统一读写小程序公开运营配置。"""

    def __init__(self, config_repo: ConfigRepo) -> None:
        self._config_repo = config_repo

    async def get_shop_operations(self) -> dict:
        """读取店铺公开运营配置。"""
        raw = await self._config_repo.get(SHOP_OPERATIONS_KEY)
        if not raw:
            return dict(DEFAULT_SHOP_OPERATIONS)
        try:
            saved = json.loads(raw)
        except json.JSONDecodeError:
            return dict(DEFAULT_SHOP_OPERATIONS)
        if not isinstance(saved, dict):
            return dict(DEFAULT_SHOP_OPERATIONS)
        return {**DEFAULT_SHOP_OPERATIONS, **saved}

    async def set_shop_operations(self, payload: dict) -> dict:
        """保存店铺公开运营配置。"""
        current = await self.get_shop_operations()
        business_hours = _clean_text(payload.get("businessHours"))
        if business_hours:
            parse_business_hours(business_hours)
        next_config = {
            **current,
            "shopName": _merge_text(current.get("shopName"), payload.get("shopName")),
            "customerWechat": _merge_text(
                current.get("customerWechat"), payload.get("customerWechat")
            ),
            "customerPhone": _merge_text(
                current.get("customerPhone"), payload.get("customerPhone")
            ),
            "businessHours": business_hours
            or _merge_text(current.get("businessHours"), ""),
            "pickupAddress": _merge_text(
                current.get("pickupAddress"), payload.get("pickupAddress")
            ),
            "deliveryNotice": _merge_text(
                current.get("deliveryNotice"), payload.get("deliveryNotice")
            ),
            "pickupNotice": _merge_text(
                current.get("pickupNotice"), payload.get("pickupNotice")
            ),
            "paymentMode": _merge_text(
                current.get("paymentMode"), payload.get("paymentMode")
            )
            or DEFAULT_PAYMENT_MODE,
            "privacyPolicyTitle": _merge_text(
                current.get("privacyPolicyTitle"), payload.get("privacyPolicyTitle")
            ),
            "privacyPolicyContent": _merge_text(
                current.get("privacyPolicyContent"), payload.get("privacyPolicyContent")
            ),
            "userAgreementTitle": _merge_text(
                current.get("userAgreementTitle"), payload.get("userAgreementTitle")
            ),
            "userAgreementContent": _merge_text(
                current.get("userAgreementContent"), payload.get("userAgreementContent")
            ),
            "afterSalesPolicyTitle": _merge_text(
                current.get("afterSalesPolicyTitle"),
                payload.get("afterSalesPolicyTitle"),
            ),
            "afterSalesPolicyContent": _merge_text(
                current.get("afterSalesPolicyContent"),
                payload.get("afterSalesPolicyContent"),
            ),
        }
        for key, default_value in DEFAULT_SHOP_OPERATIONS.items():
            if not next_config.get(key):
                next_config[key] = default_value
        await self._config_repo.set(
            SHOP_OPERATIONS_KEY,
            json.dumps(next_config, ensure_ascii=False),
        )
        return next_config


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _merge_text(current_value: object, next_value: object) -> str:
    cleaned = _clean_text(next_value)
    if cleaned:
        return cleaned
    return _clean_text(current_value)
