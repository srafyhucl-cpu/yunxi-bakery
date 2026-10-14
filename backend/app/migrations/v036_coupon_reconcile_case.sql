-- 券冲突对账案件（r77 外部核销收敛）：平台不是券权威方时，外部已核销的事实
-- 不得回滚已到账的支付，也不得在本地再核销一次（一张券抵扣两单）。正确处置是
-- 放行收款 + 把被争议的 deducted_fen 追加成可对账案件，由平台按案件吸收或追偿。
-- 事实字段只追加不修改 / 删除；仅 status 允许 open→closed 生命周期流转。
-- case_key UNIQUE 保证同订单同券同原因只记一次（幂等追加，支付腿与退款腿共用）。

CREATE TABLE IF NOT EXISTS coupon_reconcile_case (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_key TEXT NOT NULL DEFAULT '',
    coupon_id TEXT NOT NULL DEFAULT '',
    mobile TEXT NOT NULL DEFAULT '',
    order_id TEXT NOT NULL DEFAULT '',
    external_order_no TEXT NOT NULL DEFAULT '',
    external_source TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    deducted_fen INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'closed')),
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_coupon_reconcile_case_key ON coupon_reconcile_case(case_key);
CREATE INDEX IF NOT EXISTS idx_coupon_reconcile_case_order ON coupon_reconcile_case(order_id);
CREATE INDEX IF NOT EXISTS idx_coupon_reconcile_case_coupon ON coupon_reconcile_case(coupon_id);
CREATE INDEX IF NOT EXISTS idx_coupon_reconcile_case_status ON coupon_reconcile_case(status);
