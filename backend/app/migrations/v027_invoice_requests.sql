-- app/migrations/v027_invoice_requests.sql
-- 发票请求登记表（P2 试运行准备：后台人工登记，不做电子发票直连）
-- 依据 docs/specs/2026-08-25-invoice-mvp-plan.md 方案表结构

CREATE TABLE IF NOT EXISTS invoice_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no TEXT NULL,
    customer_name TEXT NOT NULL DEFAULT '',
    company_title TEXT NOT NULL DEFAULT '',
    tax_no TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    amount_fen INTEGER NULL,
    status TEXT NOT NULL DEFAULT 'applied',
    issue_note TEXT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_invoice_requests_status ON invoice_requests (status);
