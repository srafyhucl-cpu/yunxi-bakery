-- 迁移：新增客户会话短期摘要表
-- 日期：2026-07-06
-- 说明：会话摘要只服务短期上下文压缩，不直接写入长期客户画像

CREATE TABLE IF NOT EXISTS conversation_summaries (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    channel TEXT NOT NULL,
    user_id TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    state_json TEXT NOT NULL DEFAULT '{}',
    source_message_ids_json TEXT NOT NULL DEFAULT '[]',
    source_until_message_id TEXT DEFAULT '',
    token_estimate INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active','superseded','discarded')),
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cs_session_status
ON conversation_summaries(session_id, status);

CREATE INDEX IF NOT EXISTS idx_cs_channel_user
ON conversation_summaries(channel, user_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cs_active_session
ON conversation_summaries(session_id)
WHERE status = 'active';
