"""微信客服转人工阶段消息与状态同步。"""

from dataclasses import dataclass

from app.logger import setup_logger
from app.models.message import Message, MessageRole
from app.models.session import Session, SessionStatus
from app.models.session_scope import mark_handoff_started
from app.models.transfer import TransferStatus
from app.repository.message_repo import MessageRepo
from app.repository.session_repo import SessionRepo
from app.repository.transfer_repo import TransferRepo

logger = setup_logger()

WECOM_KF_CHANNEL = "wecom_kf"


@dataclass(frozen=True)
class SyncedCustomerMessage:
    """转人工阶段仅同步、不触发 AI 的用户消息。"""

    external_userid: str
    content: str
    msg_id: str


async def save_handoff_customer_messages(
    messages: list[SyncedCustomerMessage],
) -> int:
    """保存人工接管期间的用户消息，不进入 AI 回复队列。"""
    if not messages:
        return 0

    from app.database import db_session_scope

    saved_count = 0
    async with db_session_scope():
        session_repo = SessionRepo()
        message_repo = MessageRepo()
        for message in messages:
            session = await session_repo.get_active(
                message.external_userid,
                WECOM_KF_CHANNEL,
            )
            if session is None:
                logger.info(
                    "人工阶段用户消息未找到可关联会话 user=%s msg_id=%s",
                    message.external_userid,
                    message.msg_id,
                )
                continue
            saved = await message_repo.save_if_new(
                Message(
                    id="",
                    session_id=session.id,
                    role=MessageRole.USER,
                    content=message.content,
                    channel_msg_id=message.msg_id,
                )
            )
            if saved:
                await session_repo.touch(session.id)
                saved_count += 1
    return saved_count


async def mark_handoff_event(
    external_userid: str,
    change_type: int,
    staff_id: str = "",
) -> None:
    """根据企微客服会话事件更新本地会话和工单状态。"""
    from app.database import db_session_scope

    async with db_session_scope():
        session_repo = SessionRepo()
        transfer_repo = TransferRepo()
        session = await _find_event_session(session_repo, external_userid, change_type)
        if session is None:
            logger.info(
                "客服状态事件未找到本地会话 user=%s change=%d",
                external_userid,
                change_type,
            )
            return

        if change_type in (1, 2, 4):
            await session_repo.update_status(session.id, SessionStatus.HUMAN_SERVICE)
            await session_repo.update_extra(
                session.id,
                mark_handoff_started(session.extra_info),
            )
            await transfer_repo.mark_latest_for_session(
                session.id,
                TransferStatus.ACCEPTED,
                staff_id,
            )
            logger.info(
                "客服人工接入事件已同步 user=%s change=%d",
                session.user_id,
                change_type,
            )
            return

        if change_type == 3:
            await session_repo.update_status(session.id, SessionStatus.CLOSED)
            await transfer_repo.mark_latest_for_session(
                session.id,
                TransferStatus.CLOSED,
            )
            logger.info("客服会话结束事件已同步 user=%s", session.user_id)


async def _find_event_session(
    session_repo: SessionRepo,
    external_userid: str,
    change_type: int,
) -> Session | None:
    if external_userid:
        return await session_repo.get_latest(external_userid, WECOM_KF_CHANNEL)
    if change_type != 3:
        return None

    active_sessions = [
        session
        for session in await session_repo.get_all_by_channel(WECOM_KF_CHANNEL)
        if session.status
        in (SessionStatus.TRANSFER_PENDING, SessionStatus.HUMAN_SERVICE)
    ]
    if len(active_sessions) != 1:
        logger.warning(
            "客服结束事件缺少 user，无法唯一归属 active_count=%d",
            len(active_sessions),
        )
        return None
    logger.info(
        "客服结束事件缺少 user，归属唯一活跃人工会话 session=%s", active_sessions[0].id
    )
    return active_sessions[0]
