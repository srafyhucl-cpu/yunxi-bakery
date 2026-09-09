-- 小程序北京闪送报价、配送单和回调事件表
CREATE TABLE IF NOT EXISTS delivery_quotes (
    quote_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    fulfillment_method TEXT NOT NULL CHECK(fulfillment_method IN ('pickup','beijing_delivery')),
    request_hash TEXT NOT NULL,
    goods_total_fen INTEGER NOT NULL CHECK(goods_total_fen >= 0),
    delivery_fee_fen INTEGER CHECK(delivery_fee_fen IS NULL OR delivery_fee_fen >= 0),
    quote_total_fen INTEGER CHECK(quote_total_fen IS NULL OR quote_total_fen >= 0),
    status TEXT NOT NULL CHECK(status IN ('quoting','quoted','expired','address_out_of_range','provider_unavailable','pending_confirmation')),
    provider TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT '',
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_delivery_quotes_user ON delivery_quotes(user_id, created_at);

CREATE TABLE IF NOT EXISTS delivery_orders (
    order_id TEXT PRIMARY KEY REFERENCES orders(id),
    provider TEXT NOT NULL,
    provider_order_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK(status IN ('not_applicable','pending_create','created','accepted','picking_up','delivering','delivered','cancelled','failed')),
    delivery_fee_fen INTEGER CHECK(delivery_fee_fen IS NULL OR delivery_fee_fen >= 0),
    pickup_address TEXT NOT NULL DEFAULT '',
    receiver_address TEXT NOT NULL DEFAULT '',
    last_synced_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS delivery_callback_events (
    event_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    received_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('received','processed','failed'))
);
CREATE INDEX IF NOT EXISTS idx_delivery_callback_provider ON delivery_callback_events(provider, received_at);
