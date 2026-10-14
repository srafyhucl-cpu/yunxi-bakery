-- 券多周期消费（r78，M-20260926-028）
-- `v024_coupon_module.sql` 的 `UNIQUE(coupon_id, status, mobile)` 把**状态**放进
-- 唯一键，使 `TAKE → CONSUME → BACK → CONSUME` 的第二个周期在库层不可表达：
-- 全额退款退回的券被永久作废，客户在拿回全部现金的同时永久损失券面价值。
-- 本迁移把唯一键对齐到同库既有约定「唯一键 = 业务操作」（`points_ledger` /
-- `balance_ledger` 的 `UNIQUE(unique_id)`，键内含 order_id，故同一订单的不同
-- 补偿周期天然不冲突），引入 `cycle_no` 消费周期维度：
--   · 同一周期内重复进入同一状态仍被唯一键挡住（幂等兜底不丢）
--   · 跨周期各占键位（第二个消费周期合法）
-- 既有行统一落在 cycle_no=0：旧唯一键本就限制每状态至多一行，迁移不产生冲突。

ALTER TABLE coupon_inventory ADD COLUMN cycle_no INTEGER NOT NULL DEFAULT 0;

DROP INDEX IF EXISTS idx_coupon_inventory_dedup;

CREATE UNIQUE INDEX IF NOT EXISTS idx_coupon_inventory_cycle
    ON coupon_inventory(coupon_id, status, mobile, cycle_no);
