-- 持久消息 inbox：接收、lease、重试和 dead-letter 均由数据库保存。
CREATE TABLE IF NOT EXISTS inbox_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    queue_name TEXT NOT NULL,
    message_key TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'received'
        CHECK(status IN ('received', 'processing', 'processed', 'failed', 'dead_letter')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    lease_until TEXT,
    next_attempt_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_inbox_events_claim
ON inbox_events(queue_name, status, next_attempt_at, lease_until, id);
