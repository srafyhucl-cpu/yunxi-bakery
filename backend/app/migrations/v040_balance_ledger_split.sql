-- Stage 2.5.1 本金/赠送金账务拆分（M40）
-- 为 balance_ledger 增加本金/赠送金带符号增量，使储值支付、退款与流水可精确还原结构，
-- 而不是只还原总额；amount_fen 保持原有带符号语义，恒满足
-- principal_delta_fen + bonus_delta_fen == amount_fen。
-- 历史流水没有赠送金拆分，按本金回填（principal_delta_fen = amount_fen，bonus_delta_fen = 0）。
-- runner 记录版本并容忍重复列，重复执行安全：ALTER 遇到重复列被跳过，
-- 回填仅在两个拆分列同时为 0 时执行，不会覆盖已拆分的新流水。

ALTER TABLE balance_ledger ADD COLUMN principal_delta_fen INTEGER NOT NULL DEFAULT 0;
ALTER TABLE balance_ledger ADD COLUMN bonus_delta_fen INTEGER NOT NULL DEFAULT 0;

UPDATE balance_ledger
SET principal_delta_fen = amount_fen, bonus_delta_fen = 0
WHERE principal_delta_fen = 0 AND bonus_delta_fen = 0 AND amount_fen != 0;

-- 会员余额也可能存在“只裸写 stored_value_fen（或外部绝对覆盖）而本金结构未维护”
-- 的行，导致认领/展示把 principalFen 读成 0。这里按“总额减赠送金”补齐本金，
-- 只在结构不自洽且总额不低于赠送金时执行，不改动任何总额。
UPDATE member_balance
SET principal_fen = stored_value_fen - bonus_fen
WHERE stored_value_fen >= bonus_fen AND principal_fen + bonus_fen != stored_value_fen;
