"""微信客服回调业务处理器。"""

from typing import Protocol

from app.config import settings
from app.logger import setup_logger
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


class _SyncPullFailed(Exception):
    """同步拉取失败，调用方回滚后记失败状态。"""

    def __init__(self, open_kfid: str, error: str) -> None:
        super().__init__(error)
        self.open_kfid = open_kfid
        self.error = error


class _StaleSyncLease(Exception):
    """同步租约过期或游标被推进，本次持久化必须整体回滚。"""

    def __init__(self, open_kfid: str, error: str) -> None:
        super().__init__(error)
        self.open_kfid = open_kfid
        self.error = error


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
        from app.database import db_session_scope
        from app.repository.wecom_kf_sync_lease_repo import WecomKfSyncLeaseRepo
        from app.repository.wecom_kf_sync_repo import WecomKfSyncRepo as SyncRepo

        kf_token = msg.get("Token", "")
        open_kfid = msg.get("OpenKfId", "")
        if not kf_token:
            logger.warning("客服回调事件中无 Token 字段，忽略")
            return

        logger.info(
            "收到客服回调通知 open_kfid=%s token=%s...", open_kfid, kf_token[:8]
        )
        # 第一段短事务：原子取得同步租约后提交，不在事务内做网络调用。
        async with db_session_scope() as db:
            lease = await WecomKfSyncLeaseRepo(db).acquire(open_kfid)
        if lease is None:
            logger.warning("已有同步者持有租约，跳过本次回调 open_kfid=%s", open_kfid)
            return
        lease_token = str(lease["lease_token"])
        base_cursor = str(lease["base_cursor"])

        # 事务外分页拉取与分类，不写数据库。
        try:
            collected, end_cursor, truncated = await self._fetch_and_classify(
                open_kfid, kf_token, base_cursor
            )
        except _SyncPullFailed as exc:
            async with db_session_scope() as db:
                await SyncRepo(db).mark_failed(exc.open_kfid, exc.error)
                await WecomKfSyncLeaseRepo(db).fail(open_kfid, lease_token, exc.error)
            logger.error("客服同步拉取失败 open_kfid=%s err=%s", open_kfid, exc.error)
            return

        # 第二段短事务：校验租约与游标未变化，再持久化并释放租约。
        try:
            async with db_session_scope() as db:
                fresh, handoff_user_count, human_count = await self._persist_in_scope(
                    db,
                    open_kfid,
                    lease_token,
                    base_cursor,
                    collected,
                    end_cursor,
                    truncated,
                )
        except _StaleSyncLease as exc:
            async with db_session_scope() as db:
                await SyncRepo(db).mark_failed(open_kfid, exc.error)
                await WecomKfSyncLeaseRepo(db).fail(open_kfid, lease_token, exc.error)
            logger.error("客服同步租约过期 open_kfid=%s err=%s", open_kfid, exc.error)
            raise
        except Exception as exc:
            async with db_session_scope() as db:
                await SyncRepo(db).mark_failed(open_kfid, str(exc))
                await WecomKfSyncLeaseRepo(db).fail(open_kfid, lease_token, str(exc))
            raise

        for event in fresh.start_events:
            await self._send_welcome_on_event(event)

        notified_count = await self._enqueue_messages(
            open_kfid,
            fresh.user_messages,
            fresh.nontext_messages,
        )

        logger.info(
            "客服回调处理完成 total=%d queued=%d human_synced=%d handoff_user_synced=%d",
            fresh.total_count,
            notified_count,
            human_count,
            handoff_user_count,
        )

    async def _send_welcome_on_event(self, event) -> None:
        from app.service.wecom.kf_outbound_sender import send_event_guarded

        content = settings.WECOM_KF_WELCOME_TEXT.strip()
        if not event.event_code or not content:
            return
        try:
            status = await send_event_guarded(
                self._client,
                event.event_code,
                event.msg_id or event.event_code,
                content,
                part=f"welcome:{event.event_code}",
            )
        except Exception as exc:
            logger.warning("客服欢迎事件响应发送异常: %s", exc)
            return
        if status not in ("sent",):
            logger.warning(
                "客服欢迎事件响应未确认 code=%s status=%s", event.event_code, status
            )

    async def _persist_in_scope(
        self,
        db,
        open_kfid: str,
        lease_token: str,
        base_cursor: str,
        collected: CollectedMessages,
        end_cursor: str,
        truncated: bool,
    ) -> tuple[CollectedMessages, int, int]:
        """第二段短事务：校验租约与游标，持久化账本、消息、游标并释放租约。"""
        from app.repository.wecom_kf_sync_lease_repo import WecomKfSyncLeaseRepo
        from app.repository.wecom_kf_sync_repo import WecomKfSyncRepo as SyncRepo
        from app.models.session import SessionStatus
        from app.repository.session_repo import SessionRepo
        from app.service.wecom.kf_sync_persist import (
            advance_sync_cursor,
            commit_ledger_pendings,
            filter_collected_by_fresh_ids,
            stage_inbox_messages,
        )

        sync_repo = SyncRepo(db)
        state = await sync_repo.get_state(open_kfid)
        if state.last_cursor != base_cursor:
            raise _StaleSyncLease(
                open_kfid,
                f"同步游标已被其他同步者推进 base={base_cursor} "
                f"current={state.last_cursor}",
            )
        await sync_repo.mark_syncing(open_kfid)
        fresh_ids = await commit_ledger_pendings(db, collected.ledger_pendings or [])
        fresh = filter_collected_by_fresh_ids(collected, fresh_ids)
        for event in fresh.start_events:
            await mark_handoff_event(
                event.external_userid, event.change_type, event.staff_id, db=db
            )
        handoff_user_count = await save_handoff_customer_messages(
            fresh.handoff_customer_messages, db=db
        )
        human_count = await save_servicer_messages(fresh.servicer_messages, db=db)
        for event in fresh.end_events:
            await mark_handoff_event(
                event.external_userid, event.change_type, event.staff_id, db=db
            )
        await stage_inbox_messages(
            db, open_kfid, fresh.user_messages, fresh.nontext_messages
        )
        session_repo = SessionRepo(db)
        for session_id in (fresh.handoff_sessions_to_close or {}).values():
            await session_repo.update_status(
                session_id,
                SessionStatus.CLOSED,
                commit=False,
            )
        await advance_sync_cursor(db, open_kfid, end_cursor)
        released = await WecomKfSyncLeaseRepo(db).complete(
            open_kfid,
            lease_token,
            continuation_cursor=end_cursor if truncated else "",
            has_more=truncated,
        )
        if not released:
            raise _StaleSyncLease(open_kfid, "同步租约已被接管，放弃本次提交")
        if truncated:
            logger.warning(
                "sync_msg 达到最大分页次数 open_kfid=%s，已保存延续状态待后续同步",
                open_kfid,
            )
        return fresh, handoff_user_count, human_count

    async def _fetch_and_classify(
        self,
        open_kfid: str,
        kf_token: str,
        base_cursor: str,
    ) -> tuple[CollectedMessages, str, bool]:
        """事务外分页拉取原始消息并做无账本分类，不写数据库。"""
        cursor = base_cursor
        collected = empty_collected()
        for _ in range(MAX_SYNC_PAGES):
            result = await self._pull_page(kf_token, cursor, open_kfid)
            page = await self._classifier.collect_messages(
                result.get("msg_list", []),
                open_kfid,
                None,
                collected.active_handoff_users,
                collected.ended_handoff_users,
                db=None,
                dry_run=True,
            )
            collected = merge_collected_messages(collected, page)
            cursor = str(result.get("next_cursor") or cursor)
            if not result.get("has_more"):
                return collected, cursor, False
        return collected, cursor, True

    async def _pull_page(
        self,
        kf_token: str,
        cursor: str,
        open_kfid: str,
    ) -> dict:
        """拉取单页消息，失败直接抛出以回滚调用方事务。"""
        try:
            result = await self._client.sync_kf_messages(
                kf_token=kf_token, cursor=cursor
            )
        except Exception as exc:
            logger.error("sync_msg 拉取消息失败: %s", exc)
            raise _SyncPullFailed(open_kfid, str(exc)) from exc

        if result.get("errcode") == 0:
            return result

        error = f"{result.get('errcode')} {result.get('errmsg')}"
        logger.error(
            "sync_msg 返回错误 err=%s %s", result.get("errcode"), result.get("errmsg")
        )
        raise _SyncPullFailed(open_kfid, error)

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
