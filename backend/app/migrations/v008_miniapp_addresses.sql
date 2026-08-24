CREATE TABLE IF NOT EXISTS miniapp_addresses (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    receiver_name TEXT NOT NULL,
    receiver_phone TEXT NOT NULL,
    address TEXT NOT NULL,
    is_default INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_miniapp_addresses_user ON miniapp_addresses(user_id);

CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
