ALTER TABLE youzan_products ADD COLUMN tag_ids_json TEXT DEFAULT '[]';
CREATE INDEX IF NOT EXISTS idx_yp_tag_ids ON youzan_products(tag_ids_json);

CREATE TABLE IF NOT EXISTS youzan_product_categories (
    tag_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    sort INTEGER DEFAULT 0,
    product_count INTEGER DEFAULT 0,
    is_public INTEGER DEFAULT 1,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ypc_sort ON youzan_product_categories(sort, title);
