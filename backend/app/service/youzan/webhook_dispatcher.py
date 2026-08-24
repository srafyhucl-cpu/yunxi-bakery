"""有赞 Webhook 持久任务分发器。"""

import asyncio
import datetime
import json
import sqlite3
import time

from app.api.integrations.youzan_audit import YouzanWebhookAuditRecorder
from app.api.integrations.webhook_helpers import (
    is_youzan_hosting_event,
    is_youzan_hosting_message_event,
    parse_youzan_hosting_message,
)
from app.database import db_session_scope
from app.logger import setup_logger
from app.models.youzan_webhook_event import YouzanWebhookStatus
from app.repository.inbox_repo import InboxRepo
from app.service.alerting import AlertLevel, AlertService

logger = setup_logger()
DB_LOCK_RETRY_DELAYS = (0.05, 0.1, 0.2, 0.4)


class YouzanWebhookDispatcher:
    """持久化有赞 Webhook，并由单一 worker 处理。"""

    def __init__(self, alert_service: AlertService | None = None) -> None:
        self._chat_service = None
        self._worker_task: asyncio.Task[None] | None = None
        self._stop_requested = False
        self._alert_service = alert_service
        self._last_stuck_count = 0

    def start(self, chat_service) -> None:
        """启动持久 webhook worker。"""
        if self._worker_task is not None and not self._worker_task.done():
            return
        self._chat_service = chat_service
        self._stop_requested = False
        self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        """等待已持久化任务 drain 后停止。"""
        if self._worker_task is None or self._worker_task.done():
            return
        self._stop_requested = True
        await self._worker_task
        self._worker_task = None

    async def enqueue(
        self,
        message_key: str,
        payload: dict,
    ) -> bool:
        """将 webhook payload 写入 inbox。"""
        for delay in (0.0, *DB_LOCK_RETRY_DELAYS):
            if delay:
                await asyncio.sleep(delay)
            try:
                async with db_session_scope():
                    return await InboxRepo().enqueue(
                        "youzan_webhook",
                        f"youzan_webhook:{message_key}",
                        json.dumps(payload, ensure_ascii=False),
                    )
            except sqlite3.OperationalError as exc:
                if (
                    "locked" not in str(exc).lower()
                    or delay == DB_LOCK_RETRY_DELAYS[-1]
                ):
                    raise
        return False

    async def _worker_loop(self) -> None:
        while True:
            try:
                async with db_session_scope():
                    row = await InboxRepo().claim("youzan_webhook")
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower():
                    raise
                await asyncio.sleep(DB_LOCK_RETRY_DELAYS[-1])
                continue
            if row is None:
                await self._alert_on_stuck_tasks()
                if self._stop_requested:
                    return
                await asyncio.sleep(0.2)
                continue

            key = str(row["message_key"])
            try:
                payload = json.loads(str(row["payload_json"]))
                # B3.5（评审问题 8）：业务写与 mark_processed 同一事务——
                # 先在同一 UoW 内校验 lease 归属（claim_token 语义：被接管则
                # 跳过处理且不写业务、不标记失败，由新持有者负责），
                # 处理成功与 processed 标记原子提交，失败整体回滚可重试。
                async with db_session_scope():
                    if not await InboxRepo().renew_or_validate_lease(
                        key, expected_attempt=int(row["attempt_count"])
                    ):
                        logger.warning(
                            "有赞 webhook 已被其他 worker 接管，跳过处理: key=%s", key
                        )
                        continue
                    await process_youzan_webhook(self._chat_service, payload)
                    await InboxRepo().mark_processed(key)
            except Exception as exc:
                logger.error("有赞持久 webhook 处理失败 key=%s err=%s", key, exc)
                async with db_session_scope():
                    await InboxRepo().mark_failed(key, str(exc))

    async def _alert_on_stuck_tasks(self) -> None:
        """将过期 processing 任务提升为可观测告警。"""
        async with db_session_scope():
            stuck_count = await InboxRepo().count_stuck("youzan_webhook")
        if stuck_count <= 0:
            self._last_stuck_count = 0
            return
        if stuck_count == self._last_stuck_count or self._alert_service is None:
            return
        self._last_stuck_count = stuck_count
        await self._alert_service.alert(
            AlertLevel.CRITICAL,
            "有赞 webhook 任务卡住",
            f"发现 {stuck_count} 条 lease 已过期的 processing 任务。",
            key="youzan-webhook-stuck",
        )


async def process_youzan_webhook(chat_service, payload: dict) -> None:
    """执行一条已持久化的有赞 webhook。"""
    audit_recorder = YouzanWebhookAuditRecorder(chat_service)
    event_type = str(payload.get("event_type", ""))
    msg_id = str(payload.get("msg_id", ""))
    audit_id = payload.get("audit_id")
    buyer_id = str(payload.get("buyer_id", ""))
    business_payload = payload.get("body", {})

    try:
        if is_youzan_hosting_message_event(event_type):
            hosting_msg = parse_youzan_hosting_message(business_payload)
            conversation_id = hosting_msg["conversation_id"]
            hosting_msg_id = hosting_msg["msg_id"] or msg_id
            if not conversation_id or not hosting_msg_id:
                await audit_recorder.mark_result(
                    audit_id, YouzanWebhookStatus.SKIPPED, "hosting_missing_identity"
                )
                return
            await audit_recorder.mark_processing(audit_id, "hosting_chat_dispatched")
            if hosting_msg["msg_type"] != "text":
                await chat_service.reply_youzan_hosting_nontext_fallback(
                    conversation_id, hosting_msg_id
                )
                await audit_recorder.mark_result(
                    audit_id,
                    YouzanWebhookStatus.PROCESSED,
                    "hosting_nontext_fallback",
                )
                return
            content = hosting_msg["content"]
            if not content:
                await audit_recorder.mark_result(
                    audit_id, YouzanWebhookStatus.SKIPPED, "hosting_empty_content"
                )
                return
            await chat_service.handle_youzan_hosting_message(
                conversation_id=conversation_id,
                yz_open_id=hosting_msg["yz_open_id"],
                content=content,
                msg_id=hosting_msg_id,
            )
            await audit_recorder.mark_result(
                audit_id, YouzanWebhookStatus.PROCESSED, "hosting_chat_processed"
            )
            return

        if is_youzan_hosting_event(event_type):
            await audit_recorder.mark_result(
                audit_id, YouzanWebhookStatus.SKIPPED, "hosting_event_ack"
            )
            return

        if event_type:
            await audit_recorder.mark_processing(audit_id, "system_dispatched")
            timestamp_sec = business_payload.get("timestamp", int(time.time()))
            updated_at = datetime.datetime.fromtimestamp(timestamp_sec).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            await chat_service.handle_youzan_system_event(
                payload=business_payload,
                event_type=event_type,
                updated_at_str=updated_at,
                msg_id=msg_id,
                audit_id=audit_id,
            )
            await audit_recorder.mark_result(
                audit_id, YouzanWebhookStatus.PROCESSED, "system_processed"
            )
            return

        msg_type = business_payload.get("msg_type", "text")
        if msg_type != "text":
            await audit_recorder.mark_processing(audit_id, "chat_nontext_fallback")
            await chat_service.reply_youzan_nontext_fallback(buyer_id, msg_id)
            await audit_recorder.mark_result(
                audit_id, YouzanWebhookStatus.PROCESSED, "chat_nontext_fallback"
            )
            return

        content_obj = business_payload.get("content", {})
        content = (
            content_obj.get("text", "")
            if isinstance(content_obj, dict)
            else str(content_obj)
        )
        if not content:
            await audit_recorder.mark_result(
                audit_id, YouzanWebhookStatus.SKIPPED, "chat_empty_content"
            )
            return
        await audit_recorder.mark_processing(audit_id, "chat_dispatched")
        await chat_service.handle_message_and_reply_youzan(
            buyer_id=buyer_id,
            content=content,
            msg_id=msg_id,
        )
        await audit_recorder.mark_result(
            audit_id, YouzanWebhookStatus.PROCESSED, "chat_processed"
        )
    except Exception as exc:
        await audit_recorder.mark_failed(audit_id, "webhook_processing_failed", exc)
        raise
