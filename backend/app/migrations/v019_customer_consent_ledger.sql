-- 顾客记忆 consent 真相表；画像删除后仍保留 revoked 状态。
CREATE TABLE IF NOT EXISTS customer_consent_ledger (
    channel TEXT NOT NULL,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unknown'
        CHECK(status IN ('unknown', 'granted', 'revoked')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY(channel, user_id)
);
