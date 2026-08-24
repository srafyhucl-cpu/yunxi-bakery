from __future__ import annotations

import base64
import json
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.integrations.wecom_intelligent_bot import (
    create_wecom_intelligent_bot_router,
)
from app.config import settings
from app.service.wecom.crypto import (
    decrypt,
    encrypt,
    generate_signature,
    verify_signature,
)
from app.service.wecom.intelligent_bot_tools import WeComBotBusinessToolService


TOKEN = "callback-token"
AES_KEY = base64.b64encode(b"1" * 32).decode("utf-8").rstrip("=")
ACTOR_USER_ID = "synthetic-employee"
ACTOR_CHAT_ID = "synthetic-group"
ACTOR_CORP_ID = "synthetic-corp"


class _FakeCatalogService:
    async def list_products(self, *, featured: bool = False) -> list[dict]:
        return [
            {
                "id": "71001",
                "title": "草莓蛋糕",
                "priceFen": 26800,
                "stock": 6,
                "categoryName": "生日蛋糕",
                "soldText": "已售 12",
                "tags": ["生日蛋糕", "草莓"],
            }
        ]


class _FakeEmployeeAgentService:
    def __init__(self) -> None:
        self.allowed_tools: frozenset[str] | None = None

    async def answer(
        self,
        query: str,
        *,
        allowed_tools: frozenset[str] | None = None,
    ) -> str:
        self.allowed_tools = allowed_tools
        return f"agent:{query}"


def _client(monkeypatch, *, agent_service=None) -> TestClient:
    monkeypatch.setattr(settings, "WECOM_INTELLIGENT_BOT_TOKEN", TOKEN)
    monkeypatch.setattr(settings, "WECOM_INTELLIGENT_BOT_ENCODING_AES_KEY", AES_KEY)
    monkeypatch.setattr(settings, "WECOM_EMPLOYEE_AUTH_REQUIRED", True)
    monkeypatch.setattr(settings, "WECOM_EMPLOYEE_ALLOWED_USERS", ACTOR_USER_ID)
    monkeypatch.setattr(settings, "WECOM_EMPLOYEE_ALLOWED_CHATS", ACTOR_CHAT_ID)
    monkeypatch.setattr(settings, "WECOM_EMPLOYEE_CORP_ID", ACTOR_CORP_ID)
    app = FastAPI()
    app.include_router(
        create_wecom_intelligent_bot_router(
            tool_service=WeComBotBusinessToolService(
                catalog_service=_FakeCatalogService(),
            ),
            agent_service=agent_service,
        )
    )
    return TestClient(app)


def _signed_query(msg_encrypt: str, *, timestamp: str | None = None) -> dict[str, str]:
    timestamp = timestamp or str(int(time.time()))
    nonce = "nonce-1"
    return {
        "msg_signature": generate_signature(TOKEN, timestamp, nonce, msg_encrypt),
        "timestamp": timestamp,
        "nonce": nonce,
    }


def test_callback_get_returns_decrypted_echostr(monkeypatch) -> None:
    client = _client(monkeypatch)
    echostr = encrypt(AES_KEY, "ok", "")

    response = client.get(
        "/api/v1/wecom/intelligent-bot/callback",
        params={**_signed_query(echostr), "echostr": echostr},
    )

    assert response.status_code == 200
    assert response.text == "ok"


def test_callback_post_returns_encrypted_product_reply(monkeypatch) -> None:
    client = _client(monkeypatch)
    plaintext = json.dumps(
        {
            "msgid": "msg-001",
            "aibotid": "bot-001",
            "chattype": "group",
            "chatid": ACTOR_CHAT_ID,
            "corpid": ACTOR_CORP_ID,
            "from": {"userid": ACTOR_USER_ID},
            "msgtype": "text",
            "text": {"content": "@芸熙助手 草莓蛋糕还有库存吗"},
        },
        ensure_ascii=False,
    )
    msg_encrypt = encrypt(AES_KEY, plaintext, "")

    response = client.post(
        "/api/v1/wecom/intelligent-bot/callback",
        params=_signed_query(msg_encrypt),
        json={"encrypt": msg_encrypt},
    )

    assert response.status_code == 200
    payload = response.json()
    assert verify_signature(
        TOKEN,
        str(payload["timestamp"]),
        payload["nonce"],
        payload["encrypt"],
        payload["msgsignature"],
    )
    reply = json.loads(decrypt(AES_KEY, payload["encrypt"]))
    assert reply["msgtype"] == "stream"
    assert reply["stream"]["id"] == "msg-001"
    assert reply["stream"]["finish"] is True
    assert "草莓蛋糕" in reply["stream"]["content"]
    assert "库存 6" in reply["stream"]["content"]


def test_callback_post_uses_employee_agent_when_injected(monkeypatch) -> None:
    agent_service = _FakeEmployeeAgentService()
    client = _client(monkeypatch, agent_service=agent_service)
    plaintext = json.dumps(
        {
            "msgid": "msg-agent-001",
            "aibotid": "bot-001",
            "chattype": "group",
            "chatid": ACTOR_CHAT_ID,
            "corpid": ACTOR_CORP_ID,
            "from": {"userid": ACTOR_USER_ID},
            "msgtype": "text",
            "text": {"content": "今天一共多少订单"},
        },
        ensure_ascii=False,
    )
    msg_encrypt = encrypt(AES_KEY, plaintext, "")

    response = client.post(
        "/api/v1/wecom/intelligent-bot/callback",
        params=_signed_query(msg_encrypt),
        json={"encrypt": msg_encrypt},
    )

    assert response.status_code == 200
    payload = response.json()
    reply = json.loads(decrypt(AES_KEY, payload["encrypt"]))
    assert reply["stream"]["content"] == "agent:今天一共多少订单"
    assert agent_service.allowed_tools


def test_callback_post_rejects_invalid_signature(monkeypatch) -> None:
    client = _client(monkeypatch)
    msg_encrypt = encrypt(AES_KEY, '{"msgtype":"text","text":{"content":"test"}}', "")

    response = client.post(
        "/api/v1/wecom/intelligent-bot/callback",
        params={
            "msg_signature": "wrong-signature",
            "timestamp": "1783000000",
            "nonce": "nonce-1",
        },
        json={"encrypt": msg_encrypt},
    )

    assert response.status_code == 403


def test_invalid_signature_does_not_consume_nonce(monkeypatch) -> None:
    client = _client(monkeypatch)
    msg_encrypt = encrypt(AES_KEY, '{"msgtype":"event"}', "")
    timestamp = str(int(time.time()))
    nonce = "signature-retry-nonce"

    invalid = client.post(
        "/api/v1/wecom/intelligent-bot/callback",
        params={
            "msg_signature": "wrong-signature",
            "timestamp": timestamp,
            "nonce": nonce,
        },
        json={"encrypt": msg_encrypt},
    )
    valid = client.post(
        "/api/v1/wecom/intelligent-bot/callback",
        params={
            "msg_signature": generate_signature(TOKEN, timestamp, nonce, msg_encrypt),
            "timestamp": timestamp,
            "nonce": nonce,
        },
        json={"encrypt": msg_encrypt},
    )

    assert invalid.status_code == 403
    assert valid.status_code == 200


def test_callback_post_rejects_replayed_nonce(monkeypatch) -> None:
    """同一时间戳和 nonce 只能消费一次。"""
    monkeypatch.setattr(settings, "WECOM_INTELLIGENT_BOT_TOKEN", TOKEN)
    monkeypatch.setattr(settings, "WECOM_INTELLIGENT_BOT_ENCODING_AES_KEY", AES_KEY)
    timestamp = str(int(time.time()))
    nonce = "replay-nonce"
    encrypted = encrypt(AES_KEY, json.dumps({"msgtype": "event"}), "")
    signature = generate_signature(TOKEN, timestamp, nonce, encrypted)
    app = FastAPI()
    app.include_router(create_wecom_intelligent_bot_router())
    client = TestClient(app)
    params = {"msg_signature": signature, "timestamp": timestamp, "nonce": nonce}
    first = client.post(
        "/api/v1/wecom/intelligent-bot/callback",
        params=params,
        json={"encrypt": encrypted},
    )
    second = client.post(
        "/api/v1/wecom/intelligent-bot/callback",
        params=params,
        json={"encrypt": encrypted},
    )
    assert first.status_code != 403
    assert second.status_code == 403


def test_callback_post_rejects_stale_timestamp(monkeypatch) -> None:
    """过期回调必须在解密前拒绝。"""
    monkeypatch.setattr(settings, "WECOM_INTELLIGENT_BOT_TOKEN", TOKEN)
    monkeypatch.setattr(settings, "WECOM_INTELLIGENT_BOT_ENCODING_AES_KEY", AES_KEY)
    timestamp = str(int(time.time()) - settings.WECOM_CALLBACK_MAX_AGE_SECONDS - 1)
    nonce = "stale-nonce"
    encrypted = encrypt(AES_KEY, json.dumps({"msgtype": "event"}), "")
    signature = generate_signature(TOKEN, timestamp, nonce, encrypted)
    app = FastAPI()
    app.include_router(create_wecom_intelligent_bot_router())
    response = TestClient(app).post(
        "/api/v1/wecom/intelligent-bot/callback",
        params={"msg_signature": signature, "timestamp": timestamp, "nonce": nonce},
        json={"encrypt": encrypted},
    )
    assert response.status_code == 403
    assert response.text == "回调已超出允许时间窗"


def test_callback_returns_503_when_secret_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_INTELLIGENT_BOT_TOKEN", "")
    monkeypatch.setattr(settings, "WECOM_INTELLIGENT_BOT_ENCODING_AES_KEY", "")
    monkeypatch.setattr(settings, "WECOM_TOKEN", "")
    monkeypatch.setattr(settings, "WECOM_ENCODING_AES_KEY", "")
    app = FastAPI()
    app.include_router(create_wecom_intelligent_bot_router())
    client = TestClient(app)

    response = client.get(
        "/api/v1/wecom/intelligent-bot/callback",
        params={"msg_signature": "", "timestamp": "1", "nonce": "1", "echostr": "x"},
    )

    assert response.status_code == 503
