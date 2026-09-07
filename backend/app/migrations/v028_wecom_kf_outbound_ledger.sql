-- 企微客服外发投递账本：稳定幂等键与发送状态机。
CREATE TABLE IF NOT EXISTS wecom_kf_outbound_ledger (
    outbound_key TEXT PRIMARY KEY,
    open_kfid TEXT NOT NULL DEFAULT '',
    external_userid TEXT NOT NULL DEFAULT '',
    inbound_msg_id TEXT NOT NULL DEFAULT '',
    provider_msgid TEXT NOT NULL DEFAULT '',
    msgtype TEXT NOT NULL DEFAULT 'text',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'sending', 'sent', 'unknown', 'failed')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_kf_outbound_status
ON wecom_kf_outbound_ledger(status, updated_at);

CREATE INDEX IF NOT EXISTS idx_kf_outbound_inbound
ON wecom_kf_outbound_ledger(inbound_msg_id);
