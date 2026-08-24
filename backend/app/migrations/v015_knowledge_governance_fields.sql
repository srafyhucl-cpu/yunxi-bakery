-- 迁移：为 knowledge_base 增加发布治理字段
ALTER TABLE knowledge_base ADD COLUMN audience TEXT DEFAULT 'all';
UPDATE knowledge_base SET audience = 'all' WHERE audience IS NULL OR audience = '';

ALTER TABLE knowledge_base ADD COLUMN review_status TEXT DEFAULT 'published';
UPDATE knowledge_base
SET review_status = 'published'
WHERE review_status IS NULL OR review_status = '';

ALTER TABLE knowledge_base ADD COLUMN valid_from TEXT DEFAULT '';
ALTER TABLE knowledge_base ADD COLUMN valid_until TEXT DEFAULT '';
ALTER TABLE knowledge_base ADD COLUMN reviewed_by TEXT DEFAULT '';
ALTER TABLE knowledge_base ADD COLUMN reviewed_at TEXT DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_kb_governance_lookup
ON knowledge_base(is_active, review_status, audience, valid_from, valid_until);
