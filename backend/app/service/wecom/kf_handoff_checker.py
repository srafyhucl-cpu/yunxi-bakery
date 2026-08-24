"""微信客服人工接管状态检查器。"""

from collections.abc import Awaitable, Callable
from datetime import datetime

from app.config import settings
from app.logger import setup_logger
from app.models.session import SessionStatus

logger = setup_logger()

WECOM_KF_CHANNEL = "wecom_kf"
BOT_REPLYABLE_STATES = {0, 1, 4}


class DbHandoffSessionChecker:
    """从数据库和企微实际状态判断用户是否处于人工接管状态。"""

    def __init__(
        self,
        service_state_getter: Callable[[str], Awaitable[int | None]] | None = None,
    ) -> None:
        self._service_state_getter = service_state_getter

    async def is_handoff_user(self, external_userid: str) -> bool:
        if not external_userid:
            return False
        from app.database import db_session_scope
        from app.repository.session_repo import SessionRepo

        async with db_session_scope():
            session_repo = SessionRepo()
            session = await session_repo.get_active(external_userid, WECOM_KF_CHANNEL)
            if session is None:
                return False
            if session.status not in (
                SessionStatus.TRANSFER_PENDING,
                SessionStatus.HUMAN_SERVICE,
            ):
                return False
            if _is_idle_handoff_session(session.updated_at):
                await _close_local_handoff_session(session_repo, session.id)
                logger.info(
                    "微信客服人工会话空闲超时，已关闭本地旧会话 user=%s session=%s",
                    external_userid,
                    session.id,
                )
                return False
            if await self._is_wecom_session_replyable(external_userid):
                await _close_local_handoff_session(session_repo, session.id)
                logger.info(
                    "企微客服实际状态已离开人工，本地旧会话已关闭 user=%s session=%s",
                    external_userid,
                    session.id,
                )
                return False
            return True

    async def _is_wecom_session_replyable(self, external_userid: str) -> bool:
        if self._service_state_getter is None:
            return False
        try:
            state = await self._service_state_getter(external_userid)
        except Exception as exc:
            logger.warning(
                "查询企微客服实际状态失败 user=%s err=%s", external_userid, exc
            )
            return False
        return state in BOT_REPLYABLE_STATES


async def _close_local_handoff_session(session_repo, session_id: str) -> None:
    await session_repo.update_status(session_id, SessionStatus.CLOSED)


def _is_idle_handoff_session(updated_at: str) -> bool:
    if not updated_at:
        return False
    try:
        updated = datetime.strptime(updated_at, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        logger.warning("无法解析会话 updated_at=%s，跳过空闲关闭判断", updated_at)
        return False
    idle_seconds = (datetime.now() - updated).total_seconds()
    return idle_seconds > settings.WECOM_KF_SESSION_IDLE_CLOSE_SECONDS
