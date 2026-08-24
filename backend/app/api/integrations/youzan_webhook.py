"""
Webhook API 路由。

接收有赞/企微的消息回调：
- 验证签名（有赞 MD5(client_id+body+client_secret) / 企微 SHA1）
- 解析消息内容
- 提交到 ChatService 异步处理
- 立即返回 200（不阻塞渠道重试）
"""

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.logger import setup_logger
from app.service.alerting import alert_service
from app.service.chat import ChatService
from app.service.youzan.webhook import (
    verify_signature as verify_youzan_signature,
)
from app.service.youzan.webhook_dispatcher import YouzanWebhookDispatcher
from app.api.integrations.youzan_audit import YouzanWebhookAuditRecorder
from app.api.integrations.webhook_helpers import (
    extract_trace_id,
    is_youzan_hosting_message_event,
    parse_youzan_hosting_message,
)

logger = setup_logger()
_dispatchers: set[YouzanWebhookDispatcher] = set()

PAYLOAD_PREVIEW_LIMIT = 300


def create_webhook_router(chat_service: ChatService) -> APIRouter:
    """工厂函数：注入 ChatService 依赖后返回路由实例。"""
    router = APIRouter(prefix="/api/v1/webhook", tags=["webhook"])
    audit_recorder = YouzanWebhookAuditRecorder(chat_service)
    dispatcher = YouzanWebhookDispatcher(alert_service=alert_service)
    dispatcher.start(chat_service)
    _dispatchers.add(dispatcher)

    @router.post("/youzan")
    async def youzan_webhook(request: Request) -> dict:
        """
        有赞消息回调入口（统一接收客服消息推送与交易/商品事件推送）。

        验证 MD5 签名后异步处理消息。
        通过秒级内存锁与数据库双重防线去重。
        """
        raw_body = await request.body()

        if (
            not settings.YOUZAN_CLIENT_ID.strip()
            or not settings.YOUZAN_CLIENT_SECRET.strip()
        ):
            raise HTTPException(status_code=503, detail="有赞 webhook 密钥未配置")

        # 1. 验证签名
        signature = request.headers.get("event-sign", "")
        if not verify_youzan_signature(
            settings.YOUZAN_CLIENT_ID,
            settings.YOUZAN_CLIENT_SECRET,
            raw_body,
            signature,
        ):
            logger.warning("有赞签名验证失败")
            raise HTTPException(status_code=403, detail="签名验证失败")

        # 2. 解析消息
        try:
            payload = await request.json()
        except Exception as exc:
            logger.error("有赞消息解析失败: %s", exc)
            raise HTTPException(status_code=400, detail="无效的 JSON 消息") from exc

        trace_id = extract_trace_id(request)
        # 3. 审计事件创建
        event_type = payload.get("type", "") or request.headers.get("event-type", "")
        msg_id = payload.get("msg_id") or payload.get("id") or ""
        if is_youzan_hosting_message_event(event_type):
            hosting_msg = parse_youzan_hosting_message(payload)
            msg_id = hosting_msg["msg_id"] or msg_id
        if not msg_id:
            msg_id = trace_id
        if not msg_id:
            logger.warning("有赞消息缺少可用的去重 ID，丢弃")
            return {"code": 0, "msg": "success"}

        buyer_id = payload.get("buyer_id", "")
        audit_id = await audit_recorder.create_event(
            payload, raw_body, msg_id, trace_id, event_type, buyer_id
        )

        queued = await dispatcher.enqueue(
            msg_id,
            {
                "event_type": event_type,
                "msg_id": msg_id,
                "buyer_id": buyer_id,
                "audit_id": audit_id,
                "body": payload,
            },
        )
        if not queued:
            logger.info(
                "有赞 webhook 已在持久 inbox 中，跳过重复入队 msg_id=%s", msg_id
            )
        return {"code": 0, "msg": "success"}

    return router


async def stop_webhook_dispatchers() -> None:
    """停止所有已装配的有赞持久 dispatcher。"""
    for dispatcher in tuple(_dispatchers):
        await dispatcher.stop()
    _dispatchers.clear()
