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

    async def is_handoff_user(
        self,
        external_userid: str,
        db=None,
        *,
        read_only: bool = False,
        sessions_to_close: dict[str, str] | None = None,
    ) -> bool:
        """判断用户是否处于人工接管状态，传入连接时共用外层事务。"""
        if not external_userid:
            return False
        from app.database import db_session_scope
        from app.repository.session_repo import SessionRepo

        if db is not None:
            return await self._check_in_scope(
                SessionRepo(db),
                external_userid,
                read_only=read_only,
                sessions_to_close=sessions_to_close,
                commit=False,
            )
        async with db_session_scope():
            from app.database import db_conn_var

            return await self._check_in_scope(
                SessionRepo(db_conn_var.get()),
                external_userid,
                read_only=read_only,
                sessions_to_close=sessions_to_close,
                commit=True,
            )

    async def _check_in_scope(
        self,
        session_repo,
        external_userid: str,
        *,
        read_only: bool = False,
        sessions_to_close: dict[str, str] | None = None,
        commit: bool = True,
    ) -> bool:
        """在调用方事务内判断人工接管状态。"""
        session = await session_repo.get_active(external_userid, WECOM_KF_CHANNEL)
        if session is None:
            return False
        if session.status not in (
            SessionStatus.TRANSFER_PENDING,
            SessionStatus.HUMAN_SERVICE,
        ):
            return False
        if _is_idle_handoff_session(session.updated_at):
            await _defer_or_close_session(
                session_repo,
                external_userid,
                session.id,
                read_only=read_only,
                sessions_to_close=sessions_to_close,
                commit=commit,
            )
            logger.info(
                "微信客服人工会话空闲超时，已关闭本地旧会话 user=%s session=%s",
                external_userid,
                session.id,
            )
            return False
        if await self._is_wecom_session_replyable(external_userid):
            await _defer_or_close_session(
                session_repo,
                external_userid,
                session.id,
                read_only=read_only,
                sessions_to_close=sessions_to_close,
                commit=commit,
            )
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


async def _defer_or_close_session(
    session_repo,
    external_userid: str,
    session_id: str,
    *,
    read_only: bool,
    sessions_to_close: dict[str, str] | None,
    commit: bool,
) -> None:
    """分类只读时记录关闭意图，普通路径或持久化事务内直接关闭。"""
    if read_only:
        if sessions_to_close is not None:
            sessions_to_close[external_userid] = session_id
        return
    await session_repo.update_status(
        session_id,
        SessionStatus.CLOSED,
        commit=commit,
    )


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
