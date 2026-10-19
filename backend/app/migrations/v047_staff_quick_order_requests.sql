-- Stage 3C2A 店员快捷开单请求幂等（M47）
-- 同一 requestId 只允许产生一笔订单：request_id 作为唯一幂等键，
-- status 只允许 pending -> completed / failed，completed 不允许被覆盖。
-- 本表只保存开单请求的归属与结果，不保存完整手机号或储值账本字段。

CREATE TABLE IF NOT EXISTS staff_quick_order_requests (
    request_id TEXT PRIMARY KEY,
    staff_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('stored_value_direct','wechat_share_card')),
    status TEXT NOT NULL CHECK(status IN ('pending','completed','failed')),
    order_id TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_staff_quick_order_requests_staff_created
ON staff_quick_order_requests(staff_id, created_at);
