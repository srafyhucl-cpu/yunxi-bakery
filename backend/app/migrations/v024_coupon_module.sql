-- app/migrations/v024_coupon_module.sql
-- 优惠券模块（M4）
-- 1) coupon_inventory 重建：source 枚举扩展 local/order + 模板/有效期/核销列
-- 2) 新建 coupon_templates（券模板）
-- 3) 新建 coupon_grants（发券记录）

CREATE TABLE IF NOT EXISTS coupon_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    coupon_type TEXT NOT NULL DEFAULT '',
    threshold_fen INTEGER NOT NULL DEFAULT 0,
    value_fen INTEGER NOT NULL DEFAULT 0,
    discount_bp INTEGER NOT NULL DEFAULT 0,
    cap_fen INTEGER NOT NULL DEFAULT 0,
    valid_from TEXT NOT NULL DEFAULT '',
    valid_until TEXT NOT NULL DEFAULT '',
    scope_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active',
    source TEXT NOT NULL DEFAULT 'youzan',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_coupon_templates_type ON coupon_templates(coupon_type, status);

CREATE TABLE IF NOT EXISTS coupon_grants (
    id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL DEFAULT '',
    customer_id TEXT NOT NULL DEFAULT '',
    mobile TEXT NOT NULL DEFAULT '',
    coupon_code TEXT NOT NULL DEFAULT '',
    granted_by TEXT NOT NULL DEFAULT 'admin',
    channel TEXT NOT NULL DEFAULT 'admin',
    audience_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'granted',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_coupon_grants_mobile ON coupon_grants(mobile);
CREATE INDEX IF NOT EXISTS idx_coupon_grants_template ON coupon_grants(template_id);

CREATE TABLE IF NOT EXISTS coupon_inventory_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coupon_id TEXT NOT NULL DEFAULT '',
    coupon_group_id TEXT NOT NULL DEFAULT '',
    customer_id TEXT NOT NULL DEFAULT '',
    mobile TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    order_no TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    value_fen INTEGER NOT NULL DEFAULT 0,
    detail_json TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL DEFAULT 'webhook' CHECK(source IN ('webhook', 'import', 'local', 'order')),
    occurred_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    template_id TEXT NOT NULL DEFAULT '',
    valid_from TEXT NOT NULL DEFAULT '',
    valid_until TEXT NOT NULL DEFAULT '',
    deducted_fen INTEGER NOT NULL DEFAULT 0,
    consumed_at TEXT NOT NULL DEFAULT '',
    refunded_at TEXT NOT NULL DEFAULT ''
);
INSERT INTO coupon_inventory_new (id, coupon_id, coupon_group_id, customer_id, mobile, status, order_no, title, value_fen, detail_json, source, occurred_at, created_at)
SELECT id, coupon_id, coupon_group_id, customer_id, mobile, status, order_no, title, value_fen, detail_json, source, occurred_at, created_at FROM coupon_inventory;
DROP TABLE coupon_inventory;
ALTER TABLE coupon_inventory_new RENAME TO coupon_inventory;

CREATE UNIQUE INDEX IF NOT EXISTS idx_coupon_inventory_dedup ON coupon_inventory(coupon_id, status, mobile);
CREATE INDEX IF NOT EXISTS idx_coupon_inventory_mobile ON coupon_inventory(mobile);
CREATE INDEX IF NOT EXISTS idx_coupon_inventory_order ON coupon_inventory(order_no);
CREATE INDEX IF NOT EXISTS idx_coupon_inventory_latest ON coupon_inventory(coupon_id, mobile, occurred_at);
