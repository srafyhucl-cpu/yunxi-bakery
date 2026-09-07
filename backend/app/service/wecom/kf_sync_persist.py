"""微信客服同步持久化命令，与回调路由分离。"""

import json

from app.logger import setup_logger
from app.repository.inbox_repo import InboxRepo
from app.repository.wecom_kf_sync_repo import WecomKfSyncRepo
from app.service.wecom.kf_message_queue import KfIncomingMessage
from app.service.wecom.kf_sync_models import QueuedNontextMessage

logger = setup_logger()


async def stage_inbox_messages(
    db,
    open_kfid: str,
    user_messages: dict[str, dict[str, dict]],
    nontext_messages: list[QueuedNontextMessage],
) -> int:
    """在调用方事务内暂存待回复消息到持久收件箱。

    调用方事务提交后才生效，失败整体回滚，游标不会超前。
    """
    staged_count = 0
    inbox_repo = InboxRepo(db)
    for external_userid, message_by_id in user_messages.items():
        for message_id, item in message_by_id.items():
            content = item.get("text", {}).get("content", "")
            await inbox_repo.enqueue(
                "wecom_kf",
                f"wecom_kf:{message_id}",
                json.dumps(
                    KfIncomingMessage(
                        external_userid=external_userid,
                        open_kfid=open_kfid,
                        content=content,
                        msg_id=message_id,
                        msgtype="text",
                    ).__dict__,
                    ensure_ascii=False,
                ),
            )
            staged_count += 1
    for nontext_message in nontext_messages:
        await inbox_repo.enqueue(
            "wecom_kf",
            f"wecom_kf:{nontext_message.msg_id}",
            json.dumps(
                KfIncomingMessage(
                    external_userid=nontext_message.external_userid,
                    open_kfid=nontext_message.open_kfid,
                    content=f"[{nontext_message.msgtype}消息]",
                    msg_id=nontext_message.msg_id,
                    msgtype=nontext_message.msgtype,
                    media_id=nontext_message.media_id,
                ).__dict__,
                ensure_ascii=False,
            ),
        )
        staged_count += 1
    return staged_count


async def advance_sync_cursor(db, open_kfid: str, cursor: str) -> None:
    """在调用方事务内推进同步游标，仅在消息持久化后调用。"""
    await WecomKfSyncRepo(db).mark_success(open_kfid, cursor)


async def commit_ledger_pendings(db, pendings: list[dict]) -> set[str]:
    """在调用方事务内提交消息账本，返回本次新见的消息标识集合。"""
    sync_repo = WecomKfSyncRepo(db)
    fresh: set[str] = set()
    for pending in pendings or []:
        msg_id = str(pending.get("msg_id", "") or "")
        if not msg_id:
            continue
        if await sync_repo.add_message_if_new(
            msg_id=msg_id,
            open_kfid=str(pending.get("open_kfid", "") or ""),
            external_userid=str(pending.get("external_userid", "") or ""),
            origin=int(pending.get("origin", 0) or 0),
            msgtype=str(pending.get("msgtype", "") or ""),
            event_type=str(pending.get("event_type", "") or ""),
            process_action=str(pending.get("process_action", "") or ""),
        ):
            fresh.add(msg_id)
    return fresh


def filter_collected_by_fresh_ids(collected, fresh_ids: set[str]):
    """按账本复核后的新消息集合过滤分类结果，重跑不重复。"""
    from app.service.wecom.kf_sync_models import CollectedMessages

    fresh_users: dict[str, dict[str, dict]] = {}
    for external_userid, message_by_id in collected.user_messages.items():
        for message_id, item in message_by_id.items():
            if message_id in fresh_ids:
                fresh_users.setdefault(external_userid, {})[message_id] = item
    fresh_userids = {
        *fresh_users,
        *(
            msg.external_userid
            for msg in collected.nontext_messages
            if msg.msg_id in fresh_ids
        ),
        *(
            msg.external_userid
            for msg in collected.handoff_customer_messages
            if msg.msg_id in fresh_ids
        ),
    }
    return CollectedMessages(
        user_messages=fresh_users,
        nontext_messages=[
            msg for msg in collected.nontext_messages if msg.msg_id in fresh_ids
        ],
        handoff_customer_messages=[
            msg
            for msg in collected.handoff_customer_messages
            if msg.msg_id in fresh_ids
        ],
        servicer_messages=[
            msg for msg in collected.servicer_messages if msg.msg_id in fresh_ids
        ],
        start_events=[
            event for event in collected.start_events if event.msg_id in fresh_ids
        ],
        end_events=[
            event for event in collected.end_events if event.msg_id in fresh_ids
        ],
        active_handoff_users=collected.active_handoff_users,
        ended_handoff_users=collected.ended_handoff_users,
        total_count=collected.total_count,
        ledger_pendings=[],
        handoff_sessions_to_close={
            user_id: session_id
            for user_id, session_id in (
                collected.handoff_sessions_to_close or {}
            ).items()
            if user_id in fresh_userids
        },
    )


async def filter_collected_by_ledger(
    db,
    open_kfid: str,
    user_messages: dict[str, dict[str, dict]],
    nontext_messages: list[QueuedNontextMessage],
) -> tuple[dict[str, dict[str, dict]], list[QueuedNontextMessage]]:
    """在调用方事务内用消息账本复核去重，返回未见过的新消息。

    事务外分类阶段不写账本，此处 INSERT OR IGNORE 为准：已见过的消息
    不再进收件箱与通知队列，保证重跑不重复、游标不超前。
    """
    sync_repo = WecomKfSyncRepo(db)
    fresh_users: dict[str, dict[str, dict]] = {}
    for external_userid, message_by_id in user_messages.items():
        for message_id, item in message_by_id.items():
            if await sync_repo.add_message_if_new(
                msg_id=message_id,
                open_kfid=open_kfid,
                external_userid=external_userid,
                origin=3,
                msgtype="text",
                event_type="",
                process_action="route_customer",
            ):
                fresh_users.setdefault(external_userid, {})[message_id] = item
    fresh_nontext: list[QueuedNontextMessage] = []
    for nontext_message in nontext_messages:
        if await sync_repo.add_message_if_new(
            msg_id=nontext_message.msg_id,
            open_kfid=nontext_message.open_kfid,
            external_userid=nontext_message.external_userid,
            origin=0,
            msgtype=nontext_message.msgtype,
            event_type="",
            process_action="route_customer",
        ):
            fresh_nontext.append(nontext_message)
    return fresh_users, fresh_nontext
