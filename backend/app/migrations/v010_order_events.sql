CREATE TABLE IF NOT EXISTS order_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    status TEXT NOT NULL,
    operator TEXT NOT NULL DEFAULT 'system',
    note TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_order_events_order
    ON order_events(order_id);

CREATE INDEX IF NOT EXISTS idx_order_events_created
    ON order_events(created_at);
