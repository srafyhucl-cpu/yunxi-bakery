-- Stage 2.5.2 有赞储值余额导入管线（M41）
-- 用 CSV/JSON 合成数据把有赞侧的历史储值余额以“期初导入”语义落到 member_balance /
-- balance_ledger，支撑 dry-run、apply、对账、幂等与回滚，全程不接触真实有赞 API。
-- youzan_stored_value_import_batches：一次导入任务（按 source_sha256 复用）。
-- youzan_stored_value_import_rows：staging 明细行，承载校验结果与入账状态。
-- 状态机（批次）：created -> validated -> applied / failed，回滚后为 rolled_back。
-- 状态机（行）：valid / invalid / conflict -> applied / rolled_back。

CREATE TABLE IF NOT EXISTS youzan_stored_value_import_batches (
    id TEXT PRIMARY KEY,
    source_file TEXT NOT NULL DEFAULT '',
    source_sha256 TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'created'
        CHECK(status IN ('created','validated','applied','failed','rolled_back')),
    total_rows INTEGER NOT NULL DEFAULT 0,
    valid_rows INTEGER NOT NULL DEFAULT 0,
    invalid_rows INTEGER NOT NULL DEFAULT 0,
    applied_rows INTEGER NOT NULL DEFAULT 0,
    total_principal_fen INTEGER NOT NULL DEFAULT 0,
    total_bonus_fen INTEGER NOT NULL DEFAULT 0,
    total_stored_value_fen INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    applied_at TEXT NOT NULL DEFAULT '',
    rolled_back_at TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_ysv_batch_status
    ON youzan_stored_value_import_batches(status);
CREATE INDEX IF NOT EXISTS idx_ysv_batch_sha
    ON youzan_stored_value_import_batches(source_sha256);

CREATE TABLE IF NOT EXISTS youzan_stored_value_import_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL REFERENCES youzan_stored_value_import_batches(id),
    row_no INTEGER NOT NULL DEFAULT 0,
    mobile TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    principal_fen INTEGER NOT NULL DEFAULT 0,
    bonus_fen INTEGER NOT NULL DEFAULT 0,
    reported_total_fen INTEGER,
    yz_open_id TEXT NOT NULL DEFAULT '',
    card_no TEXT NOT NULL DEFAULT '',
    card_alias TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'valid'
        CHECK(status IN ('valid','invalid','applied','conflict','rolled_back')),
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    applied_at TEXT NOT NULL DEFAULT '',
    UNIQUE(batch_id, row_no)
);

CREATE INDEX IF NOT EXISTS idx_ysv_row_batch_status
    ON youzan_stored_value_import_rows(batch_id, status);
CREATE INDEX IF NOT EXISTS idx_ysv_row_mobile
    ON youzan_stored_value_import_rows(mobile);
