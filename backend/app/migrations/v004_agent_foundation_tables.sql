-- 迁移：新增 Agent 化 P0 基础表
-- 日期：2026-06-09
-- 说明：长期记忆、离线会话质检、知识缺口建议三张表

CREATE TABLE IF NOT EXISTS customer_profiles (
    id TEXT PRIMARY KEY,
    channel TEXT NOT NULL,
    user_id TEXT NOT NULL,
    display_name TEXT DEFAULT '',
    preferences_json TEXT DEFAULT '{}',
    order_summary_json TEXT DEFAULT '{}',
    allergens_json TEXT DEFAULT '[]',
    consent_status TEXT DEFAULT 'unknown'
        CHECK(consent_status IN ('unknown','granted','revoked')),
    source_evidence_json TEXT DEFAULT '{}',
    last_interaction_at TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(channel, user_id)
);

CREATE INDEX IF NOT EXISTS idx_cp_channel_user
ON customer_profiles(channel, user_id);

CREATE TABLE IF NOT EXISTS conversation_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    quality_score INTEGER NOT NULL CHECK(quality_score >= 0 AND quality_score <= 100),
    issues_json TEXT DEFAULT '[]',
    reviewer_model TEXT DEFAULT '',
    reviewed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cr_session
ON conversation_reviews(session_id);

CREATE INDEX IF NOT EXISTS idx_cr_score
ON conversation_reviews(quality_score);

CREATE TABLE IF NOT EXISTS knowledge_gaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_norm TEXT NOT NULL,
    frequency INTEGER DEFAULT 1,
    status TEXT DEFAULT 'open'
        CHECK(status IN ('open','proposed','resolved','rejected')),
    proposed_answer TEXT DEFAULT '',
    related_sessions_json TEXT DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_kg_status
ON knowledge_gaps(status);

CREATE INDEX IF NOT EXISTS idx_kg_freq
ON knowledge_gaps(frequency);
