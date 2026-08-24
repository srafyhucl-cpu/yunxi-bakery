-- 会员储值/积分/优惠券账务域数据底座（M1）
-- member_balance：按 mobile 唯一保存会员身份/卡片/余额快照（points 为积分余额，stored_value_fen 为储值余额分）
-- points_ledger：积分变动流水，unique_id 幂等去重
-- coupon_inventory：优惠券生命周期记录，coupon_id+status+mobile 组合去重

CREATE TABLE IF NOT EXISTS member_balance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id TEXT NOT NULL DEFAULT '',
    mobile TEXT NOT NULL DEFAULT '',
    yz_open_id TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    is_member INTEGER NOT NULL DEFAULT 0,
    card_alias TEXT NOT NULL DEFAULT '',
    card_no TEXT NOT NULL DEFAULT '',
    card_status TEXT NOT NULL DEFAULT '',
    points INTEGER NOT NULL DEFAULT 0,
    stored_value_fen INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_member_balance_mobile ON member_balance(mobile);
CREATE INDEX IF NOT EXISTS idx_member_balance_customer ON member_balance(customer_id);
CREATE INDEX IF NOT EXISTS idx_member_balance_openid ON member_balance(yz_open_id);

CREATE TABLE IF NOT EXISTS points_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_id TEXT NOT NULL DEFAULT '',
    customer_id TEXT NOT NULL DEFAULT '',
    mobile TEXT NOT NULL DEFAULT '',
    yz_open_id TEXT NOT NULL DEFAULT '',
    amount INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    event_type TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'webhook' CHECK(source IN ('webhook', 'import')),
    occurred_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_points_ledger_unique ON points_ledger(unique_id);
CREATE INDEX IF NOT EXISTS idx_points_ledger_customer ON points_ledger(customer_id);
CREATE INDEX IF NOT EXISTS idx_points_ledger_mobile ON points_ledger(mobile);

CREATE TABLE IF NOT EXISTS coupon_inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coupon_id TEXT NOT NULL DEFAULT '',
    coupon_group_id TEXT NOT NULL DEFAULT '',
    customer_id TEXT NOT NULL DEFAULT '',
    mobile TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    order_no TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    value_fen INTEGER NOT NULL DEFAULT 0,
    detail_json TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL DEFAULT 'webhook' CHECK(source IN ('webhook', 'import')),
    occurred_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_coupon_inventory_dedup ON coupon_inventory(coupon_id, status, mobile);
CREATE INDEX IF NOT EXISTS idx_coupon_inventory_mobile ON coupon_inventory(mobile);
