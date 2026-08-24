-- 迁移：为 knowledge_base 表添加扩展列
-- 日期：2026-06-06
-- 说明：从 database.py 的 init_db() 函数中抽取的动态迁移逻辑

-- 添加 youzan_item_id 列和唯一索引
ALTER TABLE knowledge_base ADD COLUMN youzan_item_id TEXT DEFAULT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_kb_youzan_item_id ON knowledge_base(youzan_item_id);

-- 添加 last_sync_source 列
ALTER TABLE knowledge_base ADD COLUMN last_sync_source TEXT DEFAULT 'admin_manual';
UPDATE knowledge_base SET last_sync_source = 'admin_manual' WHERE last_sync_source IS NULL OR last_sync_source = '';

-- 添加 last_sync_ref 列
ALTER TABLE knowledge_base ADD COLUMN last_sync_ref TEXT DEFAULT '';

-- 添加 content_type 列
ALTER TABLE knowledge_base ADD COLUMN content_type TEXT DEFAULT 'faq';
UPDATE knowledge_base SET content_type = CASE 
    WHEN category = 'product' THEN 'product' 
    WHEN category = 'faq' THEN 'faq' 
    ELSE 'rule' END 
WHERE content_type IS NULL OR content_type = '';

-- 添加 content_origin 列
ALTER TABLE knowledge_base ADD COLUMN content_origin TEXT DEFAULT 'admin_manual';
UPDATE knowledge_base SET content_origin = 'admin_manual' WHERE content_origin IS NULL OR content_origin = '';

-- 添加 created_by 列
ALTER TABLE knowledge_base ADD COLUMN created_by TEXT DEFAULT '';

-- 添加 updated_by 列
ALTER TABLE knowledge_base ADD COLUMN updated_by TEXT DEFAULT '';

-- 添加 suggested_category 列
ALTER TABLE knowledge_base ADD COLUMN suggested_category TEXT DEFAULT '';

-- 添加 suggest_reason 列
ALTER TABLE knowledge_base ADD COLUMN suggest_reason TEXT DEFAULT '';

-- 添加 vector_sync_status 列
ALTER TABLE knowledge_base ADD COLUMN vector_sync_status TEXT DEFAULT 'pending';
UPDATE knowledge_base SET vector_sync_status = CASE 
    WHEN is_active = 1 THEN 'success' 
    ELSE 'pending' END 
WHERE vector_sync_status IS NULL OR vector_sync_status = '';

-- 添加 vector_synced_at 列
ALTER TABLE knowledge_base ADD COLUMN vector_synced_at TEXT DEFAULT '';
UPDATE knowledge_base SET vector_synced_at = updated_at WHERE is_active = 1 AND (vector_synced_at IS NULL OR vector_synced_at = '');

-- 添加 vector_sync_error 列
ALTER TABLE knowledge_base ADD COLUMN vector_sync_error TEXT DEFAULT '';

-- 添加 vector_sync_retry_count 列
ALTER TABLE knowledge_base ADD COLUMN vector_sync_retry_count INTEGER DEFAULT 0;
