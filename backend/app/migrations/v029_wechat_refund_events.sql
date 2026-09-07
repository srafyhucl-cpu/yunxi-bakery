-- 微信退款事件事实：商户退款单号幂等，累计退款由订单支付快照 CAS 保护。
CREATE TABLE IF NOT EXISTS wechat_refund_events (
    out_refund_no TEXT PRIMARY KEY,
    order_id TEXT NOT NULL DEFAULT '',
    transaction_id TEXT NOT NULL DEFAULT '',
    refund_id TEXT NOT NULL DEFAULT '',
    total_fen INTEGER NOT NULL DEFAULT 0,
    refund_fen INTEGER NOT NULL DEFAULT 0,
    payer_refund_fen INTEGER NOT NULL DEFAULT 0,
    refund_status TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'notify'
        CHECK(source IN ('notify', 'query')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_wechat_refund_order
ON wechat_refund_events(order_id);
