"""Agent 化 P2 离线质检测试。"""

import asyncio
import json

import aiosqlite
import pytest
from langchain_core.runnables import RunnableLambda

from app.exceptions import LLMError
from app.models.conversation_review import ConversationReview
from app.models.message import Message, MessageRole
from app.models.session_scope import SessionScope, mark_handoff_started
from app.repository.conversation_review_repo import ConversationReviewRepo
from app.repository.customer_profile_repo import CustomerProfileRepo
from app.repository.knowledge_gap_repo import KnowledgeGapRepo
from app.repository.message_repo import MessageRepo
from app.repository.offline_session_repo import OfflineSessionRepo
from app.repository.session_repo import SessionRepo
from app.service.offline import agent_qa_review as qa_review_module
from app.service.offline import agent_knowledge_gap as knowledge_gap_module
from app.service.offline import agent_memory as memory_module
from app.service.offline import scheduler as scheduler_module
from app.service.offline.agent_knowledge_gap import KnowledgeGapAgent
from app.service.offline.agent_memory import MemoryAgent
from app.service.offline.agent_qa_review import QaReviewAgent
from app.service.offline.model_selection import select_offline_review_model
from app.service.offline.orchestrator import OfflineReviewOrchestrator
from app.service.offline.quality_signals import (
    extract_memory_signal,
    extract_review_issues,
)
from app.service.offline.scheduler import OfflineReviewScheduler, _is_night_window


async def test_session_repo_lists_unreviewed_closed_and_transfer_sessions(
    db: aiosqlite.Connection,
) -> None:
    """候选会话只包含未质检的已结束或转人工会话。"""
    await _insert_session(db, "active-1", "active")
    await _insert_session(db, "closed-1", "closed")
    await _insert_session(db, "transfer-1", "transfer_pending")
    await _insert_session(db, "reviewed-1", "closed")
    await db.execute(
        "INSERT INTO conversation_reviews "
        "(session_id, quality_score, issues_json, reviewer_model, reviewed_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("reviewed-1", 90, "[]", "mimo", "2026-06-09 10:00:00"),
    )
    await db.commit()

    sessions = await SessionRepo(db).list_review_candidates()

    assert {session.id for session in sessions} == {"closed-1", "transfer-1"}


async def test_session_repo_retries_invalid_empty_review(
    db: aiosqlite.Connection,
) -> None:
    """0 分且无问题说明的空质检不应阻止会话重新进入候选。"""
    await _insert_session(db, "invalid-review-1", "closed")
    await _insert_session(db, "valid-review-1", "closed")
    await db.executemany(
        "INSERT INTO conversation_reviews "
        "(session_id, quality_score, issues_json, reviewer_model, reviewed_at) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            ("invalid-review-1", 0, "[]", "mimo", "2026-06-09 10:00:00"),
            ("valid-review-1", 100, "[]", "mimo", "2026-06-09 10:00:00"),
        ],
    )
    await db.commit()

    sessions = await SessionRepo(db).list_review_candidates()

    assert {session.id for session in sessions} == {"invalid-review-1"}


async def test_qa_review_agent_writes_conversation_review(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """质检 Agent 应调用 LLM 并把结构化结果落库。"""
    await _insert_session(db, "session-1", "closed")
    await MessageRepo(db).save(
        Message(
            id="msg-1",
            session_id="session-1",
            role=MessageRole.USER,
            content="草莓蛋糕多少钱？",
        )
    )

    async def fake_llm_chat(*_args: object, **_kwargs: object) -> str:
        return '{"quality_score": 82, "issues": ["价格回答需核对"]}'

    monkeypatch.setattr(qa_review_module, "_invoke_review_chain", fake_llm_chat)
    agent = _build_agent(db)

    reviews = await agent.run()
    stored = await ConversationReviewRepo(db).list_by_session("session-1")

    assert [review.quality_score for review in reviews] == [82]
    assert stored[0].issues_json == '["价格回答需核对"]'


async def test_qa_review_agent_repairs_empty_low_score(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """低分但无问题说明时应重试并只写入修复后的质检。"""
    await _insert_session(db, "session-repair", "closed")
    await MessageRepo(db).save(
        Message(
            id="msg-repair",
            session_id="session-repair",
            role=MessageRole.USER,
            content="客服没有回答生日蜡烛收费规则",
        )
    )
    responses = [
        '{"quality_score": 0, "issues": []}',
        '{"quality_score": 35, "issues": ["未回答生日蜡烛收费规则"]}',
    ]

    async def fake_llm_chat(*_args: object, **_kwargs: object) -> str:
        return responses.pop(0)

    monkeypatch.setattr(qa_review_module, "_invoke_review_chain", fake_llm_chat)
    agent = _build_agent(db)

    reviews = await agent.run()
    stored = await ConversationReviewRepo(db).list_by_session("session-repair")

    assert [review.quality_score for review in reviews] == [35]
    assert stored[0].issues_json == '["未回答生日蜡烛收费规则"]'
    assert responses == []


async def test_qa_review_agent_falls_back_when_low_score_has_no_issue(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """低分且模型始终不说明问题时，写入人工复核提示而不是空 issues。"""
    await _insert_session(db, "session-fallback", "closed")
    await MessageRepo(db).save(
        Message(
            id="msg-fallback",
            session_id="session-fallback",
            role=MessageRole.USER,
            content="客服没有回答生日蜡烛收费规则",
        )
    )
    responses = [
        '{"quality_score": 0, "issues": []}',
        '{"quality_score": 0, "issues": []}',
    ]

    async def fake_llm_chat(*_args: object, **_kwargs: object) -> str:
        return responses.pop(0)

    monkeypatch.setattr(qa_review_module, "_invoke_review_chain", fake_llm_chat)
    agent = _build_agent(db)

    reviews = await agent.run()
    stored = await ConversationReviewRepo(db).list_by_session("session-fallback")

    assert [review.quality_score for review in reviews] == [0]
    assert stored[0].issues_json == '["模型给出低分但未说明具体问题，需人工复核"]'
    assert responses == []


async def test_qa_review_agent_adds_actionable_issues_from_dialog_signals(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模型给高分时，转人工和人工纠正信号仍应沉淀成可解释问题。"""
    await _insert_session(db, "session-signal-review", "closed")
    repo = MessageRepo(db)
    await repo.save(
        Message(
            id="signal-user-1",
            session_id="session-signal-review",
            role=MessageRole.USER,
            content="娃娃头能定制4寸的吗？",
        )
    )
    await repo.save(
        Message(
            id="signal-assistant-1",
            session_id="session-signal-review",
            role=MessageRole.ASSISTANT,
            content="可以看看4寸手绘樱桃奶油蛋糕。",
        )
    )
    await repo.save(
        Message(
            id="signal-user-2",
            session_id="session-signal-review",
            role=MessageRole.USER,
            content="转人工",
        )
    )
    await repo.save(
        Message(
            id="signal-assistant-2",
            session_id="session-signal-review",
            role=MessageRole.ASSISTANT,
            content="[人工客服] 不可以哦，这个不行",
        )
    )

    async def fake_llm_chat(*_args: object, **_kwargs: object) -> str:
        return '{"quality_score": 95, "issues": []}'

    monkeypatch.setattr(qa_review_module, "_invoke_review_chain", fake_llm_chat)
    reviews = await _build_agent(db).run()

    issues = json.loads(reviews[0].issues_json)
    assert reviews[0].quality_score == 59
    assert "用户要求转人工，需复核机器人是否已充分解决前置问题" in issues
    assert "人工客服纠正了机器人未能明确处理的问题，需沉淀规则" in issues


async def test_qa_review_agent_flags_repeated_greeting_stall(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """连续寒暄三次以上后才进入需求时，质检应输出具体问题。"""
    await _insert_session(db, "session-greeting-stall", "closed")
    repo = MessageRepo(db)
    for index, content in enumerate(("你好？", "你好", "你好？"), start=1):
        await repo.save(
            Message(
                id=f"greeting-user-{index}",
                session_id="session-greeting-stall",
                role=MessageRole.USER,
                content=content,
            )
        )
        await repo.save(
            Message(
                id=f"greeting-assistant-{index}",
                session_id="session-greeting-stall",
                role=MessageRole.ASSISTANT,
                content="您好呀~ 我一直在的！请问有什么可以帮您的呀？",
            )
        )
    await repo.save(
        Message(
            id="greeting-user-4",
            session_id="session-greeting-stall",
            role=MessageRole.USER,
            content="推荐几个蛋糕吧",
        )
    )

    async def fake_llm_chat(*_args: object, **_kwargs: object) -> str:
        return '{"quality_score": 95, "issues": []}'

    monkeypatch.setattr(qa_review_module, "_invoke_review_chain", fake_llm_chat)
    reviews = await _build_agent(db).run()

    issues = json.loads(reviews[0].issues_json)
    assert reviews[0].quality_score == 59
    assert "用户连续寒暄后才进入需求，需更快识别意图并引导到具体咨询" in issues


def test_quality_signals_handle_message_role_enum_values() -> None:
    """规则信号应兼容仓库字符串角色和内存中的 MessageRole 枚举。"""
    messages = [
        Message("enum-user-1", "enum-session", MessageRole.USER, "你好？"),
        Message("enum-ai-1", "enum-session", MessageRole.ASSISTANT, "您好~"),
        Message("enum-user-2", "enum-session", MessageRole.USER, "你好"),
        Message("enum-ai-2", "enum-session", MessageRole.ASSISTANT, "您好~"),
        Message("enum-user-3", "enum-session", MessageRole.USER, "你好？"),
        Message("enum-ai-3", "enum-session", MessageRole.ASSISTANT, "您好~"),
        Message("enum-user-4", "enum-session", MessageRole.USER, "有荔枝的吗？"),
    ]

    issues = extract_review_issues(messages)
    memory = extract_memory_signal(messages)

    assert "用户连续寒暄后才进入需求，需更快识别意图并引导到具体咨询" in issues
    assert memory.preferences["product_interests"] == ["荔枝口味"]


def test_quality_signals_do_not_treat_birthday_candle_question_as_occasion() -> None:
    """生日蜡烛收费问题是知识咨询，不应写成顾客生日场景画像。"""
    messages = [
        Message(
            "candle-user-1",
            "candle-session",
            MessageRole.USER,
            "生日蜡烛收费吗？",
        )
    ]

    memory = extract_memory_signal(messages)

    assert memory.order_summary == {}


def test_quality_signals_extract_explicit_birthday_occasion() -> None:
    """用户明确说给孩子过生日时，应写入生日使用场景。"""
    messages = [
        Message(
            "birthday-user-1",
            "birthday-session",
            MessageRole.USER,
            "给孩子过生日，推荐个不要太甜的蛋糕。",
        )
    ]

    memory = extract_memory_signal(messages)

    assert memory.order_summary["usage"] == "儿童蛋糕"
    assert memory.order_summary["occasion"] == "生日"


async def test_qa_review_agent_isolates_single_session_llm_error(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """单个会话质检失败时不应写入脏数据，也不影响整轮返回。"""
    await _insert_session(db, "session-err", "closed")
    await MessageRepo(db).save(
        Message(
            id="msg-err",
            session_id="session-err",
            role=MessageRole.USER,
            content="这个能不能吃？",
        )
    )

    async def fake_llm_chat(*_args: object, **_kwargs: object) -> object:
        raise LLMError("boom")

    monkeypatch.setattr(qa_review_module, "_invoke_review_chain", fake_llm_chat)
    agent = _build_agent(db)

    reviews = await agent.run()
    stored = await ConversationReviewRepo(db).list_by_session("session-err")

    assert reviews == []
    assert stored == []


async def test_orchestrator_isolates_agent_failure() -> None:
    """编排器应捕获单 Agent 异常并返回空结果。"""

    class BrokenAgent:
        async def run(self) -> list:
            raise RuntimeError("failed")

    orchestrator = OfflineReviewOrchestrator(BrokenAgent())  # type: ignore[arg-type]

    assert await orchestrator.run_once() == []


async def test_knowledge_gap_agent_upserts_open_gap_without_duplicate_session(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """知识缺口 Agent 应写入 open 建议，同一来源会话重复运行不重复计数。"""
    await _insert_session(db, "gap-session-1", "closed")
    await MessageRepo(db).save(
        Message(
            id="gap-msg-1",
            session_id="gap-session-1",
            role=MessageRole.USER,
            content="生日蜡烛收费吗？",
        )
    )

    async def fake_gap_chain(*_args: object, **_kwargs: object) -> str:
        return '{"question_norm":"生日蜡烛收费吗","proposed_answer":"需人工审核后补充收费规则。"}'

    monkeypatch.setattr(knowledge_gap_module, "_invoke_gap_chain", fake_gap_chain)
    agent = KnowledgeGapAgent(MessageRepo(db), KnowledgeGapRepo(db))
    reviews = [
        ConversationReview(
            id=1,
            session_id="gap-session-1",
            quality_score=30,
            issues_json='["答漏"]',
        )
    ]

    first = await agent.run(reviews)
    second = await agent.run(reviews)
    open_gaps = await KnowledgeGapRepo(db).list_open_top()

    assert first[0].question_norm == "生日蜡烛收费吗"
    assert second[0].frequency == 1
    assert open_gaps[0].frequency == 1
    assert json.loads(open_gaps[0].related_sessions_json) == ["gap-session-1"]


async def test_knowledge_gap_agent_adds_gap_from_dialog_signals(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模型未发现缺口时，真实对话里的可运营缺口仍应入库。"""
    await _insert_session(db, "gap-signal-session", "closed")
    repo = MessageRepo(db)
    await repo.save(
        Message(
            id="gap-signal-user-1",
            session_id="gap-signal-session",
            role=MessageRole.USER,
            content="娃娃头能定制4寸的吗？",
        )
    )
    await repo.save(
        Message(
            id="gap-signal-assistant-1",
            session_id="gap-signal-session",
            role=MessageRole.ASSISTANT,
            content="[人工客服] 不可以哦，这个不行",
        )
    )

    async def fake_gap_chain(*_args: object, **_kwargs: object) -> str:
        return '{"question_norm":"","proposed_answer":""}'

    monkeypatch.setattr(knowledge_gap_module, "_invoke_gap_chain", fake_gap_chain)
    agent = KnowledgeGapAgent(MessageRepo(db), KnowledgeGapRepo(db))
    reviews = [
        ConversationReview(
            id=1,
            session_id="gap-signal-session",
            quality_score=20,
            issues_json='["人工纠正"]',
        )
    ]

    gaps = await agent.run(reviews)

    assert gaps[0].question_norm == "娃娃头水果奶油蛋糕是否支持4寸定制"


async def test_memory_agent_upserts_profile_and_skips_current_profile(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """记忆固化 Agent 应写入画像，画像时间追上会话后不再重复处理。"""
    await _insert_session(db, "memory-session-1", "closed")
    await db.execute(
        "UPDATE sessions SET updated_at = ? WHERE id = ?",
        ("2026-06-09 12:00:00", "memory-session-1"),
    )
    await db.commit()
    await MessageRepo(db).save(
        Message(
            id="memory-msg-1",
            session_id="memory-session-1",
            role=MessageRole.USER,
            content="我叫小林，喜欢少糖，坚果过敏。",
        )
    )

    async def fake_llm_chat(*_args: object, **_kwargs: object) -> str:
        return (
            '{"display_name":"小林","preferences":{"sweetness":"less"},'
            '"order_summary":{},"allergens":["坚果"],"consent_status":"unknown"}'
        )

    monkeypatch.setattr(memory_module, "_invoke_memory_chain", fake_llm_chat)
    await CustomerProfileRepo(db).set_consent_status(
        "youzan", "user-memory-session-1", "granted"
    )
    agent = MemoryAgent(
        OfflineSessionRepo(db), MessageRepo(db), CustomerProfileRepo(db)
    )

    profiles = await agent.run()
    second_run = await agent.run()
    profile = await CustomerProfileRepo(db).get("youzan", "user-memory-session-1")

    assert len(profiles) == 1
    assert second_run == []
    assert profile is not None
    assert profile.display_name == "小林"
    assert profile.preferences_json == '{"sweetness": "less"}'
    assert profile.allergens_json == '["坚果"]'


async def test_memory_agent_merges_dialog_signals_when_model_returns_empty_profile(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模型返回空画像时，儿童低甜和4寸定制等服务事实不能丢失。"""
    await _insert_session(db, "memory-signal-1", "closed")
    await db.execute(
        "UPDATE sessions SET updated_at = ? WHERE id = ?",
        ("2026-06-09 12:00:00", "memory-signal-1"),
    )
    await db.commit()
    repo = MessageRepo(db)
    await repo.save(
        Message(
            id="memory-signal-msg-1",
            session_id="memory-signal-1",
            role=MessageRole.USER,
            content="推荐个孩子吃的蛋糕，不要太甜，有4寸的吗？",
        )
    )
    await repo.save(
        Message(
            id="memory-signal-msg-2",
            session_id="memory-signal-1",
            role=MessageRole.USER,
            content="娃娃头能定制4寸的吗？",
        )
    )

    async def fake_llm_chat(*_args: object, **_kwargs: object) -> str:
        return (
            '{"display_name":"","preferences":{},'
            '"order_summary":{},"special_dates":[],'
            '"allergens":[],"consent_status":"unknown"}'
        )

    monkeypatch.setattr(memory_module, "_invoke_memory_chain", fake_llm_chat)
    await CustomerProfileRepo(db).set_consent_status(
        "youzan", "user-memory-signal-1", "granted"
    )
    agent = MemoryAgent(
        OfflineSessionRepo(db), MessageRepo(db), CustomerProfileRepo(db)
    )

    profiles = await agent.run()
    profile = await CustomerProfileRepo(db).get("youzan", "user-memory-signal-1")

    assert len(profiles) == 1
    assert profile is not None
    preferences = json.loads(profile.preferences_json)
    order_summary = json.loads(profile.order_summary_json)
    assert preferences["audience"] == "孩子"
    assert preferences["sweetness"] == "低甜"
    assert preferences["size_interest"] == "4寸"
    assert preferences["service_interest"] == "定制蛋糕"
    assert order_summary["usage"] == "儿童蛋糕"


async def test_memory_agent_merges_existing_profile_facts(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同一顾客多轮会话画像应合并事实，不能用新会话覆盖旧会话。"""
    await _insert_session(db, "memory-merge-1", "closed")
    await db.execute(
        "UPDATE sessions SET updated_at = ? WHERE id = ?",
        ("2026-06-09 12:00:00", "memory-merge-1"),
    )
    await MessageRepo(db).save(
        Message(
            id="memory-merge-msg-1",
            session_id="memory-merge-1",
            role=MessageRole.USER,
            content="给孩子吃，不要太甜，想要4寸。",
        )
    )
    await CustomerProfileRepo(db).upsert(
        memory_module.CustomerProfileUpsert(
            channel="youzan",
            user_id="user-memory-merge-1",
            preferences_json='{"audience":"老人","sweetness":"木糖醇"}',
            order_summary_json='{"usage":"长辈蛋糕"}',
            last_interaction_at="2026-06-09 11:00:00",
        )
    )
    await CustomerProfileRepo(db).set_consent_status(
        "youzan", "user-memory-merge-1", "granted"
    )

    async def fake_llm_chat(*_args: object, **_kwargs: object) -> str:
        return (
            '{"display_name":"","preferences":{},'
            '"order_summary":{},"special_dates":[],'
            '"allergens":[],"consent_status":"unknown"}'
        )

    monkeypatch.setattr(memory_module, "_invoke_memory_chain", fake_llm_chat)
    agent = MemoryAgent(
        OfflineSessionRepo(db), MessageRepo(db), CustomerProfileRepo(db)
    )

    await agent.run()
    profile = await CustomerProfileRepo(db).get("youzan", "user-memory-merge-1")

    assert profile is not None
    preferences = json.loads(profile.preferences_json)
    order_summary = json.loads(profile.order_summary_json)
    assert preferences["audience"] == ["老人", "孩子"]
    assert preferences["sweetness"] == ["木糖醇", "低甜"]
    assert preferences["size_interest"] == "4寸"
    assert order_summary["usage"] == ["长辈蛋糕", "儿童蛋糕"]


async def test_memory_agent_ignores_assistant_only_birthday_prompts(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """只有助手提到生日时，不应把它当作用户画像信号触发重试。"""
    await _insert_session(db, "memory-noisy-1", "closed")
    await db.execute(
        "UPDATE sessions SET updated_at = ? WHERE id = ?",
        ("2026-06-09 12:00:00", "memory-noisy-1"),
    )
    await db.commit()
    repo = MessageRepo(db)
    await repo.save(
        Message(
            id="memory-noisy-msg-1",
            session_id="memory-noisy-1",
            role=MessageRole.USER,
            content="推荐个蛋糕吧",
        )
    )
    await repo.save(
        Message(
            id="memory-noisy-msg-2",
            session_id="memory-noisy-1",
            role=MessageRole.ASSISTANT,
            content="请问是给谁过生日呀？",
        )
    )

    call_count = 0

    async def fake_llm_chat(*_args: object, **_kwargs: object) -> str:
        nonlocal call_count
        call_count += 1
        return (
            '{"display_name":"","preferences":{},'
            '"order_summary":{},"special_dates":[],'
            '"allergens":[],"consent_status":"unknown"}'
        )

    monkeypatch.setattr(memory_module, "_invoke_memory_chain", fake_llm_chat)
    await CustomerProfileRepo(db).set_consent_status(
        "youzan", "user-memory-scope-1", "granted"
    )
    agent = MemoryAgent(
        OfflineSessionRepo(db), MessageRepo(db), CustomerProfileRepo(db)
    )

    profiles = await agent.run()
    profile = await CustomerProfileRepo(db).get("youzan", "user-memory-noisy-1")

    assert call_count == 1
    assert profiles == []
    assert profile is None


async def test_memory_agent_skips_empty_profile_without_useful_facts(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """没有抽取到可服务事实时，不写空画像冒充沉淀成果。"""
    await _insert_session(db, "memory-empty-1", "closed")
    await MessageRepo(db).save(
        Message(
            id="memory-empty-msg-1",
            session_id="memory-empty-1",
            role=MessageRole.USER,
            content="你好，在吗？",
        )
    )

    async def fake_llm_chat(*_args: object, **_kwargs: object) -> str:
        return (
            '{"display_name":"","preferences":{},'
            '"order_summary":{},"special_dates":[],'
            '"allergens":[],"consent_status":"unknown"}'
        )

    monkeypatch.setattr(memory_module, "_invoke_memory_chain", fake_llm_chat)
    agent = MemoryAgent(
        OfflineSessionRepo(db), MessageRepo(db), CustomerProfileRepo(db)
    )

    profiles = await agent.run()
    profile = await CustomerProfileRepo(db).get("youzan", "user-memory-empty-1")

    assert profiles == []
    assert profile is None


async def test_orchestrator_runs_p3_agents_after_qa() -> None:
    """编排器应在质检后串联知识缺口与记忆固化 Agent。"""

    class QaAgent:
        async def run(self) -> list[ConversationReview]:
            return [ConversationReview(id=1, session_id="s1", quality_score=20)]

    class GapAgent:
        def __init__(self) -> None:
            self.received: list[ConversationReview] = []

        async def run(self, reviews: list[ConversationReview]) -> list:
            self.received = reviews
            return []

    class MemoryAgentStub:
        def __init__(self) -> None:
            self.called = False

        async def run(self) -> list:
            self.called = True
            return []

    gap_agent = GapAgent()
    memory_agent = MemoryAgentStub()
    orchestrator = OfflineReviewOrchestrator(
        QaAgent(),  # type: ignore[arg-type]
        gap_agent,  # type: ignore[arg-type]
        memory_agent,  # type: ignore[arg-type]
    )

    reviews = await orchestrator.run_once()

    assert reviews[0].session_id == "s1"
    assert gap_agent.received == reviews
    assert memory_agent.called is True


async def test_scheduler_runs_and_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """调度器应能启动、触发一轮并优雅停止。"""

    class FakeOrchestrator:
        def __init__(self) -> None:
            self.calls = 0

        async def run_once(self) -> list:
            self.calls += 1
            return []

    orchestrator = FakeOrchestrator()
    scheduler = OfflineReviewScheduler(
        orchestrator,
        interval_hours=0.01,
    )

    monkeypatch.setattr(
        scheduler_module, "_is_night_window", lambda *_args, **_kwargs: True
    )
    scheduler.start()
    await asyncio.sleep(0.01)
    await scheduler.stop()

    assert scheduler.get_last_summary().ran is True
    assert orchestrator.calls >= 1


async def test_scheduler_closes_idle_sessions_before_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """离线沉淀每轮执行前应先收口空闲 active 会话。"""
    events: list[str] = []

    class FakeIdleCloser:
        async def close_once(self) -> int:
            events.append("close-idle")
            return 1

    class FakeOrchestrator:
        async def run_once(self) -> list:
            events.append("review")
            return []

    scheduler = OfflineReviewScheduler(
        FakeOrchestrator(),  # type: ignore[arg-type]
        interval_hours=0.01,
        idle_closer=FakeIdleCloser(),
    )
    monkeypatch.setattr(
        scheduler_module, "_is_night_window", lambda *_args, **_kwargs: True
    )

    summary = await scheduler._run_once()  # noqa: SLF001

    assert summary.ran is True
    assert events == ["close-idle", "review"]


def test_night_window_wraps_across_midnight() -> None:
    assert _is_night_window(22, 6, now_hour=23) is True
    assert _is_night_window(22, 6, now_hour=2) is True
    assert _is_night_window(22, 6, now_hour=12) is False
    assert _is_night_window(8, 18, now_hour=9) is True
    assert _is_night_window(8, 18, now_hour=20) is False


def test_offline_model_prefers_thinking_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """离线模型默认优先使用思考模型，显式模型仍可覆盖。"""
    monkeypatch.setattr(qa_review_module.settings, "OFFLINE_REVIEW_MODEL", "")
    monkeypatch.setattr(qa_review_module.settings, "MIMO_THINKING_MODEL", "mimo-think")
    monkeypatch.setattr(qa_review_module.settings, "MIMO_CHAT_MODEL", "mimo-fast")

    assert select_offline_review_model() == "mimo-think"
    assert select_offline_review_model("explicit-model") == "explicit-model"


async def test_memory_agent_records_partial_handoff_scope(
    db: aiosqlite.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """转人工但人工消息不可见时，画像证据应标记为 partial。"""
    await _insert_session(db, "memory-scope-1", "closed")
    await db.execute(
        "UPDATE sessions SET updated_at = ?, extra_info = ? WHERE id = ?",
        (
            "2026-06-09 13:00:00",
            mark_handoff_started("{}"),
            "memory-scope-1",
        ),
    )
    await db.commit()
    await MessageRepo(db).save(
        Message(
            id="memory-scope-msg-1",
            session_id="memory-scope-1",
            role=MessageRole.USER,
            content="想看看草莓蛋糕。",
        )
    )

    captured: dict[str, object] = {}

    async def fake_llm_chat(*_args: object, **kwargs: object) -> str:
        captured["messages"] = kwargs["messages"]
        return (
            '{"display_name":"","preferences":{"interest":"草莓蛋糕"},'
            '"order_summary":{},"allergens":[],"consent_status":"unknown"}'
        )

    monkeypatch.setattr(memory_module, "_invoke_memory_chain", fake_llm_chat)
    await CustomerProfileRepo(db).set_consent_status(
        "youzan", "user-memory-scope-1", "granted"
    )
    agent = MemoryAgent(
        OfflineSessionRepo(db), MessageRepo(db), CustomerProfileRepo(db)
    )

    profiles = await agent.run()
    profile = await CustomerProfileRepo(db).get("youzan", "user-memory-scope-1")

    assert len(profiles) == 1
    assert profile is not None
    assert SessionScope.BOT_THEN_HANDOFF_PARTIAL.value in str(captured["messages"])
    evidence = json.loads(profile.source_evidence_json)
    assert evidence["session_scope"] == SessionScope.BOT_THEN_HANDOFF_PARTIAL.value
    assert evidence["handoff_occurred"] is True
    assert evidence["human_messages_available"] is False


@pytest.mark.asyncio
async def test_memory_chain_redacts_inputs_before_prompt_runnable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    def capture_prompt(prompt_value, **_kwargs) -> str:
        captured.append(prompt_value.to_string())
        return "{}"

    monkeypatch.setattr(
        memory_module,
        "get_langchain_chat_model",
        lambda **_kwargs: RunnableLambda(capture_prompt),
    )

    result = await memory_module._invoke_memory_chain(
        model_name="mimo-chat",
        messages=[
            {"role": "system", "content": memory_module.MEMORY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "手机号 13812345678，订单 E1234567890123",
            },
        ],
    )

    assert result == "{}"
    assert "13812345678" not in captured[0]
    assert "E1234567890123" not in captured[0]


def _build_agent(db: aiosqlite.Connection) -> QaReviewAgent:
    return QaReviewAgent(
        session_repo=SessionRepo(db),
        message_repo=MessageRepo(db),
        review_repo=ConversationReviewRepo(db),
        max_sessions=10,
        reviewer_model="mimo-test",
    )


async def _insert_session(
    db: aiosqlite.Connection,
    session_id: str,
    status: str,
) -> None:
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id, status) VALUES (?, ?, ?, ?)",
        (session_id, "youzan", f"user-{session_id}", status),
    )
    await db.commit()
