-- 积分模块（M3）
-- points_ledger：source 扩展 order，新增 biz_type/biz_id（order_award/order_redeem/order_refund）
-- SQLite 重建表以修改 CHECK 约束并加列

CREATE TABLE IF NOT EXISTS points_ledger_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_id TEXT NOT NULL DEFAULT '',
    customer_id TEXT NOT NULL DEFAULT '',
    mobile TEXT NOT NULL DEFAULT '',
    yz_open_id TEXT NOT NULL DEFAULT '',
    amount INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    event_type TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'webhook' CHECK(source IN ('webhook', 'import', 'order')),
    biz_type TEXT NOT NULL DEFAULT '',
    biz_id TEXT NOT NULL DEFAULT '',
    occurred_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO points_ledger_new (id, unique_id, customer_id, mobile, yz_open_id, amount, total, event_type, source, occurred_at, created_at)
SELECT id, unique_id, customer_id, mobile, yz_open_id, amount, total, event_type, source, occurred_at, created_at FROM points_ledger;

DROP TABLE points_ledger;
ALTER TABLE points_ledger_new RENAME TO points_ledger;

CREATE UNIQUE INDEX IF NOT EXISTS idx_points_ledger_unique ON points_ledger(unique_id);
CREATE INDEX IF NOT EXISTS idx_points_ledger_customer ON points_ledger(customer_id);
CREATE INDEX IF NOT EXISTS idx_points_ledger_mobile ON points_ledger(mobile);
CREATE INDEX IF NOT EXISTS idx_points_ledger_biz ON points_ledger(biz_type, biz_id);
