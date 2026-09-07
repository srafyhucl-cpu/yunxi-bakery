-- P0-6 企微同步租约：短事务原子取得同步权，事务外拉取，短事务提交。
-- 同一 open_kfid 同时只允许一个同步者；拉取失败只记失败不推进游标；
-- 分页截断保存 continuation 状态并触发后续同步。
CREATE TABLE IF NOT EXISTS wecom_kf_sync_leases (
    open_kfid TEXT PRIMARY KEY,
    lease_token TEXT NOT NULL DEFAULT '',
    base_cursor TEXT NOT NULL DEFAULT '',
    lease_until TEXT NOT NULL DEFAULT '',
    continuation_cursor TEXT NOT NULL DEFAULT '',
    has_more INTEGER NOT NULL DEFAULT 0,
    fail_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_kf_sync_leases_until ON wecom_kf_sync_leases(lease_until);
