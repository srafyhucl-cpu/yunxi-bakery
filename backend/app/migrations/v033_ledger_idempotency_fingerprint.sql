-- P0-4 幂等主体合同：账本流水绑定请求指纹。
-- 幂等 runner 记录版本并容忍重复列，重复执行安全；历史流水指纹为空，
-- 代码侧仍按明文字段（账户/业务/金额）比对，保证历史兼容。
ALTER TABLE balance_ledger ADD COLUMN request_fingerprint TEXT NOT NULL DEFAULT '';
ALTER TABLE points_ledger ADD COLUMN request_fingerprint TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_balance_ledger_fingerprint ON balance_ledger(request_fingerprint);
CREATE INDEX IF NOT EXISTS idx_points_ledger_fingerprint ON points_ledger(request_fingerprint);
