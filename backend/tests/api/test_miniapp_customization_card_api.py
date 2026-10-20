"""小程序定制需求卡 API 测试。"""

from datetime import datetime, timedelta
from typing import Any

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.api.channels.storefront.chat import create_storefront_chat_router
from app.service.customization_card import CustomizationCardService
from app.service.order.fulfillment_dual_track import BEIJING_TIME_ZONE
from tests.helpers.storefront_auth import storefront_auth_headers

FIXED_NOW = datetime(2026, 6, 17, 12, 0, tzinfo=BEIJING_TIME_ZONE)
CARD_PATH = "/api/v1/miniapp/chat/customization-card"


class _FakeConversationService:
    """客服会话服务占位：定制卡接口不依赖会话能力。"""


@pytest.fixture
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(
        create_storefront_chat_router(
            _FakeConversationService(),
            CustomizationCardService(now_provider=lambda: FIXED_NOW),
        )
    )
    return test_app


def _payload(**overrides: str) -> dict[str, str]:
    payload = {
        "size": "8寸",
        "filling": "芒果慕斯",
        "greeting": "生日快乐",
        "accessories": "蜡烛、餐具",
    }
    payload.update(overrides)
    return payload


async def _count_orders(db: aiosqlite.Connection) -> int:
    rows = await db.execute_fetchall("SELECT COUNT(*) FROM orders")
    return int(rows[0][0])


async def _post(app: FastAPI, body: dict[str, Any], user_id: str = "wx_user_001"):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        return await client.post(
            CARD_PATH,
            json=body,
            headers=storefront_auth_headers(user_id),
        )


async def test_customization_card_requires_login(app: FastAPI) -> None:
    """未登录时不得生成需求卡。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(CARD_PATH, json=_payload())

    assert response.status_code == 401


async def test_customization_card_returns_structured_card(app: FastAPI) -> None:
    """登录顾客可拿到结构化需求卡。"""
    response = await _post(
        app, _payload(sweetness="5分", expectTime="2026-06-18 10:00")
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    card = body["data"]
    assert card["size"] == "8寸"
    assert card["filling"] == "芒果慕斯"
    assert card["sweetness"] == "5分甜"
    assert card["greeting"] == "生日快乐"
    assert card["accessories"] == "蜡烛、餐具"
    assert card["expectTime"] == "2026-06-18 10:00"
    assert "尺寸：8寸" in card["summary"]


async def test_customization_card_rejects_missing_field(app: FastAPI) -> None:
    """缺必填项时返回 400 与中文提示。"""
    payload = _payload()
    payload.pop("filling")

    response = await _post(app, payload)

    assert response.status_code == 400
    assert "夹心口味" in response.json()["detail"]


async def test_customization_card_rejects_expect_time_within_four_hours(
    app: FastAPI,
) -> None:
    """预约时间不足四小时时返回 400。"""
    expect_time = (FIXED_NOW + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")

    response = await _post(app, _payload(expectTime=expect_time))

    assert response.status_code == 400
    assert "提前" in response.json()["detail"]


async def test_customization_card_does_not_create_orders(
    app: FastAPI,
    db: aiosqlite.Connection,
) -> None:
    """生成需求卡不建单、不写库。"""
    before = await _count_orders(db)

    response = await _post(app, _payload(expectTime="2026-06-18 10:00"))

    assert response.status_code == 200
    assert before == 0
    assert await _count_orders(db) == 0
