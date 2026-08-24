"""小程序页面装修配置服务。"""

import copy
import json
from datetime import datetime, timezone
from typing import Any

from app.models.config import SHOP_PAGE_DRAFT_PREFIX, SHOP_PAGE_PUBLISHED_PREFIX
from app.repository.config_repo import ConfigRepo

DEFAULT_PAGE_THEME: dict[str, str] = {
    "primaryColor": "#e94b4b",
    "accentColor": "#9bb879",
    "backgroundColor": "#f7f7f7",
}

DEFAULT_PAGE_CONFIGS: dict[str, dict[str, Any]] = {
    "home": {
        "pageId": "home",
        "version": 1,
        "status": "published",
        "updatedAt": "2026-06-16T00:00:00+08:00",
        "theme": DEFAULT_PAGE_THEME,
        "blocks": [
            {
                "id": "home-search",
                "type": "searchBar",
                "enabled": True,
                "props": {"placeholder": "搜索商品"},
            },
            {
                "id": "home-notice",
                "type": "noticeBar",
                "enabled": True,
                "props": {"text": "定制蛋糕 + 客服微信：13240240418"},
            },
            {
                "id": "home-featured",
                "type": "productShelf",
                "enabled": True,
                "props": {
                    "title": "今日推荐",
                    "subtitle": "按需预订，新鲜制作",
                    "source": "manual",
                    "productIds": ["p_001", "p_002"],
                },
            },
        ],
    },
    "products": {
        "pageId": "products",
        "version": 1,
        "status": "published",
        "updatedAt": "2026-06-16T00:00:00+08:00",
        "theme": DEFAULT_PAGE_THEME,
        "blocks": [
            {
                "id": "products-search",
                "type": "searchBar",
                "enabled": True,
                "props": {"placeholder": "搜索蛋糕、甜品、伴手礼"},
            },
            {
                "id": "products-categories",
                "type": "categoryGrid",
                "enabled": True,
                "props": {
                    "categoryIds": [
                        "birthday-cake",
                        "dessert",
                        "custom-cake",
                        "gift",
                    ],
                },
            },
            {
                "id": "products-all",
                "type": "productShelf",
                "enabled": True,
                "props": {
                    "title": "全部商品",
                    "subtitle": "可按需预订，库存以客服确认为准",
                    "source": "featured",
                    "productIds": [],
                },
            },
        ],
    },
    "profile": {
        "pageId": "profile",
        "version": 1,
        "status": "published",
        "updatedAt": "2026-06-16T00:00:00+08:00",
        "theme": DEFAULT_PAGE_THEME,
        "blocks": [
            {
                "id": "profile-member",
                "type": "memberSummary",
                "enabled": True,
                "props": {
                    "greeting": "欢迎来到芸熙烘焙",
                    "name": "微信用户",
                    "levelText": "普通会员",
                    "cardSubtitle": "单笔充值 1000 元升级",
                    "cardValidity": "永久有效",
                    "points": 0,
                    "coupons": 0,
                    "balanceFen": 0,
                    "benefitCardCount": 0,
                },
            },
            {
                "id": "profile-services",
                "type": "serviceGrid",
                "enabled": True,
                "props": {
                    "title": "常用服务",
                    "items": [
                        {
                            "id": "orders",
                            "title": "我的订单",
                            "iconText": "订单",
                            "linkType": "page",
                            "linkTarget": "orders",
                        },
                        {
                            "id": "chat",
                            "title": "联系客服",
                            "iconText": "客服",
                            "linkType": "contact",
                            "linkTarget": "chat",
                        },
                        {
                            "id": "address",
                            "title": "收货地址",
                            "iconText": "地址",
                            "linkType": "page",
                            "linkTarget": "address",
                        },
                    ],
                },
            },
            {
                "id": "profile-notices",
                "type": "noticeList",
                "enabled": True,
                "props": {
                    "items": [
                        {
                            "id": "pickup",
                            "title": "自提说明",
                            "actionText": "查看",
                            "linkType": "none",
                        },
                        {
                            "id": "custom",
                            "title": "定制蛋糕须知",
                            "actionText": "咨询",
                            "linkType": "contact",
                        },
                    ],
                },
            },
        ],
    },
}


class ShopPageConfigService:
    """管理小程序装修草稿和发布配置。"""

    def __init__(self, config_repo: ConfigRepo) -> None:
        self._config_repo = config_repo

    async def get_admin_page(self, page_id: str) -> dict[str, Any]:
        """读取后台所需的草稿与已发布配置。"""
        draft = await self._get_page(self._draft_key(page_id))
        published = await self.get_published_page(page_id)
        return {
            "pageId": page_id,
            "draft": draft or copy.deepcopy(published),
            "published": published,
        }

    async def save_draft(
        self, page_id: str, page_config: dict[str, Any]
    ) -> dict[str, Any]:
        """保存装修草稿。"""
        draft = self._normalize_page_config(page_id, page_config, "draft")
        await self._config_repo.set(
            self._draft_key(page_id),
            json.dumps(draft, ensure_ascii=False),
        )
        return draft

    async def publish(self, page_id: str) -> dict[str, Any]:
        """发布当前草稿；没有草稿时发布默认配置。"""
        draft = await self._get_page(self._draft_key(page_id))
        published = self._normalize_page_config(
            page_id,
            draft or self._default_page(page_id),
            "published",
        )
        raw = json.dumps(published, ensure_ascii=False)
        await self._config_repo.set(self._published_key(page_id), raw)
        await self._config_repo.set(self._draft_key(page_id), raw)
        return published

    async def get_published_page(self, page_id: str) -> dict[str, Any]:
        """读取小程序端已发布页面配置。"""
        page = await self._get_page(self._published_key(page_id))
        return page or self._default_page(page_id)

    async def _get_page(self, key: str) -> dict[str, Any] | None:
        raw = await self._config_repo.get(key)
        if not raw:
            return None
        try:
            page = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return page if isinstance(page, dict) else None

    def _normalize_page_config(
        self,
        page_id: str,
        page_config: dict[str, Any],
        status: str,
    ) -> dict[str, Any]:
        normalized = copy.deepcopy(page_config)
        normalized["pageId"] = page_id
        normalized["status"] = status
        normalized["updatedAt"] = datetime.now(timezone.utc).isoformat()
        normalized["version"] = int(normalized.get("version") or 1)
        normalized.setdefault("theme", self._default_page(page_id)["theme"])
        normalized.setdefault("blocks", [])
        return normalized

    def _default_page(self, page_id: str) -> dict[str, Any]:
        page = copy.deepcopy(
            DEFAULT_PAGE_CONFIGS.get(page_id, DEFAULT_PAGE_CONFIGS["home"])
        )
        page["pageId"] = page_id
        return page

    def _draft_key(self, page_id: str) -> str:
        return f"{SHOP_PAGE_DRAFT_PREFIX}{page_id}"

    def _published_key(self, page_id: str) -> str:
        return f"{SHOP_PAGE_PUBLISHED_PREFIX}{page_id}"
