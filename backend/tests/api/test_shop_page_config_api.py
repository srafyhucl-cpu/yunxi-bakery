"""小程序装修页面配置 API 测试。"""

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.api.admin_shop_pages import create_shop_page_config_router
from app.config import settings
from app.repository.config_repo import ConfigRepo
from app.service.shop_page_config import ShopPageConfigService


def _home_config(title: str) -> dict:
    """构造后台装修 API 可保存的首页配置。"""
    return {
        "pageId": "home",
        "version": 2,
        "theme": {
            "primaryColor": "#e94b4b",
            "accentColor": "#9bb879",
            "backgroundColor": "#fff8f2",
        },
        "blocks": [
            {
                "id": "home-featured",
                "type": "productShelf",
                "enabled": True,
                "props": {
                    "title": title,
                    "source": "manual",
                    "productIds": ["p_001", "p_002"],
                },
            },
        ],
    }


def _home_hero_config(image_urls: list[str]) -> dict:
    """构造包含多图轮播的首页配置。"""
    return {
        "pageId": "home",
        "version": 3,
        "theme": {
            "primaryColor": "#c9a56a",
            "accentColor": "#a97a41",
            "backgroundColor": "#f6efe7",
        },
        "blocks": [
            {
                "id": "home-hero",
                "type": "heroCarousel",
                "enabled": True,
                "props": {
                    "autoplay": True,
                    "intervalMs": 3500,
                    "items": [
                        {
                            "id": "hero-api-1",
                            "imageUrl": image_urls[0],
                            "title": "好利来参考主推",
                            "subtitle": "每日现制 / 手作奶油 / 礼赠场景",
                            "eyebrow": "YUNXI BAKE",
                            "badges": ["当日现做", "精选奶油", "生日礼赠"],
                            "linkType": "product",
                            "linkTarget": "p_001",
                        },
                        {
                            "id": "hero-api-2",
                            "imageUrl": image_urls[1],
                            "title": "节日限定宣传",
                            "subtitle": "适合生日、聚会和节日赠礼",
                            "eyebrow": "PROMOTION",
                            "badges": ["新品主推", "限时预订", "门店自提"],
                            "linkType": "none",
                            "linkTarget": "",
                        },
                    ],
                },
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
    }


def _shelf_title(page_config: dict) -> str:
    for block in page_config["blocks"]:
        if block["type"] == "productShelf":
            return block["props"]["title"]
    raise AssertionError("页面配置缺少商品货架模块")


def _hero_items(page_config: dict) -> list[dict]:
    for block in page_config["blocks"]:
        if block["type"] == "heroCarousel":
            return block["props"]["items"]
    raise AssertionError("页面配置缺少首页轮播模块")


def _member_summary_props(page_config: dict) -> dict:
    for block in page_config["blocks"]:
        if block["type"] == "memberSummary":
            return block["props"]
    raise AssertionError("页面配置缺少会员摘要模块")


@pytest.fixture
def app(db: aiosqlite.Connection) -> FastAPI:
    """构建只包含装修配置路由的测试应用。"""
    test_app = FastAPI()
    service = ShopPageConfigService(ConfigRepo(db))
    test_app.include_router(create_shop_page_config_router(service))
    return test_app


@pytest.mark.asyncio
async def test_admin_draft_publish_updates_miniapp_page(app: FastAPI) -> None:
    """后台保存草稿不影响小程序发布版，发布后小程序读取最新配置。"""
    headers = {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        miniapp_initial = await client.get("/api/v1/miniapp/pages/home")
        assert miniapp_initial.status_code == 200
        assert _shelf_title(miniapp_initial.json()["data"]) == "今日推荐"

        draft_response = await client.put(
            "/api/v1/admin/shop-config/pages/home/draft",
            json=_home_config("API 路由装修测试"),
            headers=headers,
        )
        assert draft_response.status_code == 200
        assert draft_response.json()["data"]["status"] == "draft"
        assert _shelf_title(draft_response.json()["data"]) == "API 路由装修测试"

        miniapp_after_draft = await client.get("/api/v1/miniapp/pages/home")
        assert miniapp_after_draft.status_code == 200
        assert _shelf_title(miniapp_after_draft.json()["data"]) == "今日推荐"

        admin_response = await client.get(
            "/api/v1/admin/shop-config/pages/home",
            headers=headers,
        )
        assert admin_response.status_code == 200
        assert (
            _shelf_title(admin_response.json()["data"]["draft"]) == "API 路由装修测试"
        )
        assert _shelf_title(admin_response.json()["data"]["published"]) == "今日推荐"

        publish_response = await client.post(
            "/api/v1/admin/shop-config/pages/home/publish",
            headers=headers,
        )
        assert publish_response.status_code == 200
        assert publish_response.json()["data"]["status"] == "published"
        assert _shelf_title(publish_response.json()["data"]) == "API 路由装修测试"

        miniapp_after_publish = await client.get("/api/v1/miniapp/pages/home")
        assert miniapp_after_publish.status_code == 200
        assert _shelf_title(miniapp_after_publish.json()["data"]) == "API 路由装修测试"


@pytest.mark.asyncio
async def test_admin_publishes_multi_image_hero_to_miniapp(app: FastAPI) -> None:
    """后台发布多图轮播后，小程序公开接口读取同一组宣传图。"""
    headers = {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}
    transport = httpx.ASGITransport(app=app)
    image_urls = [
        "/static/uploads/decoration/decoration-smoke-1.png",
        "/static/uploads/decoration/decoration-smoke-2.webp",
    ]

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        draft_response = await client.put(
            "/api/v1/admin/shop-config/pages/home/draft",
            json=_home_hero_config(image_urls),
            headers=headers,
        )
        assert draft_response.status_code == 200
        assert len(_hero_items(draft_response.json()["data"])) == 2

        publish_response = await client.post(
            "/api/v1/admin/shop-config/pages/home/publish",
            headers=headers,
        )
        assert publish_response.status_code == 200

        miniapp_response = await client.get("/api/v1/miniapp/pages/home")
        assert miniapp_response.status_code == 200

    hero_items = _hero_items(miniapp_response.json()["data"])
    assert [item["imageUrl"] for item in hero_items] == image_urls
    assert hero_items[0]["badges"] == ["当日现做", "精选奶油", "生日礼赠"]
    assert hero_items[1]["title"] == "节日限定宣传"


@pytest.mark.asyncio
async def test_admin_page_config_requires_token(app: FastAPI) -> None:
    """后台装修接口必须校验管理员 Token，小程序发布版接口公开可读。"""
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        admin_response = await client.get("/api/v1/admin/shop-config/pages/home")
        assert admin_response.status_code == 401

        miniapp_response = await client.get("/api/v1/miniapp/pages/home")
        assert miniapp_response.status_code == 200
        assert miniapp_response.json()["data"]["status"] == "published"


@pytest.mark.asyncio
async def test_admin_can_load_each_decoratable_page(app: FastAPI) -> None:
    """后台装修页可读取首页、商品页和我的页，供前端切换编辑。"""
    headers = {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        for page_id, first_block_id in [
            ("home", "home-search"),
            ("products", "products-search"),
            ("profile", "profile-member"),
        ]:
            response = await client.get(
                f"/api/v1/admin/shop-config/pages/{page_id}",
                headers=headers,
            )
            assert response.status_code == 200
            payload = response.json()["data"]
            assert payload["pageId"] == page_id
            assert payload["draft"]["pageId"] == page_id
            assert payload["published"]["pageId"] == page_id
            assert payload["draft"]["blocks"][0]["id"] == first_block_id

        profile_response = await client.get(
            "/api/v1/miniapp/pages/profile",
            headers=headers,
        )
        profile_member = _member_summary_props(profile_response.json()["data"])
        assert profile_member["cardSubtitle"] == "单笔充值 1000 元升级"
        assert profile_member["cardValidity"] == "永久有效"
        assert profile_member["balanceFen"] == 0
        assert profile_member["benefitCardCount"] == 0
        service_items = next(
            block["props"]["items"]
            for block in profile_response.json()["data"]["blocks"]
            if block["type"] == "serviceGrid"
        )
        assert any(item["linkTarget"] == "address" for item in service_items)
