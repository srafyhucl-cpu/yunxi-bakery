"""小程序页面装修配置服务测试。"""

import aiosqlite
import pytest

from app.repository.config_repo import ConfigRepo
from app.service.shop_page_config import ShopPageConfigService


@pytest.fixture
def service(db: aiosqlite.Connection) -> ShopPageConfigService:
    """使用真实内存库仓储构建装修配置服务。"""
    return ShopPageConfigService(ConfigRepo(db))


def _home_config(title: str) -> dict:
    """构造一份可保存、可发布的首页装修配置。"""
    return {
        "pageId": "home",
        "version": 3,
        "theme": {
            "primaryColor": "#e94b4b",
            "accentColor": "#9bb879",
            "backgroundColor": "#fff8f2",
        },
        "blocks": [
            {
                "id": "home-notice",
                "type": "noticeBar",
                "enabled": True,
                "props": {"text": "后台装修草稿测试"},
            },
            {
                "id": "home-featured",
                "type": "productShelf",
                "enabled": True,
                "props": {
                    "title": title,
                    "subtitle": "后台保存后发布给小程序",
                    "source": "manual",
                    "productIds": ["p_001", "p_003"],
                },
            },
        ],
    }


def _shelf_title(page_config: dict) -> str:
    for block in page_config["blocks"]:
        if block["type"] == "productShelf":
            return block["props"]["title"]
    raise AssertionError("页面配置缺少商品货架模块")


def _member_summary_props(page_config: dict) -> dict:
    for block in page_config["blocks"]:
        if block["type"] == "memberSummary":
            return block["props"]
    raise AssertionError("页面配置缺少会员摘要模块")


async def test_draft_isolated_until_publish_and_miniapp_reads_published(
    service: ShopPageConfigService,
) -> None:
    """后台草稿保存不影响小程序，发布后小程序读取最新 published 配置。"""
    initial_published = await service.get_published_page("home")
    assert initial_published["status"] == "published"
    assert _shelf_title(initial_published) == "今日推荐"

    saved_draft = await service.save_draft("home", _home_config("端午新品预售"))
    assert saved_draft["status"] == "draft"
    assert _shelf_title(saved_draft) == "端午新品预售"

    miniapp_before_publish = await service.get_published_page("home")
    assert miniapp_before_publish["status"] == "published"
    assert _shelf_title(miniapp_before_publish) == "今日推荐"

    admin_page = await service.get_admin_page("home")
    assert _shelf_title(admin_page["draft"]) == "端午新品预售"
    assert _shelf_title(admin_page["published"]) == "今日推荐"

    published = await service.publish("home")
    assert published["status"] == "published"
    assert _shelf_title(published) == "端午新品预售"

    miniapp_after_publish = await service.get_published_page("home")
    assert miniapp_after_publish["status"] == "published"
    assert _shelf_title(miniapp_after_publish) == "端午新品预售"
    assert miniapp_after_publish["blocks"] == published["blocks"]


async def test_publish_without_draft_uses_default_page(
    service: ShopPageConfigService,
) -> None:
    """没有草稿时发布默认配置，保证后台初始化后小程序可直接渲染。"""
    published = await service.publish("products")

    assert published["pageId"] == "products"
    assert published["status"] == "published"
    assert published["version"] == 1
    assert published["theme"]["primaryColor"] == "#e94b4b"
    assert len(published["blocks"]) > 0

    admin_page = await service.get_admin_page("products")
    assert admin_page["draft"]["status"] == "published"
    assert admin_page["published"]["status"] == "published"
    assert admin_page["draft"]["blocks"] == admin_page["published"]["blocks"]


async def test_default_pages_match_each_miniapp_surface(
    service: ShopPageConfigService,
) -> None:
    """不同小程序页面初始化为各自的装修模块，避免后台切页后仍是首页模板。"""
    home = await service.get_published_page("home")
    products = await service.get_published_page("products")
    profile = await service.get_published_page("profile")

    assert [block["id"] for block in home["blocks"]] == [
        "home-search",
        "home-notice",
        "home-featured",
    ]
    assert [block["id"] for block in products["blocks"]] == [
        "products-search",
        "products-categories",
        "products-all",
    ]
    assert [block["id"] for block in profile["blocks"]] == [
        "profile-member",
        "profile-services",
        "profile-notices",
    ]
    service_items = next(
        block["props"]["items"]
        for block in profile["blocks"]
        if block["type"] == "serviceGrid"
    )
    assert any(item["linkTarget"] == "address" for item in service_items)
    member_props = _member_summary_props(profile)
    assert member_props["levelText"] == "普通会员"
    assert member_props["cardSubtitle"] == "单笔充值 1000 元升级"
    assert member_props["cardValidity"] == "永久有效"
    assert member_props["balanceFen"] == 0
    assert member_props["benefitCardCount"] == 0
    assert home["blocks"] != products["blocks"]
    assert products["blocks"] != profile["blocks"]
