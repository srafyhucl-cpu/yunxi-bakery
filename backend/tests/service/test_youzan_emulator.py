"""有赞 Webhook/API 异步仿真器单元测试。"""

import pytest

from app.config import settings
from app.service.youzan.client import YouzanClient
from app.service.youzan.mock_emulator import YouzanMockEmulator
from app.service.youzan.webhook import verify_signature


def test_youzan_webhook_emulator_signature_verification() -> None:
    """测试有赞 Webhook 仿真数据生成与签名算法的正确性。"""
    buyer_id = "test_buyer_888"
    content_text = "帮我查一下订单发货了没"
    client_id = "test_client_id"
    client_secret = "test_webhook_token_secret"

    # 生成仿真数据
    raw_body, signature = YouzanMockEmulator.generate_webhook_message(
        buyer_id=buyer_id,
        content_text=content_text,
        client_id=client_id,
        client_secret=client_secret,
    )

    # 验证有赞 Webhook 模块的验证逻辑是否能通过
    assert verify_signature(client_id, client_secret, raw_body, signature) is True


@pytest.mark.asyncio
async def test_youzan_client_mock_api_calls() -> None:
    """测试开启 YOUZAN_MOCK_MODE 之后 API 被完全仿真拦截并不依赖真实网络。"""
    # 强制开启 Mock 模式
    settings.YOUZAN_MOCK_MODE = True

    client = YouzanClient()
    try:
        # 1. 验证 token 获取是否被拦截并返回仿真数据
        token = await client.get_token()
        assert token == "mock_access_token_123456"

        # 2. 验证消息回复接口拦截
        reply_resp = await client.send_reply(
            buyer_open_id="buyer_888", content="收到，马上处理"
        )
        assert reply_resp == {"response": {"success": True}}

        # 3. 验证订单详情查询拦截（data.full_order_info 结构）
        order_resp = await client.get_order(order_no="order_xyz999")
        foi = order_resp["data"]["full_order_info"]
        assert foi["order_info"]["tid"] == "order_xyz999"
        assert foi["order_info"]["status"] == "WAIT_SELLER_SEND_GOODS"

        # 4. 验证物流详情查询拦截
        logistics_resp = await client.get_logistics(order_no="order_xyz999")
        assert logistics_resp["response"]["express_name"] == "顺丰速运"
        assert len(logistics_resp["response"]["transit_step_infos"]) > 0

    finally:
        await client.close()
