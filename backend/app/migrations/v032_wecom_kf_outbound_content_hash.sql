-- P1-1 外发投递合同：同一幂等键绑定内容哈希，不同内容必须冲突。
-- 幂等 runner 记录版本并容忍重复列，重复执行安全。
ALTER TABLE wecom_kf_outbound_ledger ADD COLUMN content_hash TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_kf_outbound_content ON wecom_kf_outbound_ledger(content_hash);
