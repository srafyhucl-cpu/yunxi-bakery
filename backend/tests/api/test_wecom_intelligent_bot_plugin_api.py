from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.integrations.wecom_intelligent_bot import (
    create_wecom_intelligent_bot_router,
)
from app.config import settings
from app.models.knowledge import KnowledgeCategory, KnowledgeEntry
from app.models.transfer import HumanTransfer
from app.service.wecom.intelligent_bot_ops_tools import WeComBotOpsToolService
from app.service.wecom.intelligent_bot_status_tools import WeComBotStatusToolService
from app.service.wecom.intelligent_bot_tools import WeComBotBusinessToolService


class _FakeOrderService:
    async def list_admin_orders(
        self,
        *,
        page: int = 1,
        keyword: str = "",
        status: str = "",
        board_filter: str = "",
    ) -> dict:
        return {
            "items": [
                {
                    "id": "ord_001",
                    "status": "pending",
                    "paymentStatus": "unpaid",
                    "itemTitle": "草莓蛋糕",
                    "itemCount": 1,
                    "totalFen": 26800,
                    "receiverName": "张三",
                    "receiverPhone": "13812345678",
                    "expectTime": "2026-07-03 18:00",
                    "createdAt": "2026-07-02 12:00:00",
                }
            ],
            "total": 1,
        }


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


class _FakeNoStockCatalogService:
    async def list_products(self, *, featured: bool = False) -> list[dict]:
        return [
            {
                "id": "71002",
                "title": "招牌牛奶吐司",
                "priceFen": 1500,
                "stock": 0,
                "categoryName": "甜品和面包",
                "soldText": "已售 8",
                "tags": ["吐司", "面包"],
            }
        ]


class _FakeKnowledgeRetriever:
    async def search(self, query: str, limit: int = 8) -> list[KnowledgeEntry]:
        return [
            KnowledgeEntry(
                id=1,
                category=KnowledgeCategory.FAQ,
                title="配送范围",
                content="当前配送范围以后台店铺运营配置为准，超出范围建议客服人工确认。",
            )
        ][:limit]


class _FakeCustomerAddressService:
    async def list_admin_addresses(
        self,
        *,
        page: int = 1,
        keyword: str = "",
    ) -> dict:
        return {
            "items": [
                {
                    "id": "addr_001",
                    "userId": "user_001",
                    "receiverName": "张三",
                    "receiverPhone": "13812345678",
                    "address": "测试路 1 号",
                    "isDefault": True,
                    "updatedAt": "2026-07-02 12:00:00",
                }
            ],
            "total": 1,
        }


class _FakeEmptyCustomerAddressService:
    def __init__(self) -> None:
        self.keywords: list[str] = []

    async def list_admin_addresses(
        self,
        *,
        page: int = 1,
        keyword: str = "",
    ) -> dict:
        self.keywords.append(keyword)
        return {"items": [], "total": 0}


class _FakeCustomerGroupService:
    async def get_campaign_summary(self, campaign_id: str) -> dict:
        return {
            "campaign": {"id": campaign_id, "title": "周六团购"},
            "totalRegistrations": 2,
            "totalQuantity": 3,
            "productTotals": [{"productName": "草莓蛋糕", "quantity": 3}],
            "pendingFollowups": [
                {
                    "id": "gr_001",
                    "userId": "wecom-user-001",
                    "customerName": "李四",
                    "customerPhone": "13912345678",
                    "productName": "草莓蛋糕",
                    "quantity": 1,
                    "fulfillmentMethod": "delivery",
                    "desiredTime": "2026-07-03",
                    "address": "隐私路 99 号",
                    "remark": "电话 13912345678，地址隐私路 99 号",
                    "status": "pending",
                }
            ],
            "summaryText": "周六团购登记汇总：\n1. 草莓蛋糕：3份",
        }


class _FakeMissingCustomerGroupService:
    async def get_campaign_summary(self, campaign_id: str) -> dict:
        raise ValueError("活动批次不存在")


class _FakeTransferManager:
    async def get_pending(self) -> list[HumanTransfer]:
        return [
            HumanTransfer(
                id="tr_001",
                session_id="sess_001",
                user_id="user_001",
                reason="客户要求人工确认配送",
                conversation_summary="客户 13812345678 问配送到隐私路 99 号的时间。",
                created_at="2026-07-02 12:00:00",
            )
        ]


class _FakeObservabilityService:
    async def get_summary(self) -> dict:
        return {
            "status": "attention",
            "counts": {
                "content_change_failures": 1,
                "webhook_failures": 2,
                "webhook_processing": 0,
                "slow_webhooks": 1,
            },
            "recent_failures": {"content_changes": [], "webhooks": []},
            "slow_webhooks": [],
        }

    async def get_webhooks(
        self,
        *,
        date_from: str = "",
        date_to: str = "",
        status: str = "",
        event_type: str = "",
        keyword: str = "",
        limit: int = 30,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        return (
            [
                {
                    "event_type": "ITEM_INFO",
                    "business_key": "71001",
                    "error_type": "RuntimeError",
                    "error_message": "同步失败，联系人 13812345678",
                    "details": {"receiverPhone": "13812345678"},
                }
            ],
            1,
        )


class _FakeOfflineReviewSummary:
    started_at = "2026-07-02 02:00:00"
    finished_at = "2026-07-02 02:05:00"
    ran = True
    skipped_reason = ""
    review_count = 2
    gap_count = 1
    profile_count = 3
    total_processed = 6


class _FakeSkippedOfflineReviewSummary:
    started_at = "2026-07-02 14:00:00"
    finished_at = "2026-07-02 14:00:01"
    ran = False
    skipped_reason = "outside_night_window"
    review_count = 0
    gap_count = 0
    profile_count = 0
    total_processed = 0


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(create_wecom_intelligent_bot_router())
    return TestClient(app)


def _business_client(
    offline_summary_provider: Callable[[], Any] | None = None,
    customer_address_service: Any | None = None,
    customer_group_service: Any | None = None,
    catalog_service: Any | None = None,
) -> TestClient:
    provider = offline_summary_provider or (lambda: _FakeOfflineReviewSummary())
    app = FastAPI()
    app.include_router(
        create_wecom_intelligent_bot_router(
            tool_service=WeComBotBusinessToolService(
                order_service=_FakeOrderService(),
                catalog_service=catalog_service or _FakeCatalogService(),
                knowledge_retriever=_FakeKnowledgeRetriever(),
            ),
            ops_tool_service=WeComBotOpsToolService(
                customer_address_service=(
                    customer_address_service or _FakeCustomerAddressService()
                ),
                customer_group_service=(
                    customer_group_service or _FakeCustomerGroupService()
                ),
                transfer_mgr=_FakeTransferManager(),
            ),
            status_tool_service=WeComBotStatusToolService(
                observability_service=_FakeObservabilityService(),
                offline_summary_provider=provider,
            ),
        )
    )
    return TestClient(app)


def _serialized(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def test_ping_rejects_when_plugin_key_unconfigured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_BOT_PLUGIN_API_KEY", "")

    response = _client().post(
        "/api/v1/wecom/intelligent-bot/plugins/ping",
        headers={"X-Yunxi-Bot-Key": "secret"},
        json={"text": "测试"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "企微机器人插件密钥未配置"


def test_ping_rejects_invalid_plugin_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_BOT_PLUGIN_API_KEY", "expected-secret")

    response = _client().post(
        "/api/v1/wecom/intelligent-bot/plugins/ping",
        headers={"X-Yunxi-Bot-Key": "wrong-secret"},
        json={"text": "测试"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "企微机器人插件密钥无效"


def test_ping_returns_plugin_status_for_valid_header_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_BOT_PLUGIN_API_KEY", "expected-secret")

    response = _client().post(
        "/api/v1/wecom/intelligent-bot/plugins/ping",
        headers={"X-Yunxi-Bot-Key": "expected-secret"},
        json={"text": "帮我查一下插件状态"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "plugin": "yunxi_employee_assistant_ping",
        "message": "芸熙员工助理插件已接通",
        "receivedText": "帮我查一下插件状态",
        "suggestedReply": "已收到：帮我查一下插件状态",
        "result": "已收到：帮我查一下插件状态",
        "resultText": "已收到：帮我查一下插件状态",
        "nextAction": "下一步可接入查订单、查客户、知识库问答等业务 skill。",
        "version": response.json()["version"],
    }


def test_ping_accepts_bearer_token(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_BOT_PLUGIN_API_KEY", "expected-secret")

    response = _client().get(
        "/api/v1/wecom/intelligent-bot/plugins/ping",
        headers={"Authorization": "Bearer expected-secret"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "芸熙员工助理插件已接通"


def test_query_parameter_key_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_BOT_PLUGIN_API_KEY", "expected-secret")

    response = _client().get(
        "/api/v1/wecom/intelligent-bot/plugins/ping?api_key=expected-secret"
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "企微机器人插件密钥无效"


def test_order_lookup_returns_compact_order_for_valid_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_BOT_PLUGIN_API_KEY", "expected-secret")

    response = _business_client().post(
        "/api/v1/wecom/intelligent-bot/tools/order-lookup",
        headers={"X-Yunxi-Bot-Key": "expected-secret"},
        json={"query": "张三"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["tool"] == "order_lookup"
    assert payload["orders"][0]["id"] == "ord_001"
    assert payload["orders"][0]["receiverPhoneMasked"] == "138****5678"
    assert "ord_001" in payload["ordersText"]


def test_product_lookup_returns_stock_for_valid_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_BOT_PLUGIN_API_KEY", "expected-secret")

    response = _business_client().post(
        "/api/v1/wecom/intelligent-bot/tools/product-lookup",
        headers={"X-Yunxi-Bot-Key": "expected-secret"},
        json={"query": "草莓蛋糕"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["tool"] == "product_lookup"
    assert payload["products"][0]["title"] == "草莓蛋糕"
    assert payload["products"][0]["stock"] == 6
    assert "库存 6" in payload["productsText"]
    assert "低库存" not in payload["nextAction"]
    assert "库存和价格以小程序商品数据为准" in payload["nextAction"]


def test_product_lookup_no_stock_is_actionable(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_BOT_PLUGIN_API_KEY", "expected-secret")

    response = _business_client(catalog_service=_FakeNoStockCatalogService()).post(
        "/api/v1/wecom/intelligent-bot/tools/product-lookup",
        headers={"X-Yunxi-Bot-Key": "expected-secret"},
        json={"query": "招牌牛奶吐司"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["products"][0]["stock"] == 0
    assert "库存 0" in payload["productsText"]
    assert "暂无可售库存" in payload["nextAction"]
    assert "不要承诺有货" in payload["nextAction"]


def test_product_lookup_miss_is_not_stockout(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_BOT_PLUGIN_API_KEY", "expected-secret")

    response = _business_client().post(
        "/api/v1/wecom/intelligent-bot/tools/product-lookup",
        headers={"X-Yunxi-Bot-Key": "expected-secret"},
        json={"query": "不存在的月球蛋糕"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["products"] == []
    assert "未找到匹配商品" in payload["productsText"]
    assert "未命中结果" in payload["nextAction"]
    assert "缺货结论" in payload["nextAction"]


def test_knowledge_answer_returns_sources_for_valid_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_BOT_PLUGIN_API_KEY", "expected-secret")

    response = _business_client().post(
        "/api/v1/wecom/intelligent-bot/tools/knowledge-answer",
        headers={"X-Yunxi-Bot-Key": "expected-secret"},
        json={"question": "配送范围怎么说"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["tool"] == "knowledge_answer"
    assert payload["sources"][0]["title"] == "配送范围"
    assert "配送范围" in payload["answer"]


def test_business_tool_rejects_invalid_plugin_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_BOT_PLUGIN_API_KEY", "expected-secret")

    response = _business_client().post(
        "/api/v1/wecom/intelligent-bot/tools/order-lookup",
        headers={"X-Yunxi-Bot-Key": "wrong-secret"},
        json={"query": "张三"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "企微机器人插件密钥无效"


def test_business_tool_rejects_query_parameter_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_BOT_PLUGIN_API_KEY", "expected-secret")

    response = _business_client().post(
        "/api/v1/wecom/intelligent-bot/tools/order-lookup?api_key=expected-secret",
        json={"query": "张三"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "企微机器人插件密钥无效"


def test_customer_lookup_returns_address_leads(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_BOT_PLUGIN_API_KEY", "expected-secret")

    response = _business_client().post(
        "/api/v1/wecom/intelligent-bot/tools/customer-lookup",
        headers={"X-Yunxi-Bot-Key": "expected-secret"},
        json={"query": "张三"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["tool"] == "customer_lookup"
    assert payload["addresses"][0]["receiverName"] == "张三"
    assert payload["addresses"][0]["receiverPhoneMasked"] == "138****5678"
    assert payload["addresses"][0]["addressPreview"] == "测试路1..."
    serialized = _serialized(payload)
    assert "13812345678" not in serialized
    assert "测试路 1 号" not in serialized
    assert "user_001" not in serialized


def test_customer_lookup_empty_result_is_actionable(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_BOT_PLUGIN_API_KEY", "expected-secret")
    customer_address_service = _FakeEmptyCustomerAddressService()

    response = _business_client(
        customer_address_service=customer_address_service,
    ).post(
        "/api/v1/wecom/intelligent-bot/tools/customer-lookup",
        headers={"X-Yunxi-Bot-Key": "expected-secret"},
        json={"query": "张三"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["addresses"] == []
    assert customer_address_service.keywords == ["张三"]
    assert "没找到“张三”的客户地址线索" in payload["result"]
    assert "请换客户姓名或地址关键词再查" in payload["nextAction"]
    serialized = _serialized(payload)
    assert "未找到匹配客户地址" not in serialized
    assert "手机号" not in serialized
    assert "订单尾号" not in serialized


def test_customer_lookup_empty_result_masks_sensitive_query(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_BOT_PLUGIN_API_KEY", "expected-secret")
    customer_address_service = _FakeEmptyCustomerAddressService()

    response = _business_client(
        customer_address_service=customer_address_service,
    ).post(
        "/api/v1/wecom/intelligent-bot/tools/customer-lookup",
        headers={"X-Yunxi-Bot-Key": "expected-secret"},
        json={"query": "查一下13812345678地址线索"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert customer_address_service.keywords == ["13812345678"]
    assert "138****5678" in payload["result"]
    serialized = _serialized(payload)
    assert "13812345678" not in serialized
    assert "手机号" not in serialized


def test_group_campaign_summary_returns_summary_text(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_BOT_PLUGIN_API_KEY", "expected-secret")

    response = _business_client().post(
        "/api/v1/wecom/intelligent-bot/tools/group-campaign-summary",
        headers={"X-Yunxi-Bot-Key": "expected-secret"},
        json={"campaignId": "gcp_001"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["tool"] == "group_campaign_summary"
    assert payload["campaign"]["id"] == "gcp_001"
    assert "草莓蛋糕：3份" in payload["summaryText"]
    assert payload["pendingFollowups"][0]["customerPhoneMasked"] == "139****5678"
    assert payload["pendingFollowups"][0]["addressPreview"] == "隐私路9..."
    serialized = _serialized(payload)
    assert "13912345678" not in serialized
    assert "隐私路 99 号" not in serialized
    assert "wecom-user-001" not in serialized


def test_group_campaign_missing_result_is_actionable(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_BOT_PLUGIN_API_KEY", "expected-secret")

    response = _business_client(
        customer_group_service=_FakeMissingCustomerGroupService(),
    ).post(
        "/api/v1/wecom/intelligent-bot/tools/group-campaign-summary",
        headers={"X-Yunxi-Bot-Key": "expected-secret"},
        json={"campaignId": "abc123"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["campaign"] == {}
    assert payload["productTotals"] == []
    assert payload["pendingFollowups"] == []
    assert "未找到客户群活动批次 campaignId:abc123" in payload["result"]
    assert "请确认 campaignId 是否复制完整" in payload["nextAction"]
    serialized = _serialized(payload)
    assert "请稍后重试" not in serialized
    assert "活动批次不存在" not in serialized
    assert "手机号" not in serialized


def test_handoff_pending_returns_pending_transfers(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_BOT_PLUGIN_API_KEY", "expected-secret")

    response = _business_client().post(
        "/api/v1/wecom/intelligent-bot/tools/handoff-pending",
        headers={"X-Yunxi-Bot-Key": "expected-secret"},
        json={},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["tool"] == "handoff_pending"
    assert payload["transfers"][0]["id"] == "tr_001"
    assert "客户要求人工确认配送" in payload["transfersText"]
    assert "摘要：" in payload["transfersText"]
    serialized = _serialized(payload)
    assert "13812345678" not in serialized
    assert "隐私路 99 号" not in serialized
    assert "conversationSummary" not in serialized


def test_ops_summary_returns_observability_counts(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_BOT_PLUGIN_API_KEY", "expected-secret")

    response = _business_client().post(
        "/api/v1/wecom/intelligent-bot/tools/ops-summary",
        headers={"X-Yunxi-Bot-Key": "expected-secret"},
        json={},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["tool"] == "ops_summary"
    assert payload["status"] == "attention"
    assert payload["counts"]["webhook_failures"] == 2
    assert "系统需要关注" in payload["result"]
    assert "Webhook 失败 2 条" in payload["result"]
    assert "先看 Webhook 失败记录" in payload["result"]
    assert "status=attention" not in payload["result"]
    assert "status=attention" not in payload["nextAction"]
    assert "recentFailures" not in payload
    assert "slowWebhooks" not in payload


def test_integration_status_returns_failed_webhooks(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_BOT_PLUGIN_API_KEY", "expected-secret")

    response = _business_client().post(
        "/api/v1/wecom/intelligent-bot/tools/integration-status",
        headers={"X-Yunxi-Bot-Key": "expected-secret"},
        json={"query": "71001"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["tool"] == "integration_status"
    assert payload["webhooks"][0]["businessKey"] == "71001"
    assert "同步失败" in payload["webhooksText"]
    serialized = _serialized(payload)
    assert "13812345678" not in serialized
    assert "details" not in serialized
    assert "error_message" not in serialized


def test_offline_review_summary_returns_latest_run(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_BOT_PLUGIN_API_KEY", "expected-secret")

    response = _business_client().post(
        "/api/v1/wecom/intelligent-bot/tools/offline-review-summary",
        headers={"X-Yunxi-Bot-Key": "expected-secret"},
        json={},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["tool"] == "offline_review_summary"
    assert payload["ran"] is True
    assert payload["totalProcessed"] == 6
    assert "skippedReason" not in payload["nextAction"]


def test_offline_review_summary_hides_raw_skipped_reason(monkeypatch) -> None:
    monkeypatch.setattr(settings, "WECOM_BOT_PLUGIN_API_KEY", "expected-secret")

    response = _business_client(
        offline_summary_provider=lambda: _FakeSkippedOfflineReviewSummary(),
    ).post(
        "/api/v1/wecom/intelligent-bot/tools/offline-review-summary",
        headers={"X-Yunxi-Bot-Key": "expected-secret"},
        json={},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["ran"] is False
    assert payload["skippedReason"] == "outside_night_window"
    assert "当前不在夜间复盘窗口" in payload["result"]
    assert "如需立即复盘" in payload["nextAction"]
    assert "outside_night_window" not in payload["result"]
    assert "outside_night_window" not in payload["nextAction"]
    assert "skippedReason" not in payload["result"]
    assert "skippedReason" not in payload["nextAction"]
