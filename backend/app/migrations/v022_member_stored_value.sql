-- 会员储值余额账务（M2）
-- stored_value_recharge：充值单，status 生命周期 unpaid -> paid/cancelled/expired
-- balance_ledger：储值余额流水，unique_id 幂等去重；amount_fen 带符号（充值+、支付-、退款+）

CREATE TABLE IF NOT EXISTS stored_value_recharge (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT '',
    mobile TEXT NOT NULL DEFAULT '',
    amount_fen INTEGER NOT NULL DEFAULT 0 CHECK(amount_fen > 0),
    status TEXT NOT NULL DEFAULT 'unpaid' CHECK(status IN ('unpaid', 'paid', 'cancelled', 'expired')),
    payment_method TEXT NOT NULL DEFAULT '',
    paid_at TEXT NOT NULL DEFAULT '',
    expired_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_recharge_user_created ON stored_value_recharge(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_recharge_mobile ON stored_value_recharge(mobile);

CREATE TABLE IF NOT EXISTS balance_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_id TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL DEFAULT '',
    mobile TEXT NOT NULL DEFAULT '',
    customer_id TEXT NOT NULL DEFAULT '',
    amount_fen INTEGER NOT NULL DEFAULT 0,
    balance_after_fen INTEGER NOT NULL DEFAULT 0,
    biz_type TEXT NOT NULL DEFAULT '' CHECK(biz_type IN ('recharge', 'order_pay', 'order_refund')),
    biz_id TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'recharge' CHECK(source IN ('webhook', 'import', 'recharge', 'order')),
    occurred_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_balance_ledger_unique ON balance_ledger(unique_id);
CREATE INDEX IF NOT EXISTS idx_balance_ledger_mobile_created ON balance_ledger(mobile, created_at);
CREATE INDEX IF NOT EXISTS idx_balance_ledger_biz ON balance_ledger(biz_type, biz_id);
