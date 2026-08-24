from dataclasses import dataclass
from base64 import b64encode
from types import SimpleNamespace

import pytest

from app.service import chat_message_flow as chat_message_flow_module
from app.service import chat_ai_loop as chat_ai_loop_module
from app.service.agents.customer.support import build_transfer_handler
from app.service.agents.customer.tool_messages import (
    ToolExecutionContext,
)
from app.models.message import Message, MessageRole
from app.models.customer_profile import CustomerProfile
from app.models.session import Session, SessionStatus
from app.models.session_scope import SessionScope
from app.service.chat import TRANSFER_REPLY
from app.service.chat_ai_loop import (
    AiConversationLoopDependencies,
    AiConversationLoopRequest,
    run_ai_conversation_loop,
)
from app.service.chat_context import (
    prepare_ai_conversation_messages,
    prepare_chat_context,
)
from app.service.chat_context_budget import (
    BUDGET_PRESSURE_LEVEL_CRITICAL,
    BUDGET_PRESSURE_LEVEL_NORMAL,
    BUDGET_PRESSURE_LEVEL_WATCH,
    build_chat_context_budget_snapshot,
    record_tool_context_budget_delta,
)
from app.service.chat_intent import IntentDetectionResult, build_history_text
from app.service.chat_message_flow import (
    ChatMessageRequest,
    ChatMessageFlowDependencies,
    complete_ai_reply,
    handle_transfer_intent,
    run_ai_reply_loop,
)
from app.service.conversation_summary_scheduler import (
    ConversationSummaryAfterReplyRequest,
)
from app.service.llm.constants import LLM_FAILURE_REASON_KEY
from app.service.llm import provider as provider_module
from app.service.llm.provider import select_llm_model
from app.service.chat_multimodal import (
    apply_multimodal_image_message,
    normalize_image_data_uri,
)
from app.service.chat_reply import postprocess_reply, record_reply_latency
from app.service.chat_transfer import (
    HumanTransferContext,
    build_transfer_summary_fallback,
    request_human_transfer,
)
from app.service.llm.intent import IntentType


def test_build_history_text_keeps_recent_dialog_and_truncates_content() -> None:
    history = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
        {"role": "tool", "content": "tool result"},
        {"role": "user", "content": "third"},
        {"role": "assistant", "content": "A" * 100},
        {"role": "user", "content": "fourth"},
    ]

    history_text = build_history_text(history)

    assert "system" not in history_text
    assert "tool result" not in history_text
    assert "first" not in history_text
    assert "用户：third" in history_text
    assert "AI：" + ("A" * 80) in history_text
    assert "用户：fourth" in history_text


@dataclass
class _TransferCall:
    session_id: str
    user_id: str
    reason: str
    summary: str


class _FakeTransferManager:
    def __init__(self) -> None:
        self.calls: list[_TransferCall] = []

    async def request_transfer(
        self, session_id: str, user_id: str, reason: str = "", summary: str = ""
    ) -> object:
        self.calls.append(
            _TransferCall(
                session_id=session_id,
                user_id=user_id,
                reason=reason,
                summary=summary,
            )
        )
        return object()


class _FakeSessionRepo:
    def __init__(self) -> None:
        self.updated: list[tuple[str, SessionStatus]] = []
        self.extra_updates: list[tuple[str, str]] = []

    async def update_status(self, session_id: str, status: SessionStatus) -> None:
        self.updated.append((session_id, status))

    async def update_extra(self, session_id: str, extra_info: str) -> None:
        self.extra_updates.append((session_id, extra_info))


class _FakeMessageRepo:
    def __init__(self) -> None:
        self.saved: list[Message] = []

    async def save(self, message: Message) -> None:
        self.saved.append(message)


class _FakeAnalyticsRepo:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def add_event(self, **kwargs: object) -> None:
        self.events.append(kwargs)


class _FakeKnowledgeRetriever:
    def __init__(self) -> None:
        self.search_calls: list[tuple[str, int]] = []
        self.keyword_calls: list[tuple[str, int]] = []

    async def search(self, query: str, limit: int = 8) -> list:
        self.search_calls.append((query, limit))
        return []

    async def search_keyword_only(self, query: str, limit: int = 8) -> list:
        self.keyword_calls.append((query, limit))
        return []


class _FakeLangChainRetriever:
    def __init__(self, documents: list[object]) -> None:
        self.documents = documents
        self.queries: list[str] = []

    async def ainvoke(self, query: str) -> list[object]:
        self.queries.append(query)
        return self.documents


class _FakeLangChainRetrieverAdapter:
    def __init__(self, retriever: _FakeLangChainRetriever) -> None:
        self.retriever = retriever

    def as_retriever(self) -> _FakeLangChainRetriever:
        return self.retriever


class _FakeConversationSummaryRepo:
    def __init__(self, summary_text: str = "") -> None:
        self.summary_text = summary_text
        self.calls: list[str] = []

    async def get_active(self, session_id: str) -> object | None:
        self.calls.append(session_id)
        if not self.summary_text:
            return None
        return SimpleNamespace(summary_text=self.summary_text)


async def _fake_alerter(message: str) -> None:
    raise AssertionError(message)


def _build_flow_dependencies(
    session_repo: object,
    message_repo: object,
    transfer_mgr: object,
    analytics_repo: object | None = None,
    schedule_conversation_summary: object | None = None,
) -> ChatMessageFlowDependencies:
    analytics = analytics_repo or _FakeAnalyticsRepo()
    return ChatMessageFlowDependencies(
        session_mgr=object(),
        session_repo=session_repo,
        message_repo=message_repo,
        transfer_mgr=transfer_mgr,
        analytics_repo=analytics,
        ai_loop_dependencies=AiConversationLoopDependencies(
            session_mgr=object(),
            knowledge=object(),
            transfer_mgr=transfer_mgr,
            session_repo=session_repo,
            youzan_client=object(),
            fallback_reply="fallback",
            timeout_reply="timeout",
            failure_alerter=_fake_alerter,
        ),
        fallback_reply="fallback",
        transfer_reply=TRANSFER_REPLY,
        auto_transfer_reply="auto transfer reply",
        schedule_conversation_summary=schedule_conversation_summary,
    )


@pytest.mark.asyncio
async def test_handle_transfer_intent_updates_state_and_saves_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transfer_mgr = _FakeTransferManager()
    session_repo = _FakeSessionRepo()
    message_repo = _FakeMessageRepo()
    session = Session(id="session-1", channel="youzan", user_id="buyer-1")

    async def fake_summary(reason: str, history_text: str) -> str:
        return f"客户请求人工接待：{reason}"

    monkeypatch.setattr(
        "app.service.chat_transfer.build_transfer_summary", fake_summary
    )

    reply = await handle_transfer_intent(
        dependencies=_build_flow_dependencies(
            session_repo=session_repo,
            message_repo=message_repo,
            transfer_mgr=transfer_mgr,
            analytics_repo=object(),
        ),
        session=session,
        user_id="buyer-1",
        reason="need human support",
        history_text="old dialog " * 100,
    )

    assert reply == TRANSFER_REPLY
    assert transfer_mgr.calls[0].session_id == "session-1"
    assert transfer_mgr.calls[0].user_id == "buyer-1"
    assert transfer_mgr.calls[0].reason == "need human support"
    assert "need human support" in transfer_mgr.calls[0].summary
    assert len(transfer_mgr.calls[0].summary) <= 200
    assert session_repo.updated == [("session-1", SessionStatus.TRANSFER_PENDING)]
    assert (
        SessionScope.BOT_THEN_HANDOFF_PARTIAL.value in session_repo.extra_updates[0][1]
    )
    assert len(message_repo.saved) == 1
    assert message_repo.saved[0].role == MessageRole.ASSISTANT
    assert message_repo.saved[0].content == TRANSFER_REPLY


def test_postprocess_reply_removes_markdown_marks() -> None:
    reply = postprocess_reply(
        "# title\n**hello** __ok__ `code`\n> quoted reply",
        user_content="normal",
    )

    assert reply == "title\nhello ok code\nquoted reply"


@pytest.mark.asyncio
async def test_complete_ai_reply_auto_transfers_on_llm_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transfer_mgr = _FakeTransferManager()
    session_repo = _FakeSessionRepo()
    message_repo = _FakeMessageRepo()
    analytics_repo = _FakeAnalyticsRepo()
    session = Session(id="session-1", channel="youzan", user_id="buyer-1")
    dependencies = _build_flow_dependencies(
        session_repo=session_repo,
        message_repo=message_repo,
        transfer_mgr=transfer_mgr,
        analytics_repo=analytics_repo,
    )

    async def fake_summary(reason: str, history_text: str) -> str:
        return f"handoff: {reason}"

    async def fake_run_ai_conversation_loop(
        dependencies: object,
        request: AiConversationLoopRequest,
    ) -> str:
        assert request.timing is not None
        request.timing[LLM_FAILURE_REASON_KEY] = "llm_api_error"
        return "fallback"

    monkeypatch.setattr(
        "app.service.chat_transfer.build_transfer_summary", fake_summary
    )
    monkeypatch.setattr(
        chat_message_flow_module,
        "run_ai_conversation_loop",
        fake_run_ai_conversation_loop,
    )

    reply = await complete_ai_reply(
        dependencies=dependencies,
        request=ChatMessageRequest(
            channel="youzan",
            user_id="buyer-1",
            content="help me choose a cake",
        ),
        session=session,
        intent_result=IntentDetectionResult(
            intent=IntentType.PRODUCT_CONSULTATION,
            history=[],
            history_text="用户：help me choose a cake",
            started_at=1.0,
            finished_at=1.1,
            intent_ms=100,
        ),
    )

    assert reply == "auto transfer reply"
    assert transfer_mgr.calls[0].session_id == "session-1"
    assert transfer_mgr.calls[0].user_id == "buyer-1"
    assert "llm_api_error" in transfer_mgr.calls[0].reason
    assert session_repo.updated == [("session-1", SessionStatus.TRANSFER_PENDING)]
    assert message_repo.saved[0].content == "auto transfer reply"
    event_types = {event["event_type"] for event in analytics_repo.events}
    assert "ai_failure_auto_transfer" in event_types
    assert "reply_latency" in event_types
    assert "llm_api_error" in str(analytics_repo.events)


@pytest.mark.asyncio
async def test_complete_ai_reply_schedules_summary_after_reply_saved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transfer_mgr = _FakeTransferManager()
    session_repo = _FakeSessionRepo()
    message_repo = _FakeMessageRepo()
    analytics_repo = _FakeAnalyticsRepo()
    scheduled_requests: list[ConversationSummaryAfterReplyRequest] = []

    def fake_schedule(request: ConversationSummaryAfterReplyRequest) -> bool:
        assert message_repo.saved[0].content == "guarded reply"
        assert analytics_repo.events[0]["event_type"] == "reply_latency"
        scheduled_requests.append(request)
        return True

    dependencies = _build_flow_dependencies(
        session_repo=session_repo,
        message_repo=message_repo,
        transfer_mgr=transfer_mgr,
        analytics_repo=analytics_repo,
        schedule_conversation_summary=fake_schedule,
    )
    session = Session(id="session-1", channel="youzan", user_id="buyer-1")

    async def fake_run_ai_conversation_loop(
        dependencies: object,
        request: AiConversationLoopRequest,
    ) -> str:
        assert request.timing is not None
        request.timing["context_budget"] = {"needs_session_summary_candidate": True}
        return "guarded reply"

    monkeypatch.setattr(
        chat_message_flow_module,
        "run_ai_conversation_loop",
        fake_run_ai_conversation_loop,
    )

    reply = await complete_ai_reply(
        dependencies=dependencies,
        request=ChatMessageRequest(
            channel="youzan",
            user_id="buyer-1",
            content="我想继续确认配送",
        ),
        session=session,
        intent_result=IntentDetectionResult(
            intent=IntentType.PRODUCT_CONSULTATION,
            history=[],
            history_text="用户：我想继续确认配送",
            started_at=1.0,
            finished_at=1.1,
            intent_ms=100,
        ),
    )

    assert reply == "guarded reply"
    assert len(scheduled_requests) == 1
    assert scheduled_requests[0].session is session
    assert scheduled_requests[0].context_budget == {
        "needs_session_summary_candidate": True
    }


@pytest.mark.asyncio
async def test_record_reply_latency_keeps_expected_meta() -> None:
    analytics_repo = _FakeAnalyticsRepo()
    session = Session(id="session-1", channel="youzan", user_id="buyer-1")

    await record_reply_latency(
        analytics_repo=analytics_repo,
        session=session,
        user_id="buyer-1",
        channel="youzan",
        intent=IntentType.PRODUCT_CONSULTATION,
        intent_ms=12,
        timing={
            "rag_ms": 34,
            "llm_ms": 56,
            "tool_rounds": 1,
            "context_budget": {"history_message_count": 2},
        },
        loop_ms=78,
        total_ms=90,
    )

    assert len(analytics_repo.events) == 1
    event = analytics_repo.events[0]
    assert event["session_id"] == "session-1"
    assert event["buyer_id"] == "buyer-1"
    assert event["event_type"] == "reply_latency"
    assert '"intent": "PRODUCT_CONSULTATION"' in str(event["meta_data"])
    assert '"tool_rounds": 1' in str(event["meta_data"])
    assert '"context_budget": {"history_message_count": 2}' in str(event["meta_data"])


@pytest.mark.asyncio
async def test_prepare_chat_context_builds_system_message_and_preserves_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    knowledge = _FakeKnowledgeRetriever()
    history = [{"role": "user", "content": "hello"}]

    async def fake_rewrite_query(user_query: str, history: str = "") -> str:
        return f"rewritten:{user_query}:{history}"

    monkeypatch.setattr(
        "app.service.chat_context.rewrite_query",
        fake_rewrite_query,
    )

    chat_context = await prepare_chat_context(
        knowledge=knowledge,
        user_query="cake",
        history_text="old",
        intent=IntentType.PRODUCT_CONSULTATION,
        history=history,
    )

    assert knowledge.search_calls == [("rewritten:cake:old", 8)]
    assert chat_context.messages[0]["role"] == "system"
    assert chat_context.messages[1:] == history
    assert isinstance(chat_context.rag_ms, int)
    assert chat_context.context_budget is not None
    assert chat_context.context_budget.history_message_count == 1
    assert chat_context.context_budget.knowledge_entry_limit == 8
    assert chat_context.context_budget.customer_profile_present is False
    assert chat_context.context_budget.tool_result_message_count == 0
    assert chat_context.context_budget.budget_pressure_level == (
        BUDGET_PRESSURE_LEVEL_NORMAL
    )
    assert chat_context.context_budget.needs_session_summary_candidate is False


@pytest.mark.asyncio
async def test_prepare_chat_context_uses_hybrid_direct_search_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    knowledge = _FakeKnowledgeRetriever()
    history = [{"role": "user", "content": "hello"}]
    adapter_calls: list[object] = []

    async def fake_rewrite_query(user_query: str, history: str = "") -> str:
        return f"rewritten:{user_query}"

    def fake_build_adapter(*args: object, **kwargs: object) -> object:
        adapter_calls.append((args, kwargs))
        return _FakeLangChainRetrieverAdapter(_FakeLangChainRetriever([]))

    monkeypatch.setattr(
        "app.service.chat_context.rewrite_query",
        fake_rewrite_query,
    )
    monkeypatch.setattr(
        "app.service.chat_context.build_langchain_knowledge_retriever_for_mode",
        fake_build_adapter,
    )
    monkeypatch.setattr(
        "app.service.chat_context.settings.RAG_RETRIEVAL_MODE", "hybrid"
    )

    await prepare_chat_context(
        knowledge=knowledge,
        user_query="cake",
        history_text="old",
        intent=IntentType.PRODUCT_CONSULTATION,
        history=history,
    )

    assert knowledge.search_calls == []
    assert adapter_calls == [((knowledge,), {"mode": "hybrid", "limit": 8})]


@pytest.mark.asyncio
async def test_prepare_chat_context_uses_langchain_retriever_for_planned_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    knowledge = _FakeKnowledgeRetriever()
    history = [{"role": "user", "content": "hello"}]
    fake_document = SimpleNamespace(
        page_content="命中的知识正文",
        metadata={
            "knowledge_id": 12,
            "title": "命中知识",
            "category": "faq",
            "content_type": "faq",
            "audience": "customer",
            "review_status": "published",
            "priority": 3,
        },
    )
    fake_retriever = _FakeLangChainRetriever([fake_document])
    adapter_calls: list[dict[str, object]] = []

    async def fake_rewrite_query(user_query: str, history: str = "") -> str:
        return f"rewritten:{user_query}"

    def fake_build_adapter(*args: object, **kwargs: object) -> object:
        adapter_calls.append(kwargs)
        return _FakeLangChainRetrieverAdapter(fake_retriever)

    monkeypatch.setattr(
        "app.service.chat_context.rewrite_query",
        fake_rewrite_query,
    )
    monkeypatch.setattr(
        "app.service.chat_context.build_langchain_knowledge_retriever_for_mode",
        fake_build_adapter,
    )
    monkeypatch.setattr(
        "app.service.chat_context.settings.RAG_RETRIEVAL_MODE",
        "planned-hybrid",
    )

    chat_context = await prepare_chat_context(
        knowledge=knowledge,
        user_query="cake",
        history_text="old",
        intent=IntentType.PRODUCT_CONSULTATION,
        history=history,
    )

    assert knowledge.search_calls == []
    assert adapter_calls == [{"mode": "planned-hybrid", "limit": 8}]
    assert fake_retriever.queries == ["rewritten:cake"]
    assert chat_context.knowledge_entry_ids == (12,)
    assert "命中的知识正文" in chat_context.guard_source_text


@pytest.mark.asyncio
async def test_prepare_chat_context_injects_summary_without_replacing_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    knowledge = _FakeKnowledgeRetriever()
    history = [
        {"role": "user", "content": "最近一句客户追问配送"},
        {"role": "assistant", "content": "最近一句客服回复"},
    ]

    async def fake_rewrite_query(user_query: str, history: str = "") -> str:
        return user_query

    monkeypatch.setattr(
        "app.service.chat_context.rewrite_query",
        fake_rewrite_query,
    )

    chat_context = await prepare_chat_context(
        knowledge=knowledge,
        user_query="配送还来得及吗",
        history_text="用户：配送还来得及吗",
        intent=IntentType.PRODUCT_CONSULTATION,
        history=history,
        conversation_summary_text="客户早前说明想要低糖生日蛋糕，配送时间待确认。",
    )

    system_prompt = chat_context.messages[0]["content"]
    assert "【本会话早期摘要】" in system_prompt
    assert "低糖生日蛋糕" in system_prompt
    assert "订单、库存、配送、价格仍以工具和知识库为准" in system_prompt
    assert chat_context.messages[1:] == history
    assert chat_context.context_budget is not None
    assert chat_context.context_budget.conversation_summary_present is True
    assert chat_context.context_budget.conversation_summary_token_estimate > 0
    assert (
        chat_context.context_budget.conversation_summary_policy
        == "read_only_short_term_context"
    )


@pytest.mark.asyncio
async def test_prepare_ai_conversation_messages_records_context_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    knowledge = _FakeKnowledgeRetriever()
    history = [{"role": "user", "content": "hello"}]
    timing: dict[str, object] = {}
    profile = CustomerProfile(
        id="profile-1",
        channel="youzan",
        user_id="buyer-1",
        display_name="小云",
    )
    session = Session(id="session-1", channel="youzan", user_id="buyer-1")

    async def fake_rewrite_query(user_query: str, history: str = "") -> str:
        return f"rewritten:{user_query}:{history}"

    monkeypatch.setattr(
        "app.service.chat_context.rewrite_query",
        fake_rewrite_query,
    )

    await prepare_ai_conversation_messages(
        session_mgr=object(),
        knowledge=knowledge,
        session=session,
        user_query="cake",
        intent=IntentType.PRODUCT_CONSULTATION,
        timing=timing,
        history=history,
        history_text="old",
        image_base64=None,
        customer_profile=profile,
    )

    context_budget = timing["context_budget"]
    assert isinstance(context_budget, dict)
    assert context_budget["history_message_count"] == 1
    assert context_budget["customer_profile_present"] is True
    assert context_budget["long_term_memory_policy"] == "read_only_prompt_hints"
    assert context_budget["budget_pressure_level"] == BUDGET_PRESSURE_LEVEL_NORMAL
    assert context_budget["needs_session_summary_candidate"] is False
    assert context_budget["summary_candidate_policy"] == (
        "observe_only_no_summary_write"
    )
    assert context_budget["conversation_summary_present"] is False


def test_chat_context_budget_marks_summary_candidate_by_history_pressure() -> None:
    snapshot = build_chat_context_budget_snapshot(
        system_prompt="system",
        history=[{"role": "user", "content": "长" * 6000}],
        knowledge_entries=[],
        knowledge_entry_limit=8,
        customer_profile=None,
    )

    assert snapshot.history_budget_ratio >= 0.7
    assert snapshot.prompt_budget_ratio >= snapshot.history_budget_ratio
    assert snapshot.budget_pressure_level in {
        BUDGET_PRESSURE_LEVEL_WATCH,
        BUDGET_PRESSURE_LEVEL_CRITICAL,
    }
    assert snapshot.needs_session_summary_candidate is True
    assert snapshot.summary_candidate_policy == "observe_only_no_summary_write"


def test_record_tool_context_budget_delta_refreshes_prompt_pressure() -> None:
    timing: dict[str, object] = {
        "context_budget": {
            "history_token_estimate": 12,
            "total_prompt_token_estimate": 100,
        }
    }

    record_tool_context_budget_delta(
        timing,
        [{"role": "tool", "content": "长" * 8000}],
    )

    context_budget = timing["context_budget"]
    assert isinstance(context_budget, dict)
    assert context_budget["prompt_budget_ratio"] >= 0.9
    assert context_budget["budget_pressure_level"] == BUDGET_PRESSURE_LEVEL_CRITICAL
    assert context_budget["needs_session_summary_candidate"] is False
    assert context_budget["summary_candidate_policy"] == (
        "observe_only_no_summary_write"
    )


def test_normalize_image_data_uri_detects_png() -> None:
    png_base64 = b64encode(b"\x89PNG\r\n\x1a\nfake").decode("ascii")

    data_uri = normalize_image_data_uri(png_base64)

    assert data_uri.startswith("data:image/png;base64,")
    assert data_uri.endswith(png_base64)


def test_apply_multimodal_image_message_replaces_last_user_message() -> None:
    jpeg_base64 = b64encode(b"\xff\xd8\xff\xe0fake").decode("ascii")
    messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "answer"},
        {"role": "user", "content": "last"},
    ]

    apply_multimodal_image_message(messages, jpeg_base64, "session-1")

    assert messages[0]["content"] == "first"
    assert messages[2]["role"] == "user"
    assert messages[2]["content"][0]["type"] == "image_url"
    assert messages[2]["content"][0]["image_url"]["url"].startswith(
        "data:image/jpeg;base64,"
    )
    text_part = messages[2]["content"][1]
    assert text_part["type"] == "text"
    assert "提取对烘焙客服有用的信息" in text_part["text"]
    assert "用户文字：last" in text_part["text"]


def test_select_llm_model_uses_default_for_text() -> None:
    assert select_llm_model(has_image=False) == ""


def test_select_llm_model_uses_vision_and_chat_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_module.settings, "MIMO_VISION_MODEL", "vision-model")
    monkeypatch.setattr(provider_module.settings, "MIMO_CHAT_MODEL", "chat-model")

    assert select_llm_model(has_image=True) == "vision-model"

    monkeypatch.setattr(provider_module.settings, "MIMO_VISION_MODEL", "")
    assert select_llm_model(has_image=True) == "chat-model"


@pytest.mark.asyncio
async def test_run_ai_conversation_loop_prepares_messages_and_invokes_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    session = Session(id="session-1", channel="youzan", user_id="buyer-1")

    class FakeCustomerGraphService:
        def __init__(self, dependencies: object) -> None:
            captured["graph_dependencies"] = dependencies

        async def answer(self, request: object) -> str:
            captured["graph_request"] = request
            return "reply"

    monkeypatch.setattr(
        chat_ai_loop_module,
        "CustomerAgentGraphService",
        FakeCustomerGraphService,
    )

    reply = await run_ai_conversation_loop(
        AiConversationLoopDependencies(
            session_mgr=object(),
            knowledge=object(),
            transfer_mgr=object(),
            session_repo=object(),
            youzan_client=object(),
            fallback_reply="fallback",
            timeout_reply="timeout",
            failure_alerter=_fake_alerter,
            conversation_summary_repo=_FakeConversationSummaryRepo(
                "客户早前想要低糖蛋糕。"
            ),
        ),
        AiConversationLoopRequest(
            session=session,
            user_query="cake",
            intent=IntentType.PRODUCT_CONSULTATION,
            timing={},
            history=[],
            history_text="old",
            image_base64="image",
        ),
    )

    assert reply == "reply"
    graph_dependencies = captured["graph_dependencies"]
    assert graph_dependencies.conversation_summary_repo.summary_text == (
        "客户早前想要低糖蛋糕。"
    )
    graph_request = captured["graph_request"]
    assert graph_request.session is session
    assert graph_request.user_query == "cake"
    assert graph_request.history_text == "old"
    assert graph_request.image_base64 == "image"


@pytest.mark.asyncio
async def test_run_ai_reply_loop_passes_customer_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    profile = CustomerProfile(id="p-1", channel="youzan", user_id="buyer-1")
    dependencies = ChatMessageFlowDependencies(
        session_mgr=object(),
        session_repo=object(),
        message_repo=object(),
        transfer_mgr=object(),
        analytics_repo=object(),
        fallback_reply="fallback",
        transfer_reply="transfer",
        auto_transfer_reply="auto transfer",
        ai_loop_dependencies=AiConversationLoopDependencies(
            session_mgr=object(),
            knowledge=object(),
            transfer_mgr=object(),
            session_repo=object(),
            youzan_client=object(),
            fallback_reply="fallback",
            timeout_reply="timeout",
            failure_alerter=_fake_alerter,
        ),
        customer_profile_repo=object(),
    )
    session = Session(id="session-1", channel="youzan", user_id="buyer-1")

    async def fake_load_customer_profile(
        customer_profile_repo: object,
        channel: str,
        user_id: str,
    ) -> CustomerProfile | None:
        captured["load_args"] = (channel, user_id, customer_profile_repo)
        return profile

    async def fake_run_ai_conversation_loop(
        dependencies: object,
        request: AiConversationLoopRequest,
    ) -> str:
        captured["request_profile"] = request.customer_profile
        return "reply"

    monkeypatch.setattr(
        chat_message_flow_module,
        "load_customer_profile",
        fake_load_customer_profile,
    )
    monkeypatch.setattr(
        chat_message_flow_module,
        "run_ai_conversation_loop",
        fake_run_ai_conversation_loop,
    )

    reply = await run_ai_reply_loop(
        dependencies,
        ChatMessageRequest(channel="youzan", user_id="buyer-1", content="hello"),
        session,
        IntentDetectionResult(
            intent=IntentType.PRODUCT_CONSULTATION,
            history=[],
            history_text="history",
            started_at=0.0,
            finished_at=0.0,
            intent_ms=0,
        ),
        {},
    )

    assert reply == "reply"
    assert captured["load_args"][:2] == ("youzan", "buyer-1")
    assert captured["request_profile"] is profile


@pytest.mark.asyncio
async def test_transfer_handler_returns_canonical_tool_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transfer_mgr = _FakeTransferManager()
    session_repo = _FakeSessionRepo()
    session = Session(id="session-1", channel="youzan", user_id="buyer-1")

    async def fake_summary(reason: str, history_text: str) -> str:
        return f"客户请求人工接待：{reason}"

    monkeypatch.setattr(
        "app.service.chat_transfer.build_transfer_summary", fake_summary
    )

    tool_context = ToolExecutionContext(
        session=session,
        history_text="old dialog " * 100,
        transfer_mgr=transfer_mgr,
        session_repo=session_repo,
        knowledge=object(),
        youzan_client=object(),
    )
    result = await build_transfer_handler(tool_context)("need staff")

    assert transfer_mgr.calls[0].reason == "need staff"
    assert session_repo.updated == [("session-1", SessionStatus.TRANSFER_PENDING)]
    assert '"status": "success"' in result


@pytest.mark.asyncio
async def test_request_human_transfer_updates_state_and_truncates_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transfer_mgr = _FakeTransferManager()
    session_repo = _FakeSessionRepo()
    session = Session(id="session-1", channel="youzan", user_id="buyer-1")

    async def fake_summary(reason: str, history_text: str) -> str:
        return f"客户请求人工接待：{reason}"

    monkeypatch.setattr(
        "app.service.chat_transfer.build_transfer_summary", fake_summary
    )

    created = await request_human_transfer(
        HumanTransferContext(
            session=session,
            user_id="buyer-1",
            reason="need staff",
            history_text="old dialog " * 100,
            transfer_mgr=transfer_mgr,
            session_repo=session_repo,
        )
    )

    assert created is True
    assert transfer_mgr.calls[0].session_id == "session-1"
    assert transfer_mgr.calls[0].user_id == "buyer-1"
    assert transfer_mgr.calls[0].reason == "need staff"
    assert "need staff" in transfer_mgr.calls[0].summary
    assert len(transfer_mgr.calls[0].summary) <= 200
    assert session_repo.updated == [("session-1", SessionStatus.TRANSFER_PENDING)]
    assert (
        SessionScope.BOT_THEN_HANDOFF_PARTIAL.value in session_repo.extra_updates[0][1]
    )


def test_build_transfer_summary_fallback_builds_concise_handoff_note() -> None:
    history_text = "\n".join(
        [
            "用户：first",
            "AI：second",
            "用户：想订草莓千层，少糖",
            "AI：确认配送时间",
            "用户：今天下午到，可以转人工吗",
        ]
    )

    summary = build_transfer_summary_fallback("用户要求转人工", history_text)

    assert "低糖" in summary or "少糖" in summary
    assert "AI：确认配送时间" not in summary
    assert len(summary) <= 180
