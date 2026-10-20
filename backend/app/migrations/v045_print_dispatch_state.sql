-- Stage 3B1 已支付订单打印调度游标（M45）
-- 调度器按 (updated_at, id) 字典序扫描已支付订单并入队打印作业。
-- 单行固定 id='default'，保证应用重启后从上次游标继续，不重复、不丢单。

CREATE TABLE IF NOT EXISTS order_print_dispatch_state (
    id TEXT PRIMARY KEY,
    last_updated_at TEXT NOT NULL DEFAULT '',
    last_order_id TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
