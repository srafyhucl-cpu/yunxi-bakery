-- Stage 3A 打印作业骨架（M44）
-- 订单进入已支付后由 3B 创建打印作业；本表只记录作业状态，不保存真实出纸结果。
-- 同一订单同一联单以 idempotency_key 唯一约束保证入队幂等；补打创建新作业，
-- 不覆盖原作业，保留完整打印尝试轨迹。

CREATE TABLE IF NOT EXISTS order_print_jobs (
    id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    ticket_type TEXT NOT NULL CHECK(ticket_type IN ('CAKE_KITCHEN','DAILY_FRONT')),
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK(status IN ('PENDING','CLAIMED','SUBMITTED','PRINTED','FAILED','MOCKED','CANCELLED')),
    provider TEXT NOT NULL DEFAULT '',
    printer_id TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    provider_job_id TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL,
    payload_snapshot TEXT NOT NULL DEFAULT '',
    operator TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    printed_at TEXT NOT NULL DEFAULT '',
    UNIQUE(idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_order_print_jobs_order_id
ON order_print_jobs(order_id);

CREATE INDEX IF NOT EXISTS idx_order_print_jobs_status
ON order_print_jobs(status);
