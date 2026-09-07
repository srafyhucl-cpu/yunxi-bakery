-- P1-5 外发投递 owner 隔离：认领凭证绑定发送者，状态更新必须 fencing。
-- 幂等 runner 记录版本并容忍重复列，重复执行安全；历史行凭证为空，
-- 新认领一律签发新凭证，旧凭证无法再提交。
ALTER TABLE wecom_kf_outbound_ledger ADD COLUMN claim_token TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_kf_outbound_claim ON wecom_kf_outbound_ledger(claim_token);
