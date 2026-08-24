"""
核心对话循环。

所有渠道的消息最终汇聚到此模块，并委托到细分服务边界处理。
"""

from app.logger import setup_logger
from app.models.youzan_webhook_event import (
    YouzanWebhookEventCreate,
    YouzanWebhookEventUpdate,
)
from app.repository.message_repo import MessageRepo
from app.repository.session_repo import SessionRepo
from app.repository.transfer_repo import TransferRepo
from app.repository.analytics_repo import AnalyticsRepo
from app.repository.conversation_summary_repo import ConversationSummaryRepo
from app.repository.customer_profile_repo import CustomerProfileRepo
from app.repository.youzan_webhook_event_repo import YouzanWebhookEventRepo
from app.models.message import Message, MessageRole
from app.models.session import SessionCreate
from app.service.chat_ai_loop import (
    AiConversationLoopDependencies,
)
from app.service.agents.trace_sink import AgentTraceSink
from app.service.chat_message_flow import (
    ChatMessageFlowDependencies,
    ChatMessageRequest,
    handle_chat_message,
)
from app.service.chat_reply import (
    save_assistant_reply,
)
from app.service.conversation_summary_scheduler import (
    schedule_conversation_summary_after_reply,
)
from app.service.knowledge_retriever import KnowledgeRetriever
from app.service.session_manager import SessionManager
from app.service.transfer_manager import TransferManager
from app.service.youzan.client import YouzanClient
from app.service.youzan.event_handler import YouzanEventHandler
from app.service.alerting import AlertLevel, alert_service

logger = setup_logger()

# ── 业务常量 ──────────────────────────────────────────────────────────────────
FALLBACK_REPLY = "系统正忙，请稍后再试或联系人工客服。"
# 非文本消息（图片/语音/视频等）兑底提示：不喂给 LLM，直接友好引导用户改发文字。
NONTEXT_FALLBACK_REPLY = "您好~ 我暂时只能识别文字消息，麻烦您用文字描述一下需要咨询的问题，我会尽快为您解答 :)"
TRANSFER_REPLY = "非常抱歉给您带来不好的体验，已为您转接人工客服，请稍候~"


# LLM 连续失败阈值告警器（60 秒内累计 3 次失败触发告警）
_llm_failure_alerter = alert_service.create_threshold_alerter(
    AlertLevel.WARNING,
    "LLM 调用连续失败",
    threshold=3,
    window_seconds=60.0,
)
QUERY_TIMEOUT_REPLY = "正在为您查询，请稍候。如果长时间没有回复，请联系人工客服。"

AI_FAILURE_AUTO_TRANSFER_REPLY = (
    "\u975e\u5e38\u62b1\u6b49\uff0cAI \u5ba2\u670d\u5f53\u524d\u54cd\u5e94\u4e0d\u7a33\u5b9a\uff0c"
    "\u6211\u5df2\u4e3a\u60a8\u8f6c\u63a5\u4eba\u5de5\u5ba2\u670d\u63a5\u7740\u5904\u7406\uff0c\u8bf7\u7a0d\u5019\u3002"
)


class ChatService:
    """AI 对话服务：处理消息、调用 LLM、管理工具调用循环。"""

    def __init__(
        self,
        session_repo: SessionRepo,
        message_repo: MessageRepo,
        transfer_repo: TransferRepo,
        knowledge_retriever: KnowledgeRetriever,
        youzan_client: YouzanClient,
        youzan_webhook_events_repo: YouzanWebhookEventRepo,
        youzan_event_handler: YouzanEventHandler,
        analytics_repo: AnalyticsRepo,
        customer_profile_repo: CustomerProfileRepo | None = None,
        conversation_summary_repo: ConversationSummaryRepo | None = None,
        trace_sink: AgentTraceSink | None = None,
        order_repo=None,
        config_repo=None,
        product_repo=None,
        knowledge_product_repo=None,
        history_repo=None,
    ) -> None:
        self._session_mgr = SessionManager(session_repo, message_repo)
        self._session_repo = session_repo
        self._message_repo = message_repo
        self._transfer_mgr = TransferManager(transfer_repo)
        self._knowledge = knowledge_retriever
        # 显式依赖注入：由组装根传入，避免服务层自行获取持久化连接。
        self._youzan_client = youzan_client
        self._youzan_webhook_events_repo = youzan_webhook_events_repo
        self._youzan_events = youzan_event_handler
        self._analytics_repo = analytics_repo
        self._customer_profile_repo = customer_profile_repo
        self._conversation_summary_repo = conversation_summary_repo
        self._ai_loop_dependencies = AiConversationLoopDependencies(
            session_mgr=self._session_mgr,
            knowledge=self._knowledge,
            transfer_mgr=self._transfer_mgr,
            session_repo=self._session_repo,
            youzan_client=self._youzan_client,
            fallback_reply=FALLBACK_REPLY,
            timeout_reply=QUERY_TIMEOUT_REPLY,
            failure_alerter=_llm_failure_alerter,
            order_repo=order_repo,
            config_repo=config_repo,
            product_repo=product_repo,
            knowledge_product_repo=knowledge_product_repo,
            analytics_repo=self._analytics_repo,
            history_repo=history_repo,
            conversation_summary_repo=self._conversation_summary_repo,
            trace_sink=trace_sink,
        )
        self._message_flow_dependencies = ChatMessageFlowDependencies(
            session_mgr=self._session_mgr,
            session_repo=self._session_repo,
            message_repo=self._message_repo,
            transfer_mgr=self._transfer_mgr,
            analytics_repo=self._analytics_repo,
            customer_profile_repo=self._customer_profile_repo,
            ai_loop_dependencies=self._ai_loop_dependencies,
            fallback_reply=FALLBACK_REPLY,
            transfer_reply=TRANSFER_REPLY,
            auto_transfer_reply=AI_FAILURE_AUTO_TRANSFER_REPLY,
            schedule_conversation_summary=schedule_conversation_summary_after_reply,
        )

    async def create_youzan_webhook_audit(self, event: YouzanWebhookEventCreate) -> int:
        """Record receipt of a Youzan webhook before async business handling."""
        return await self._youzan_webhook_events_repo.create_received(event)

    async def mark_youzan_webhook_processing(
        self, audit_id: int, stage: str = "dispatched"
    ) -> None:
        """Mark a Youzan webhook as dispatched to background processing."""
        await self._youzan_webhook_events_repo.mark_processing(audit_id, stage)

    async def mark_youzan_webhook_result(
        self, audit_id: int, update: YouzanWebhookEventUpdate
    ) -> None:
        """Persist a terminal result for a Youzan webhook."""
        await self._youzan_webhook_events_repo.mark_result(audit_id, update)

    async def has_processed_message(self, channel_msg_id: str) -> bool:
        """Webhook 秒回去重：渠道原始消息 ID 是否已处理（公共接口，避免越层访问 repo）。"""
        return await self._message_repo.has_processed(channel_msg_id)

    async def reply_youzan_nontext_fallback(self, buyer_id: str, msg_id: str) -> None:
        """有赞非文本消息兑底：直接回友好提示，不喂给 LLM（N-6）。"""
        if msg_id and not await self._claim_inbound_message(
            channel="youzan",
            user_id=buyer_id,
            content="[非文本消息]",
            channel_msg_id=msg_id,
        ):
            return
        await self._youzan_client.send_reply(
            buyer_open_id=buyer_id, content=NONTEXT_FALLBACK_REPLY
        )

    async def reply_youzan_hosting_nontext_fallback(
        self, conversation_id: str, msg_id: str
    ) -> None:
        """有赞托管非文本消息兑底：直接按托管会话回复友好提示。"""
        if msg_id and not await self._claim_inbound_message(
            channel="youzan",
            user_id=conversation_id,
            content="[托管非文本消息]",
            channel_msg_id=msg_id,
        ):
            return
        await self._youzan_client.send_hosting_reply(
            conversation_id=conversation_id,
            content=NONTEXT_FALLBACK_REPLY,
            msg_type="text",
        )

    async def _claim_inbound_message(
        self,
        channel: str,
        user_id: str,
        content: str,
        channel_msg_id: str,
        staff_id: str = "",
    ) -> bool:
        """为不进入主对话流的入站消息建立原子幂等账本记录。"""
        session = await self._session_repo.get_or_create(
            SessionCreate(
                id="",
                channel=channel,
                user_id=user_id,
                staff_id=staff_id,
            )
        )
        return await self._message_repo.save_if_new(
            Message(
                id="",
                session_id=session.id,
                role=MessageRole.USER,
                content=content,
                channel_msg_id=channel_msg_id,
            )
        )

    async def handle_message_and_reply_youzan(
        self, buyer_id: str, content: str, msg_id: str
    ) -> None:
        """处理消息，并将 AI 回复通过有赞客户端投递给买家（业务层闭环封装）。"""
        reply = await self.handle_message(
            channel="youzan",
            user_id=buyer_id,
            content=content,
            channel_msg_id=msg_id,
        )
        if reply:
            await self._youzan_client.send_reply(buyer_open_id=buyer_id, content=reply)

    async def handle_youzan_hosting_message(
        self,
        conversation_id: str,
        yz_open_id: str,
        content: str,
        msg_id: str,
    ) -> None:
        """处理有赞客服托管消息，并按托管会话 ID 回复客户。"""
        reply = await self.handle_message(
            channel="youzan",
            user_id=yz_open_id or conversation_id,
            content=content,
            channel_msg_id=msg_id,
        )
        if reply:
            await self._youzan_client.send_hosting_reply(
                conversation_id=conversation_id,
                content=reply,
                msg_type="text",
            )

    async def handle_message(
        self,
        channel: str,
        user_id: str,
        content: str,
        staff_id: str = "",
        channel_msg_id: str = "",
        image_base64: str | None = None,
    ) -> str | None:
        """
        处理用户消息的主入口。

        参数：
            channel: 渠道标识（youzan / wecom_1on1 / wecom_group / wecom_kf）
            user_id: 渠道用户 ID
            content: 消息内容
            staff_id: 所属员工 ID（企微必传）
            channel_msg_id: 渠道原始消息 ID（用于去重）
            image_base64: 图片的 base64 编码数据（多模态识别用，可选）
        返回：
            回复文本，无需回复时返回 None
        """
        return await handle_chat_message(
            self._message_flow_dependencies,
            ChatMessageRequest(
                channel=channel,
                user_id=user_id,
                content=content,
                staff_id=staff_id,
                channel_msg_id=channel_msg_id,
                image_base64=image_base64,
            ),
        )

    async def handle_human_reply(self, session_id: str, content: str) -> None:
        """
        人工客服回复消息。

        参数：
            session_id: 会话 ID
            content: 回复内容
        """
        await save_assistant_reply(self._message_repo, session_id, content)
        logger.info("人工客服回复: session=%s", session_id)

    async def handle_youzan_system_event(
        self,
        payload: dict,
        event_type: str,
        updated_at_str: str,
        msg_id: str,
        audit_id: int | None = None,
    ) -> None:
        """有赞系统事件处理（商品/交易 Webhook），委托至 YouzanEventHandler。"""
        await self._youzan_events.handle_system_event(
            payload, event_type, updated_at_str, msg_id, audit_id
        )
