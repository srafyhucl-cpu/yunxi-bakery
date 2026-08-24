-- 迁移：为 youzan_products 表添加扩展列
-- 日期：2026-06-06
-- 说明：从 database.py 的 init_db() 函数中抽取的动态迁移逻辑

-- 添加 skus_json 列
ALTER TABLE youzan_products ADD COLUMN skus_json TEXT DEFAULT '[]';

-- 添加 desc 列
ALTER TABLE youzan_products ADD COLUMN desc TEXT DEFAULT '';

-- 添加 tags 列
ALTER TABLE youzan_products ADD COLUMN tags TEXT DEFAULT '';

-- 添加 item_props_json 列
ALTER TABLE youzan_products ADD COLUMN item_props_json TEXT DEFAULT '[]';

-- 添加 last_sync_source 列
ALTER TABLE youzan_products ADD COLUMN last_sync_source TEXT DEFAULT 'product_reconcile';
UPDATE youzan_products SET last_sync_source = 'product_reconcile' WHERE last_sync_source IS NULL OR last_sync_source = '';

-- 添加 last_sync_ref 列
ALTER TABLE youzan_products ADD COLUMN last_sync_ref TEXT DEFAULT '';

-- 添加 sold_num 列
ALTER TABLE youzan_products ADD COLUMN sold_num INTEGER DEFAULT 0;

-- 添加 item_no 列
ALTER TABLE youzan_products ADD COLUMN item_no TEXT DEFAULT '';
