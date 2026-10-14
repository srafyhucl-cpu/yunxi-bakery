-- 会员储值区分实充本金与赠送金（M39）
-- 为 member_balance 表添加 principal_fen（实充本金）与 bonus_fen（赠送金）
-- 既有余额平滑迁移：当 principal_fen 与 bonus_fen 均为 0 且 stored_value_fen > 0 时，将 stored_value_fen 计为实充本金。

ALTER TABLE member_balance ADD COLUMN principal_fen INTEGER NOT NULL DEFAULT 0;
ALTER TABLE member_balance ADD COLUMN bonus_fen INTEGER NOT NULL DEFAULT 0;

UPDATE member_balance
SET principal_fen = stored_value_fen
WHERE principal_fen = 0 AND bonus_fen = 0 AND stored_value_fen > 0;
