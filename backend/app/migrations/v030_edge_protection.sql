-- 边缘防护共享状态：多 worker 与重启后保持一致的限流与登录保护。
CREATE TABLE IF NOT EXISTS rate_limit_windows (
    client_key TEXT PRIMARY KEY,
    window_start INTEGER NOT NULL DEFAULT 0,
    request_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS admin_login_attempts (
    client_key TEXT PRIMARY KEY,
    fail_count INTEGER NOT NULL DEFAULT 0,
    window_until INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
