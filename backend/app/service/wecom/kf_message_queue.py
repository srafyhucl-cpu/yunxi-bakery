"""微信客服异步消息队列 + 后台 Worker。

职责：
- 接收入队请求，立即返回（<1ms）
- 后台循环消费队列，调用 ChatService 处理 AI 对话
- 使用 /kf/send_msg 发送回复（与自建应用的 /message/send 完全独立）
- 解析 UMP 统一媒体协议标记，分离文本和卡片/图片发送

使用方式：
    lifespan startup:  kf_queue.start_worker(chat_service)
    callback 入队:      kf_queue.enqueue(KfIncomingMessage(...))
    lifespan shutdown:   await kf_queue.stop()
"""

import json
from dataclasses import dataclass

from app.database import db_session_scope
from app.logger import setup_logger
from app.service.wecom.base_queue import BaseWeComMessageQueue
from app.repository.inbox_repo import InboxRepo
from app.service.wecom.kf_handoff_checker import DbHandoffSessionChecker
from app.service.wecom.kf_card_sender import send_kf_card
from app.service.wecom.kf_message_preprocessor import preprocess_kf_message
from app.service.wecom.ump import parse_ump_tags

logger = setup_logger()

# 队列容量上限（满队列时新消息被丢弃）
QUEUE_MAX_SIZE = 1000


@dataclass(frozen=True)
class KfIncomingMessage:
    """微信客服入队消息（不可变数据对象）。"""

    external_userid: str  # 微信客户的 external_userid
    open_kfid: str  # 客服账号 ID
    content: str  # 文本内容（文本消息为原文，非文本消息为占位描述）
    msg_id: str  # 消息唯一 ID
    msgtype: str = "text"  # 消息类型（text/image/voice/video/file/location 等）
    media_id: str = ""  # 非文本消息的素材 ID（用于下载）


class KfMessageQueue(BaseWeComMessageQueue[KfIncomingMessage]):
    """微信客服异步消息队列 + 后台 Worker。"""

    def __init__(self) -> None:
        super().__init__(QUEUE_MAX_SIZE, "微信客服消息队列")
        self._persistent_mode = True

    async def enqueue(self, msg: KfIncomingMessage) -> bool:
        """
        入队（非阻塞）。
        返回 True 表示入队成功，False 表示队列已满。
        """
        async with db_session_scope():
            await InboxRepo().enqueue(
                "wecom_kf",
                self._persistent_message_key(msg),
                json.dumps(msg.__dict__, ensure_ascii=False),
            )
        return True

    async def _process_one(self, msg: KfIncomingMessage) -> None:
        """
        处理单条客服消息的完整流程：
        1. 非文本消息处理：图片→下载+识别，其他→兜底提示
        2. 文本/图片消息：调用 ChatService 进行 AI 对话
        3. 解析回复中的 UMP 标记（卡片/图片）
        4. 通过 /kf/send_msg 发送纯文本和链接消息
        """
        if self._chat_service is None:
            logger.error("ChatService 未注入，无法处理客服消息")
            return

        from app.database import db_session_scope
        from app.service.wecom.client import get_wecom_client

        client = get_wecom_client()

        if await self._should_skip_auto_reply(client, msg.external_userid):
            logger.info(
                "客服会话处于人工接待或不可回复状态，跳过自动回复 user=%s",
                msg.external_userid,
            )
            return

        prepared_message = await preprocess_kf_message(client, msg)
        if prepared_message is None:
            return
        effective_content = prepared_message.content
        image_base64 = prepared_message.image_base64

        # 确保会话处于可发消息状态（企微限制：非智能助手状态无法API发送）
        await self._sync_local_session_before_reply(client, msg.external_userid)
        can_send = await client.ensure_kf_session_active(msg.external_userid)
        if not can_send:
            logger.info("客服会话不可用，跳过回复 user=%s", msg.external_userid)
            return

        # Worker 绕过 API 层直接调用 service，需自行提供数据库上下文
        async with db_session_scope():
            # 处理前同步 session 状态与企微实际状态
            # 场景：之前转人工后企微会话已结束（state=4），用户重新发消息
            # 触发企微创建新会话（state=0/1），但数据库 session.status 还是 transfer_pending
            # 此时需要重置 session 为 active，让 AI 能正常回复
            from app.models.session import SessionStatus
            from app.repository.session_repo import SessionRepo

            session_repo = SessionRepo()
            session = await session_repo.get_active(msg.external_userid, "wecom_kf")
            if session and session.status in (
                "transfer_pending",
                "human_service",
            ):
                # 查询企微实际会话状态
                kf_state = await client.get_kf_service_state(msg.external_userid)
                # 企微状态 0(未处理)、1(智能助手) 或 4(已结束)
                # 说明旧的人工会话已结束，应重置 session 让 AI 继续服务
                if kf_state is not None and kf_state in (0, 1, 4):
                    await session_repo.update_status(session.id, SessionStatus.ACTIVE)
                    logger.info(
                        "企微会话已重建(state=%d)，重置session %s 为active",
                        kf_state,
                        session.id,
                    )

            reply = await self._chat_service.handle_message(
                channel="wecom_kf",  # 用独立渠道标识区分来源
                user_id=msg.external_userid,
                content=effective_content,
                channel_msg_id=msg.msg_id,
                image_base64=image_base64 or None,
            )

            if not reply:
                return

            # 处理完 AI 回复后，检查 session 是否因转人工而变为人工状态
            # 如果是，则通知企微将会话切换为人工接待模式（service_state=3）
            from app.repository.session_repo import SessionRepo

            session_repo = SessionRepo()
            session = await session_repo.get_active(msg.external_userid, "wecom_kf")
            if session and session.status in (
                "transfer_pending",
                "human_service",
            ):
                logger.info(
                    "会话已进入人工状态(%s)，切换企微为人工接待 mode user=%s",
                    session.status,
                    msg.external_userid,
                )
                trans_result = await client._trans_service_state(
                    msg.external_userid,
                    3,
                )
                if not trans_result:
                    logger.error("切换人工接待模式失败 user=%s", msg.external_userid)

        # 解析 UMP 标记，分离纯文本和卡片/图片
        clean_text, ump_tags = parse_ump_tags(reply)

        # 发送纯文本（如果解析后还有内容）
        if clean_text:
            result = await client.send_kf_text(msg.external_userid, clean_text)
            if result.get("errcode") != 0:
                logger.error(
                    "客服文本回复发送失败 user=%s err=%s",
                    msg.external_userid,
                    result.get("errmsg"),
                )

        # 发送 UMP 卡片（type=card 用 link 图文链接消息）
        for ump in ump_tags:
            ump_type = ump.get("type", "")
            if ump_type == "card":
                await send_kf_card(client, msg.external_userid, ump)
            elif ump_type == "image":
                logger.debug("UMP image 暂不单独发送（图片已内置在 card 中）")

    async def _sync_local_session_before_reply(
        self, client, external_userid: str
    ) -> None:
        from app.database import db_session_scope
        from app.models.session import SessionStatus
        from app.repository.session_repo import SessionRepo

        async with db_session_scope():
            session_repo = SessionRepo()
            session = await session_repo.get_active(external_userid, "wecom_kf")
            if session is None or session.status not in (
                "transfer_pending",
                "human_service",
            ):
                return
            kf_state = await client.get_kf_service_state(external_userid)
            if kf_state is not None and kf_state in (0, 1, 4):
                await session_repo.update_status(session.id, SessionStatus.ACTIVE)
                logger.info(
                    "WeCom KF session state=%d, reset local session %s to active",
                    kf_state,
                    session.id,
                )

    async def _should_skip_auto_reply(self, client, external_userid: str) -> bool:
        if not external_userid:
            return True

        service_state_getter = getattr(client, "get_kf_service_state", None)
        handoff_checker = DbHandoffSessionChecker(service_state_getter)
        if await handoff_checker.is_handoff_user(external_userid):
            return True

        return not await client.ensure_kf_session_active(external_userid)

    def _message_log_context(self, msg: KfIncomingMessage) -> str:
        return f"user={msg.external_userid} msg_id={msg.msg_id}"

    def _persistent_message_key(self, msg: KfIncomingMessage) -> str:
        return f"wecom_kf:{msg.msg_id}"

    async def _claim_persisted_message(self) -> KfIncomingMessage | None:
        async with db_session_scope():
            row = await InboxRepo().claim("wecom_kf")
        if row is None:
            return None
        return KfIncomingMessage(**json.loads(row["payload_json"]))

    async def _mark_persisted_processed(self, message_key: str) -> None:
        async with db_session_scope():
            await InboxRepo().mark_processed(message_key)

    async def _mark_persisted_failed(self, message_key: str, error: Exception) -> None:
        async with db_session_scope():
            await InboxRepo().mark_failed(message_key, str(error))


# ── 全局单例 ────────────────────────────────────────────────
kf_queue = KfMessageQueue()
