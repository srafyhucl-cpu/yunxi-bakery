-- 迁移 v048：放开 youzan_webhook_events.business_type 的 CHECK 约束，加入 member 取值
--
-- 背景：有赞会员类事件（msg_id 前缀 yzuser_*）在 webhook 审计表中的 business_type 取值为
-- 'member'，但历史表结构的 CHECK 仅允许 ('trade','item','chat','unknown')，
-- 导致生产环境写审计记录时直接抛 "CHECK constraint failed: business_type IN (...)"，
-- 审计链路整体中断。
--
-- SQLite 不支持直接修改已存在表的 CHECK 约束，只能「重建表」：
--   1) 旧表改名备份；
--   2) 按最新字段定义创建新表，business_type 的 CHECK 增加 'member'；
--   3) 把历史审计数据整表拷贝回新表；
--   4) 删除备份表；
--   5) 重建原索引。
--
-- 安全性说明：
--   - 该表无外键、无触发器、无视图依赖，重建过程不触碰任何其它表；
--   - 全流程包在单个事务内，中途异常会整体回滚，不会留下「表已改名但数据未拷贝」的半成品；
--   - 重复执行安全：备份表名固定为 youzan_webhook_events_old，改名后必然存在，
--     开头的清理语句仅用于兜底异常中断残留的备份表。

BEGIN IMMEDIATE;

-- 兜底清理异常中断残留的备份表
DROP TABLE IF EXISTS youzan_webhook_events_old;

-- 旧表改名备份
ALTER TABLE youzan_webhook_events RENAME TO youzan_webhook_events_old;

-- 按最新字段定义重建表（business_type 放开 member，其余字段/默认值/主键保持不变）
CREATE TABLE youzan_webhook_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_id TEXT NOT NULL UNIQUE,
    trace_id TEXT DEFAULT '',
    event_type TEXT DEFAULT '',
    business_type TEXT NOT NULL
        CHECK(business_type IN ('trade','item','chat','member','unknown')),
    business_key TEXT DEFAULT '',
    status TEXT NOT NULL
        CHECK(status IN ('received','processing','processed','skipped','failed','duplicate')),
    http_status INTEGER DEFAULT 200,
    process_stage TEXT DEFAULT '',
    error_type TEXT DEFAULT '',
    error_message TEXT DEFAULT '',
    payload_hash TEXT DEFAULT '',
    payload_summary_json TEXT DEFAULT '{}',
    received_at TEXT NOT NULL,
    process_started_at TEXT,
    process_finished_at TEXT,
    duration_ms INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- 拷贝历史审计数据
INSERT INTO youzan_webhook_events (
    id, msg_id, trace_id, event_type, business_type, business_key, status,
    http_status, process_stage, error_type, error_message, payload_hash,
    payload_summary_json, received_at, process_started_at, process_finished_at,
    duration_ms, created_at, updated_at
)
SELECT
    id, msg_id, trace_id, event_type, business_type, business_key, status,
    http_status, process_stage, error_type, error_message, payload_hash,
    payload_summary_json, received_at, process_started_at, process_finished_at,
    duration_ms, created_at, updated_at
FROM youzan_webhook_events_old;

-- 删除备份表
DROP TABLE youzan_webhook_events_old;

-- 重建索引
CREATE INDEX IF NOT EXISTS idx_ywe_received ON youzan_webhook_events(received_at);
CREATE INDEX IF NOT EXISTS idx_ywe_status ON youzan_webhook_events(status);
CREATE INDEX IF NOT EXISTS idx_ywe_event_type ON youzan_webhook_events(event_type);
CREATE INDEX IF NOT EXISTS idx_ywe_business_key ON youzan_webhook_events(business_key);

COMMIT;
