-- 账务结算事实与补偿持久化（B3.5，评审问题 2 / 3）：最小 D1 持久化
-- 1) ledger_operation：结算事实（redeem 扣减 / award 发放），与积分流水、pointsSettledAt
--    标记同一 UoW 提交（评审问题 2：流水先提交、标记后写导致崩溃误判未结算 → 事实表同事务原子写）
-- 2) refund_operation：退款操作事实（补偿记录，operation_key 幂等）
-- 3) refund_shortfall_debt：奖励积分扣回余额不足欠账（评审问题 3：clawback 返回 None 不得静默跳过）
-- 4) points_refund_reconcile 案件审计列（评审问题 3）：处理人 / 处理时间 / 结论 / 证据引用 /
--    补录幂等键 / 案件版本（reopen 后 version 递增）
-- 5) member_balance_id 快照绑定：积分快照绑定不可变余额账户 ID（评审问题 2），
--    结算与退款一律按快照绑定账户，禁止账户漂移

CREATE TABLE IF NOT EXISTS ledger_operation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_type TEXT NOT NULL DEFAULT '',
    subject_type TEXT NOT NULL DEFAULT 'order',
    subject_id TEXT NOT NULL DEFAULT '',
    mobile TEXT NOT NULL DEFAULT '',
    member_balance_id INTEGER,
    amount INTEGER NOT NULL DEFAULT 0,
    unique_id TEXT NOT NULL DEFAULT '',
    biz_type TEXT NOT NULL DEFAULT '',
    biz_id TEXT NOT NULL DEFAULT '',
    occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ledger_operation_unique_id ON ledger_operation(unique_id);
CREATE INDEX IF NOT EXISTS idx_ledger_operation_subject ON ledger_operation(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_ledger_operation_member ON ledger_operation(member_balance_id);

CREATE TABLE IF NOT EXISTS refund_operation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL DEFAULT '',
    mobile TEXT NOT NULL DEFAULT '',
    member_balance_id INTEGER,
    operation_key TEXT NOT NULL DEFAULT '',
    points_used INTEGER NOT NULL DEFAULT 0,
    points_awarded INTEGER NOT NULL DEFAULT 0,
    return_amount INTEGER NOT NULL DEFAULT 0,
    clawback_amount INTEGER NOT NULL DEFAULT 0,
    shortfall_amount INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'partial' CHECK(status IN ('succeeded', 'partial', 'shortfall')),
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_refund_operation_key ON refund_operation(operation_key);
CREATE INDEX IF NOT EXISTS idx_refund_operation_order ON refund_operation(order_id);

CREATE TABLE IF NOT EXISTS refund_shortfall_debt (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL DEFAULT '',
    mobile TEXT NOT NULL DEFAULT '',
    member_balance_id INTEGER,
    operation_key TEXT NOT NULL DEFAULT '',
    amount INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'settled')),
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_refund_shortfall_key ON refund_shortfall_debt(operation_key);
CREATE INDEX IF NOT EXISTS idx_refund_shortfall_order ON refund_shortfall_debt(order_id);

-- 案件审计列（评审问题 3）：处理人 / 处理时间 / 处理结论 / 证据引用 / 补录幂等键 / 案件版本
ALTER TABLE points_refund_reconcile ADD COLUMN resolved_by TEXT NOT NULL DEFAULT '';
ALTER TABLE points_refund_reconcile ADD COLUMN resolved_at TEXT;
ALTER TABLE points_refund_reconcile ADD COLUMN resolution TEXT NOT NULL DEFAULT '';
ALTER TABLE points_refund_reconcile ADD COLUMN evidence_ref TEXT NOT NULL DEFAULT '';
ALTER TABLE points_refund_reconcile ADD COLUMN operation_key TEXT NOT NULL DEFAULT '';
ALTER TABLE points_refund_reconcile ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
