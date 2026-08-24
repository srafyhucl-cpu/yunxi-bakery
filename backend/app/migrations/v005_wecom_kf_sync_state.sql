-- 迁移：微信客服转人工同步状态
-- 日期：2026-06-10
-- 说明：保存 sync_msg cursor，并用 msgid 账本抵御重复回调和历史回放

CREATE TABLE IF NOT EXISTS wecom_kf_sync_states (
    open_kfid TEXT PRIMARY KEY,
    last_cursor TEXT DEFAULT '',
    status TEXT DEFAULT 'idle'
        CHECK(status IN ('idle','syncing','failed')),
    last_error TEXT DEFAULT '',
    retry_count INTEGER DEFAULT 0,
    last_synced_at TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS wecom_kf_message_ledger (
    msg_id TEXT PRIMARY KEY,
    open_kfid TEXT DEFAULT '',
    external_userid TEXT DEFAULT '',
    origin INTEGER DEFAULT 0,
    msgtype TEXT DEFAULT '',
    event_type TEXT DEFAULT '',
    process_action TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_wkms_open_kfid
ON wecom_kf_message_ledger(open_kfid);

CREATE INDEX IF NOT EXISTS idx_wkms_external_user
ON wecom_kf_message_ledger(external_userid);
