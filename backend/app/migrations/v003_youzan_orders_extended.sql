-- 迁移：为 youzan_orders 表添加扩展列
-- 日期：2026-06-06
-- 说明：从 database.py 的 init_db() 函数中抽取的动态迁移逻辑

-- 添加 pay_time 列
ALTER TABLE youzan_orders ADD COLUMN pay_time TEXT DEFAULT '';

-- 添加 consign_time 列
ALTER TABLE youzan_orders ADD COLUMN consign_time TEXT DEFAULT '';

-- 添加 pay_type_str 列
ALTER TABLE youzan_orders ADD COLUMN pay_type_str TEXT DEFAULT '';

-- 添加 express_type 列
ALTER TABLE youzan_orders ADD COLUMN express_type INTEGER DEFAULT 0;

-- 添加 refund_state 列
ALTER TABLE youzan_orders ADD COLUMN refund_state INTEGER DEFAULT 0;

-- 添加 post_fee_fen 列
ALTER TABLE youzan_orders ADD COLUMN post_fee_fen INTEGER DEFAULT 0;

-- 添加 discount_fen 列
ALTER TABLE youzan_orders ADD COLUMN discount_fen INTEGER DEFAULT 0;

-- 添加 delivery_province 列
ALTER TABLE youzan_orders ADD COLUMN delivery_province TEXT DEFAULT '';

-- 添加 delivery_city 列
ALTER TABLE youzan_orders ADD COLUMN delivery_city TEXT DEFAULT '';

-- 添加 delivery_district 列
ALTER TABLE youzan_orders ADD COLUMN delivery_district TEXT DEFAULT '';

-- 添加 delivery_time 列
ALTER TABLE youzan_orders ADD COLUMN delivery_time TEXT DEFAULT '';

-- 添加 outer_user_id 列
ALTER TABLE youzan_orders ADD COLUMN outer_user_id TEXT DEFAULT '';

-- 添加 order_items_json 列
ALTER TABLE youzan_orders ADD COLUMN order_items_json TEXT DEFAULT '[]';
