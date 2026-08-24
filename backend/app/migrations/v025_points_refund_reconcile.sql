-- 积分退款对账修正清单（B3.3 建表，B3.4 定稿语义）：事实字段只追加，不修改 / 删除；
-- 仅 status 允许 open→closed 生命周期流转（人工核对后关闭，见 PointsRefundReconcileRepo.close_open）
-- 记录积分退款命令发现的异常（已结算订单 redeem / award 流水缺失或金额 / 归属不一致等），
-- 供对账与人工修正；未结算正常取消不建案件（B3.4 两命令分流）
-- 唯一索引 (order_id, reason) 保证同一订单同一异常只记一次（幂等追加）

CREATE TABLE IF NOT EXISTS points_refund_reconcile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL DEFAULT '',
    mobile TEXT NOT NULL DEFAULT '',
    unique_id TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    amount INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'closed')),
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_points_refund_reconcile_order_reason ON points_refund_reconcile(order_id, reason);
CREATE INDEX IF NOT EXISTS idx_points_refund_reconcile_status ON points_refund_reconcile(status);
CREATE INDEX IF NOT EXISTS idx_points_refund_reconcile_mobile ON points_refund_reconcile(mobile);
