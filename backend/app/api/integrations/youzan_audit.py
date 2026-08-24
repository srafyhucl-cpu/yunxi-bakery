"""有赞 Webhook 审计状态写入辅助。"""

import hashlib

from app.api.integrations.webhook_helpers import (
    build_payload_summary,
    extract_business_fields,
)
from app.logger import setup_logger
from app.models.youzan_webhook_event import (
    YouzanWebhookEventCreate,
    YouzanWebhookEventUpdate,
    YouzanWebhookStatus,
)

logger = setup_logger()

AUDIT_HTTP_OK = 200


class YouzanWebhookAuditRecorder:
    """封装有赞 Webhook 审计写入，避免路由入口承担审计细节。"""

    def __init__(self, chat_service) -> None:
        self._chat_service = chat_service

    async def create_event(
        self,
        payload: dict,
        raw_body: bytes,
        msg_id: str,
        trace_id: str,
        event_type: str,
        buyer_id: str,
    ) -> int | None:
        """创建有赞 Webhook 审计事件，返回审计 ID。"""
        if not hasattr(self._chat_service, "create_youzan_webhook_audit"):
            return None
        business_type, business_key = extract_business_fields(
            payload, event_type, buyer_id
        )
        try:
            return await self._chat_service.create_youzan_webhook_audit(
                YouzanWebhookEventCreate(
                    msg_id=msg_id,
                    trace_id=trace_id,
                    event_type=event_type,
                    business_type=business_type,
                    business_key=business_key,
                    http_status=AUDIT_HTTP_OK,
                    payload_hash=hashlib.sha256(raw_body).hexdigest(),
                    payload_summary_json=build_payload_summary(
                        payload, event_type, business_type, business_key
                    ),
                ),
            )
        except Exception as exc:
            logger.error("有赞 webhook 审计收件写入失败 [msg_id=%s]: %s", msg_id, exc)
            return None

    async def mark_processing(self, audit_id: int | None, stage: str) -> None:
        """标记审计事件进入处理阶段。"""
        if audit_id is None or not hasattr(
            self._chat_service, "mark_youzan_webhook_processing"
        ):
            return
        try:
            await self._chat_service.mark_youzan_webhook_processing(audit_id, stage)
        except Exception as exc:
            logger.error(
                "有赞 webhook 审计处理中状态写入失败 [audit_id=%s]: %s",
                audit_id,
                exc,
            )

    async def mark_result(
        self,
        audit_id: int | None,
        status: str,
        stage: str,
        error_type: str = "",
        error_message: str = "",
    ) -> None:
        """标记审计事件处理结果。"""
        if audit_id is None or not hasattr(
            self._chat_service, "mark_youzan_webhook_result"
        ):
            return
        try:
            await self._chat_service.mark_youzan_webhook_result(
                audit_id,
                YouzanWebhookEventUpdate(
                    status=status,
                    process_stage=stage,
                    error_type=error_type,
                    error_message=error_message,
                ),
            )
        except Exception as exc:
            logger.error(
                "有赞 webhook 审计结果写入失败 [audit_id=%s]: %s", audit_id, exc
            )

    async def mark_failed(
        self, audit_id: int | None, stage: str, exc: Exception
    ) -> None:
        """将异常转换为审计失败结果。"""
        await self.mark_result(
            audit_id, YouzanWebhookStatus.FAILED, stage, type(exc).__name__, str(exc)
        )
