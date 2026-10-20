-- Stage 2.5.5 定制蛋糕 2 小时时段容量原子预占（M43）
-- 以 slot_key（YYYY-MM-DD HH:00-HH:00）为粒度记录当前已预占单量，
-- 替代“先统计活跃订单再下单”的竞态校验；取消/超时/后台关闭时释放，
-- 订单完成（done）不释放，保留当日实际产能占用。
-- reservations 以 order_id 为主键，保证同一订单重复预占幂等。

CREATE TABLE IF NOT EXISTS cake_slot_capacity (
    slot_key TEXT PRIMARY KEY,
    reserved_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    CHECK(reserved_count >= 0)
);

CREATE TABLE IF NOT EXISTS cake_slot_reservations (
    order_id TEXT PRIMARY KEY,
    slot_key TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cake_slot_reservations_slot
ON cake_slot_reservations(slot_key);
