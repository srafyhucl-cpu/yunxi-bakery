"""微信客服 sync_msg 消息分类器。"""

import time
from typing import Protocol

from app.logger import setup_logger
from app.repository.wecom_kf_sync_repo import WecomKfSyncRepo
from app.service.wecom.kf_handoff_sync import SyncedCustomerMessage
from app.service.wecom.kf_servicer_sync import SyncedServicerMessage
from app.service.wecom.kf_sync_models import (
    CUSTOMER_ORIGIN,
    SESSION_END_CHANGE_TYPE,
    SERVICER_ORIGIN,
    SYSTEM_ORIGIN,
    CollectedMessages,
    QueuedNontextMessage,
    append_sync_event,
    build_sync_event,
    extract_event_type,
    extract_media_id,
    extract_message_content,
)

logger = setup_logger()

STALE_MESSAGE_MAX_DELAY_SECONDS = 120


class HandoffSessionChecker(Protocol):
    async def is_handoff_user(self, external_userid: str) -> bool:
        """判断用户当前是否处于人工接管状态。"""


class KfMessageClassifier:
    """将 sync_msg 返回内容分类为 AI 入队、人工同步和系统事件。"""

    def __init__(self, handoff_checker: HandoffSessionChecker) -> None:
        self._handoff_checker = handoff_checker

    async def collect_messages(
        self,
        msg_list: list[dict],
        open_kfid: str,
        sync_repo: WecomKfSyncRepo,
        active_handoff_users: set[str] | None = None,
        ended_handoff_users: set[str] | None = None,
    ) -> CollectedMessages:
        user_messages: dict[str, dict[str, dict]] = {}
        nontext_processed_users: set[str] = set()
        nontext_messages: list[QueuedNontextMessage] = []
        handoff_customer_messages: list[SyncedCustomerMessage] = []
        servicer_messages: list[SyncedServicerMessage] = []
        start_events = []
        end_events = []
        active_users = set(active_handoff_users or set())
        ended_users = set(ended_handoff_users or set())

        for item in msg_list:
            if _is_stale_message(item):
                continue
            if not await _mark_message_if_new(item, open_kfid, sync_repo):
                continue

            event = build_sync_event(item)
            if event is not None:
                append_sync_event(event, start_events, end_events)
                _apply_session_event(
                    event.external_userid, event.change_type, active_users, ended_users
                )
                continue

            if _is_servicer_message(item):
                servicer_message = _build_servicer_message(item)
                if servicer_message is not None:
                    servicer_messages.append(servicer_message)
                continue

            if not _is_customer_message(item):
                continue

            external_userid = item.get("external_userid", "")
            if external_userid in active_users or (
                external_userid not in ended_users
                and await self._handoff_checker.is_handoff_user(external_userid)
            ):
                active_users.add(external_userid)
                handoff_message = _build_handoff_customer_message(item)
                if handoff_message is not None:
                    handoff_customer_messages.append(handoff_message)
                continue

            _collect_replyable_customer_message(
                user_messages,
                nontext_processed_users,
                nontext_messages,
                open_kfid,
                item,
            )

        return CollectedMessages(
            user_messages=user_messages,
            nontext_messages=nontext_messages,
            handoff_customer_messages=handoff_customer_messages,
            servicer_messages=servicer_messages,
            start_events=start_events,
            end_events=end_events,
            active_handoff_users=active_users,
            ended_handoff_users=ended_users,
            total_count=len(msg_list),
        )


async def _mark_message_if_new(
    item: dict,
    open_kfid: str,
    sync_repo: WecomKfSyncRepo,
) -> bool:
    return await sync_repo.add_message_if_new(
        msg_id=item.get("msgid", ""),
        open_kfid=open_kfid,
        external_userid=item.get("external_userid", ""),
        origin=int(item.get("origin", 0) or 0),
        msgtype=item.get("msgtype", ""),
        event_type=extract_event_type(item),
        process_action=_classify_process_action(item),
    )


def _classify_process_action(item: dict) -> str:
    if build_sync_event(item) is not None:
        return "session_event"
    origin = item.get("origin", 0)
    if origin == SERVICER_ORIGIN:
        return "sync_servicer"
    if origin == CUSTOMER_ORIGIN:
        return "route_customer"
    return "ignore"


def _is_stale_message(item: dict) -> bool:
    send_time = item.get("send_time", 0)
    if send_time <= 0:
        return False
    delay = int(time.time()) - send_time
    if delay <= STALE_MESSAGE_MAX_DELAY_SECONDS:
        return False
    logger.info(
        "跳过微信客服过期的历史重推消息 msg_id=%s send_time=%d delay=%ds",
        item.get("msgid", ""),
        send_time,
        delay,
    )
    return True


def _is_customer_message(item: dict) -> bool:
    origin = item.get("origin", 0)
    if origin == CUSTOMER_ORIGIN:
        return True
    if origin == SYSTEM_ORIGIN:
        logger.debug(
            "客服系统事件 type=%s msg_id=%s",
            extract_event_type(item),
            item.get("msgid", ""),
        )
    return False


def _is_servicer_message(item: dict) -> bool:
    return item.get("origin", 0) == SERVICER_ORIGIN


def _build_servicer_message(item: dict) -> SyncedServicerMessage | None:
    external_userid = item.get("external_userid", "")
    msg_id = item.get("msgid", "")
    content = extract_message_content(item)
    if not external_userid or not msg_id or not content:
        return None
    return SyncedServicerMessage(
        external_userid=external_userid,
        content=f"[人工客服] {content}",
        msg_id=msg_id,
    )


def _build_handoff_customer_message(item: dict) -> SyncedCustomerMessage | None:
    external_userid = item.get("external_userid", "")
    msg_id = item.get("msgid", "")
    content = extract_message_content(item)
    if not external_userid or not msg_id or not content:
        return None
    return SyncedCustomerMessage(
        external_userid=external_userid,
        content=content,
        msg_id=msg_id,
    )


def _collect_replyable_customer_message(
    user_messages: dict[str, dict[str, dict]],
    nontext_processed_users: set[str],
    nontext_messages: list[QueuedNontextMessage],
    open_kfid: str,
    item: dict,
) -> None:
    external_userid = item.get("external_userid", "")
    msgtype = item.get("msgtype", "")
    if msgtype == "text":
        _collect_text_message(user_messages, external_userid, item)
        return
    _collect_nontext_message(
        nontext_processed_users,
        nontext_messages,
        external_userid,
        open_kfid,
        item,
    )


def _collect_text_message(
    user_messages: dict[str, dict[str, dict]],
    external_userid: str,
    item: dict,
) -> None:
    text_content = item.get("text", {}).get("content", "")
    item_msgid = item.get("msgid", "")
    if not text_content.strip():
        return
    user_dict = user_messages.setdefault(external_userid, {})
    if item_msgid in user_dict:
        logger.debug("重复消息已跳过 user=%s msg_id=%s", external_userid, item_msgid)
        return
    user_dict[item_msgid] = item
    logger.info(
        "收到客服文本消息 user=%s content=%s msg_id=%s",
        external_userid,
        text_content[:50],
        item_msgid,
    )


def _collect_nontext_message(
    nontext_processed_users: set[str],
    nontext_messages: list[QueuedNontextMessage],
    external_userid: str,
    open_kfid: str,
    item: dict,
) -> None:
    item_msgid = item.get("msgid", "")
    msgtype = item.get("msgtype", "")
    if external_userid in nontext_processed_users:
        logger.debug(
            "重复非文本消息已跳过 user=%s msg_id=%s", external_userid, item_msgid
        )
        return
    nontext_processed_users.add(external_userid)
    media_id = extract_media_id(item)
    logger.info(
        "收到客服非文本消息 type=%s user=%s media_id=%s msg_id=%s",
        msgtype,
        external_userid,
        media_id[:20] if media_id else "(空)",
        item_msgid,
    )
    nontext_messages.append(
        QueuedNontextMessage(
            external_userid=external_userid,
            open_kfid=open_kfid,
            msgtype=msgtype,
            media_id=media_id,
            msg_id=item_msgid,
        )
    )


def _apply_session_event(
    external_userid: str,
    change_type: int,
    active_users: set[str],
    ended_users: set[str],
) -> None:
    if not external_userid:
        return
    if change_type == SESSION_END_CHANGE_TYPE:
        active_users.discard(external_userid)
        ended_users.add(external_userid)
        return
    active_users.add(external_userid)
    ended_users.discard(external_userid)
