-- 迁移：记录知识库检索命中，用于客户/员工知识命中观测
CREATE TABLE IF NOT EXISTS knowledge_retrieval_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_type TEXT NOT NULL DEFAULT '',
    audience TEXT NOT NULL DEFAULT 'all',
    query TEXT NOT NULL DEFAULT '',
    retrieval_mode TEXT NOT NULL DEFAULT '',
    matched_entry_ids_json TEXT NOT NULL DEFAULT '[]',
    matched_titles_json TEXT NOT NULL DEFAULT '[]',
    result_count INTEGER NOT NULL DEFAULT 0,
    fallback_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_krl_created_at
ON knowledge_retrieval_logs(created_at);

CREATE INDEX IF NOT EXISTS idx_krl_bot_audience_created
ON knowledge_retrieval_logs(bot_type, audience, created_at);

