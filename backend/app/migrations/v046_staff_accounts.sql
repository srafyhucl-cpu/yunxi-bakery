-- Stage 3C1 店员账号与操作审计（M46）
-- 店员使用手机号 + PIN 登录，会话与 ADMIN_API_TOKEN 完全隔离。
-- PIN 只保存 PBKDF2 派生值与独立盐，不保存明文；审计日志用于快捷开单追责。

CREATE TABLE IF NOT EXISTS staff_accounts (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'yunxi',
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('cashier','manager')),
    pin_hash TEXT NOT NULL,
    pin_salt TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    last_login_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(tenant_id, phone)
);

CREATE TABLE IF NOT EXISTS staff_audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL DEFAULT '',
    target_id TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_staff_audit_logs_staff_created
ON staff_audit_logs(staff_id, created_at);

CREATE INDEX IF NOT EXISTS idx_staff_audit_logs_action
ON staff_audit_logs(action);
