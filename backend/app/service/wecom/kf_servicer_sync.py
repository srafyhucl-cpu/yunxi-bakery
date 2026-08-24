"""微信客服接待人员消息同步落库。"""

from dataclasses import dataclass

from app.logger import setup_logger
from app.models.message import Message, MessageRole
from app.models.session_scope import mark_human_messages_synced
from app.repository.message_repo import MessageRepo
from app.repository.session_repo import SessionRepo

logger = setup_logger()

WECOM_KF_CHANNEL = "wecom_kf"


@dataclass(frozen=True)
class SyncedServicerMessage:
    """等待落库的接待人员消息。"""

    external_userid: str
    content: str
    msg_id: str


async def save_servicer_messages(messages: list[SyncedServicerMessage]) -> int:
    """幂等保存接待人员消息，并标记会话人工阶段可见。"""
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
                    "人工客服消息未找到可关联会话 user=%s msg_id=%s",
                    message.external_userid,
                    message.msg_id,
                )
                continue
            saved = await message_repo.save_if_new(
                Message(
                    id="",
                    session_id=session.id,
                    role=MessageRole.ASSISTANT,
                    content=message.content,
                    channel_msg_id=message.msg_id,
                )
            )
            if not saved:
                continue
            await session_repo.touch(session.id)
            await session_repo.update_extra(
                session.id,
                mark_human_messages_synced(session.extra_info),
            )
            saved_count += 1
    return saved_count
