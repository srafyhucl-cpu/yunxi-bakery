"""微信客服回调业务处理器。"""

from typing import Protocol

from app.config import settings
from app.logger import setup_logger
from app.repository.wecom_kf_sync_repo import WecomKfSyncRepo
from app.service.wecom.kf_handoff_checker import DbHandoffSessionChecker
from app.service.wecom.kf_handoff_sync import mark_handoff_event
from app.service.wecom.kf_handoff_sync import save_handoff_customer_messages
from app.service.wecom.kf_message_classifier import KfMessageClassifier
from app.service.wecom.kf_message_queue import KfIncomingMessage, kf_queue
from app.service.wecom.kf_servicer_sync import save_servicer_messages
from app.service.wecom.kf_sync_models import (
    CollectedMessages,
    QueuedNontextMessage,
    empty_collected,
    merge_collected_messages,
)

logger = setup_logger()

STALE_MESSAGE_MAX_DELAY_SECONDS = 120
MAX_SYNC_PAGES = 10
WECOM_KF_CHANNEL = "wecom_kf"


class KfClientProtocol(Protocol):
    async def sync_kf_messages(self, kf_token: str, cursor: str = "") -> dict:
        """拉取微信客服消息。"""

        ...

    async def ensure_kf_session_active(self, external_userid: str) -> bool:
        """确认微信客服会话可回复。"""

        ...

    async def send_kf_event_text(
        self, code: str, content: str, msgid: str = ""
    ) -> dict:
        """发送微信客服事件响应消息。"""

        ...


class KfQueueProtocol(Protocol):
    async def enqueue(self, msg: KfIncomingMessage) -> bool:
        """入队微信客服消息。"""

        ...


class KfCallbackProcessor:
    """处理微信客服通知，拉取消息并按机器人/人工边界分流。"""

    def __init__(
        self,
        client: KfClientProtocol,
        queue: KfQueueProtocol = kf_queue,
    ) -> None:
        self._client = client
        self._queue = queue
        service_state_getter = getattr(client, "get_kf_service_state", None)
        self._classifier = KfMessageClassifier(
            DbHandoffSessionChecker(service_state_getter)
        )

    async def handle_callback(self, msg: dict) -> None:
        kf_token = msg.get("Token", "")
        open_kfid = msg.get("OpenKfId", "")
        if not kf_token:
            logger.warning("客服回调事件中无 Token 字段，忽略")
            return

        logger.info(
            "收到客服回调通知 open_kfid=%s token=%s...", open_kfid, kf_token[:8]
        )
        collected = await self._sync_and_collect(open_kfid, kf_token)
        if collected is None:
            return

        for event in collected.start_events:
            await mark_handoff_event(
                event.external_userid, event.change_type, event.staff_id
            )
            await self._send_welcome_on_event(event.event_code)

        handoff_user_count = await save_handoff_customer_messages(
            collected.handoff_customer_messages
        )
        human_count = await save_servicer_messages(collected.servicer_messages)

        for event in collected.end_events:
            await mark_handoff_event(
                event.external_userid, event.change_type, event.staff_id
            )

        queued_count = await self._enqueue_messages(
            open_kfid,
            collected.user_messages,
            collected.nontext_messages,
        )

        logger.info(
            "客服回调处理完成 total=%d queued=%d human_synced=%d handoff_user_synced=%d",
            collected.total_count,
            queued_count,
            human_count,
            handoff_user_count,
        )

    async def _send_welcome_on_event(self, event_code: str) -> None:
        content = settings.WECOM_KF_WELCOME_TEXT.strip()
        if not event_code or not content:
            return
        try:
            result = await self._client.send_kf_event_text(event_code, content)
        except Exception as exc:
            logger.warning("客服欢迎事件响应发送异常: %s", exc)
            return
        if result.get("errcode") != 0:
            logger.warning(
                "客服欢迎事件响应发送失败 err=%s %s",
                result.get("errcode"),
                result.get("errmsg"),
            )

    async def _sync_and_collect(
        self,
        open_kfid: str,
        kf_token: str,
    ) -> CollectedMessages | None:
        from app.database import db_session_scope

        async with db_session_scope():
            sync_repo = WecomKfSyncRepo()
            state = await sync_repo.get_state(open_kfid)
            await sync_repo.mark_syncing(open_kfid)
            cursor = state.last_cursor
            collected = empty_collected()
            for _ in range(MAX_SYNC_PAGES):
                result = await self._pull_page(kf_token, cursor, sync_repo, open_kfid)
                if result is None:
                    return None
                page = await self._classifier.collect_messages(
                    result.get("msg_list", []),
                    open_kfid,
                    sync_repo,
                    collected.active_handoff_users,
                    collected.ended_handoff_users,
                )
                collected = merge_collected_messages(collected, page)
                cursor = str(result.get("next_cursor") or cursor)
                if not result.get("has_more"):
                    await sync_repo.mark_success(open_kfid, cursor)
                    return collected

            await sync_repo.mark_success(open_kfid, cursor)
            logger.warning("sync_msg 达到最大分页次数 open_kfid=%s", open_kfid)
            return collected

    async def _pull_page(
        self,
        kf_token: str,
        cursor: str,
        sync_repo: WecomKfSyncRepo,
        open_kfid: str,
    ) -> dict | None:
        try:
            result = await self._client.sync_kf_messages(
                kf_token=kf_token, cursor=cursor
            )
        except Exception as exc:
            await sync_repo.mark_failed(open_kfid, str(exc))
            logger.error("sync_msg 拉取消息失败: %s", exc)
            return None

        if result.get("errcode") == 0:
            return result

        error = f"{result.get('errcode')} {result.get('errmsg')}"
        await sync_repo.mark_failed(open_kfid, error)
        logger.error(
            "sync_msg 返回错误 err=%s %s", result.get("errcode"), result.get("errmsg")
        )
        return None

    async def _enqueue_messages(
        self,
        open_kfid: str,
        user_messages: dict[str, dict[str, dict]],
        nontext_messages: list[QueuedNontextMessage],
    ) -> int:
        enqueued_count = 0
        for external_userid, message_by_id in user_messages.items():
            if not await self._can_reply(external_userid, len(message_by_id)):
                continue
            for message_id, item in message_by_id.items():
                if await self._queue.enqueue(
                    KfIncomingMessage(
                        external_userid=external_userid,
                        open_kfid=open_kfid,
                        content=item["text"]["content"],
                        msg_id=message_id,
                        msgtype="text",
                    )
                ):
                    enqueued_count += 1
                else:
                    logger.warning("客服消息队列已满，丢弃 user=%s", external_userid)

        for nontext_message in nontext_messages:
            if not await self._can_reply(nontext_message.external_userid, 1):
                continue
            if await self._queue.enqueue(
                KfIncomingMessage(
                    external_userid=nontext_message.external_userid,
                    open_kfid=nontext_message.open_kfid,
                    content=f"[{nontext_message.msgtype}消息]",
                    msg_id=nontext_message.msg_id,
                    msgtype=nontext_message.msgtype,
                    media_id=nontext_message.media_id,
                )
            ):
                enqueued_count += 1
            else:
                logger.warning(
                    "客服消息队列已满，丢弃非文本消息 user=%s type=%s",
                    nontext_message.external_userid,
                    nontext_message.msgtype,
                )
        return enqueued_count

    async def _can_reply(self, external_userid: str, message_count: int) -> bool:
        can_reply = await self._client.ensure_kf_session_active(external_userid)
        if not can_reply:
            logger.info(
                "用户会话不可用，跳过 %d 条消息 user=%s", message_count, external_userid
            )
        return can_reply
