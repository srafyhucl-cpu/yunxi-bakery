"""Agent 化 P0 repository 单元测试。"""

import aiosqlite

from app.models.conversation_review import ConversationReviewCreate
from app.models.customer_profile import CustomerProfileUpsert, MemoryConsentStatus
from app.models.knowledge_gap import KnowledgeGapCreate, KnowledgeGapStatus
from app.repository.conversation_review_repo import ConversationReviewRepo
from app.repository.customer_profile_repo import CustomerProfileRepo
from app.repository.knowledge_gap_repo import KnowledgeGapRepo


async def test_customer_profile_upsert_updates_existing_row(
    db: aiosqlite.Connection,
) -> None:
    """同一渠道用户重复 upsert 应更新原画像而不是新增行。"""
    repo = CustomerProfileRepo(db)
    first = await repo.upsert(
        CustomerProfileUpsert(
            channel="youzan",
            user_id="buyer-001",
            display_name="小林",
            preferences_json='{"sweetness":"less"}',
            last_interaction_at="2026-06-09 10:00:00",
        )
    )
    second = await repo.upsert(
        CustomerProfileUpsert(
            channel="youzan",
            user_id="buyer-001",
            display_name="小林同学",
            preferences_json='{"sweetness":"none"}',
            allergens_json='["nuts"]',
            consent_status=MemoryConsentStatus.GRANTED.value,
            last_interaction_at="2026-06-09 11:00:00",
        )
    )
    rows = await db.execute_fetchall(
        "SELECT COUNT(*) AS row_count FROM customer_profiles WHERE channel = ? AND user_id = ?",
        ("youzan", "buyer-001"),
    )

    assert first.id == second.id
    assert second.display_name == "小林同学"
    assert second.preferences_json == '{"sweetness":"none"}'
    assert second.allergens_json == '["nuts"]'
    assert second.consent_status == MemoryConsentStatus.GRANTED.value
    assert rows[0]["row_count"] == 1


async def test_customer_profile_get_and_touch(
    db: aiosqlite.Connection,
) -> None:
    """画像不存在时返回 None，存在时可刷新最近交互时间。"""
    repo = CustomerProfileRepo(db)
    missing = await repo.get("youzan", "missing")
    await repo.upsert(
        CustomerProfileUpsert(
            channel="youzan",
            user_id="buyer-002",
            last_interaction_at="2000-01-01 00:00:00",
        )
    )
    await repo.touch_interaction("youzan", "buyer-002")

    profile = await repo.get("youzan", "buyer-002")
    assert missing is None
    assert profile is not None
    assert profile.last_interaction_at != "2000-01-01 00:00:00"


async def test_conversation_review_create_and_list_low_score(
    db: aiosqlite.Connection,
) -> None:
    """会话质检结果应可按会话查询，也可筛选低分会话。"""
    await _insert_session(db, "session-review-001")
    repo = ConversationReviewRepo(db)
    high = await repo.create(
        ConversationReviewCreate(
            session_id="session-review-001",
            quality_score=88,
            reviewer_model="mimo",
            reviewed_at="2026-06-09 10:00:00",
        )
    )
    low = await repo.create(
        ConversationReviewCreate(
            session_id="session-review-001",
            quality_score=30,
            issues_json='["答漏"]',
            reviewer_model="mimo",
            reviewed_at="2026-06-09 11:00:00",
        )
    )

    session_reviews = await repo.list_by_session("session-review-001")
    low_scores = await repo.list_low_score(50)

    assert [review.id for review in session_reviews] == [low.id, high.id]
    assert [review.id for review in low_scores] == [low.id]
    assert low_scores[0].issues_json == '["答漏"]'


async def test_knowledge_gap_create_list_and_update_status(
    db: aiosqlite.Connection,
) -> None:
    """知识缺口建议应可按状态查询并更新审核状态。"""
    repo = KnowledgeGapRepo(db)
    await repo.create(KnowledgeGapCreate(question_norm="配送范围", frequency=2))
    frequent = await repo.create(
        KnowledgeGapCreate(question_norm="生日蜡烛收费吗", frequency=5)
    )

    open_gaps = await repo.list_open_top()
    await repo.update_status(
        frequent.id,
        KnowledgeGapStatus.PROPOSED.value,
        "生日蜡烛收费以门店实际规则为准。",
    )
    proposed_gaps = await repo.list_by_status(KnowledgeGapStatus.PROPOSED.value)

    assert [gap.question_norm for gap in open_gaps] == ["生日蜡烛收费吗", "配送范围"]
    assert proposed_gaps[0].id == frequent.id
    assert proposed_gaps[0].status == KnowledgeGapStatus.PROPOSED.value
    assert proposed_gaps[0].proposed_answer == "生日蜡烛收费以门店实际规则为准。"


async def _insert_session(db: aiosqlite.Connection, session_id: str) -> None:
    await db.execute(
        "INSERT INTO sessions (id, channel, user_id, status) VALUES (?, ?, ?, ?)",
        (session_id, "youzan", f"user-{session_id}", "closed"),
    )
    await db.commit()
