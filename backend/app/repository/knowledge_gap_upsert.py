"""知识缺口 open 建议的幂等累加写入。"""

import json

from app.repository.base import DatabaseHandle
from app.models.knowledge_gap import (
    KnowledgeGap,
    KnowledgeGapCreate,
    KnowledgeGapStatus,
)
from app.utils import now_str


async def upsert_open_gap(
    db: DatabaseHandle,
    gap: KnowledgeGapCreate,
) -> KnowledgeGap:
    """按归一化问题合并 open 缺口，避免同一会话重复计数。"""
    now = now_str()
    new_session_ids = _load_session_ids(gap.related_sessions_json)
    frequency = max(gap.frequency, len(new_session_ids))
    rows = await db.execute_fetchall(
        "SELECT id, question_norm, frequency, status, proposed_answer, "
        "related_sessions_json, created_at, updated_at "
        "FROM knowledge_gaps WHERE question_norm = ? AND status = ? "
        "ORDER BY updated_at DESC, id DESC LIMIT 1",
        (gap.question_norm, KnowledgeGapStatus.OPEN.value),
    )
    if rows:
        return await _update_gap(db, rows[0], gap, new_session_ids, now)
    return await _insert_gap(db, gap, frequency, now)


async def _update_gap(
    db: DatabaseHandle,
    row: dict[str, object],
    gap: KnowledgeGapCreate,
    new_session_ids: set[str],
    now: str,
) -> KnowledgeGap:
    session_ids = sorted(
        _load_session_ids(row["related_sessions_json"]) | new_session_ids
    )
    related_sessions_json = json.dumps(session_ids, ensure_ascii=False)
    frequency = max(_as_int(row["frequency"]), len(session_ids), gap.frequency)
    await db.execute(
        "UPDATE knowledge_gaps SET frequency = ?, proposed_answer = ?, "
        "related_sessions_json = ?, updated_at = ? WHERE id = ?",
        (
            frequency,
            gap.proposed_answer,
            related_sessions_json,
            now,
            _as_int(row["id"]),
        ),
    )
    await db.commit()
    return KnowledgeGap(
        id=_as_int(row["id"]),
        question_norm=str(row["question_norm"]),
        frequency=frequency,
        status=str(row["status"]),
        proposed_answer=gap.proposed_answer,
        related_sessions_json=related_sessions_json,
        created_at=str(row["created_at"]),
        updated_at=now,
    )


async def _insert_gap(
    db: DatabaseHandle,
    gap: KnowledgeGapCreate,
    frequency: int,
    now: str,
) -> KnowledgeGap:
    await db.execute(
        "INSERT INTO knowledge_gaps (question_norm, frequency, status, proposed_answer, "
        "related_sessions_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            gap.question_norm,
            frequency,
            KnowledgeGapStatus.OPEN.value,
            gap.proposed_answer,
            gap.related_sessions_json,
            now,
            now,
        ),
    )
    await db.commit()
    rows = await db.execute_fetchall("SELECT last_insert_rowid() AS id")
    return KnowledgeGap(
        id=_as_int(rows[0]["id"]),
        question_norm=gap.question_norm,
        frequency=frequency,
        status=KnowledgeGapStatus.OPEN.value,
        proposed_answer=gap.proposed_answer,
        related_sessions_json=gap.related_sessions_json,
        created_at=now,
        updated_at=now,
    )


def _load_session_ids(raw_json: object) -> set[str]:
    """解析缺口来源会话列表，格式异常时返回空集合。"""
    try:
        payload = json.loads(str(raw_json or "[]"))
    except json.JSONDecodeError:
        return set()
    if not isinstance(payload, list):
        return set()
    return {str(item) for item in payload if str(item).strip()}


def _as_int(value: object) -> int:
    return int(str(value))
