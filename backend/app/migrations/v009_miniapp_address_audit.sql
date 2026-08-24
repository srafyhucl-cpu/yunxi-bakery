CREATE TABLE IF NOT EXISTS miniapp_address_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    address_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    operator TEXT NOT NULL DEFAULT 'admin',
    action TEXT NOT NULL,
    before_json TEXT DEFAULT '{}',
    after_json TEXT DEFAULT '{}',
    note TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_miniapp_address_audit_address
    ON miniapp_address_audit(address_id);

CREATE INDEX IF NOT EXISTS idx_miniapp_address_audit_user
    ON miniapp_address_audit(user_id);

CREATE INDEX IF NOT EXISTS idx_miniapp_address_audit_created
    ON miniapp_address_audit(created_at);
