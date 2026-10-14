-- 积分外部权威锚点（r79，M-20260926-030）
-- `member_balance.points` 这一列此前同时承载两种**不兼容**的写入语义：
--   · 外部镜像（有赞 `POINTS` webhook、`member_loyalty` 全量导入）走
--     `upsert_identity(points=total)`，SQL 是
--     `points = CASE WHEN ? IS NOT NULL THEN ? ELSE points END`，即**绝对覆盖**；
--   · 本地订单发分 / 抵扣扣减 / 退款退返 / 退收回滚走
--     `PointsLedgerService.credit` / `deduct` → `credit_points` /
--     `deduct_points_if_sufficient`，即 `points = points ± ?` **相对增量**。
-- 有赞侧没有积分写接口（`member_api.py` 只有四个查询方法），本地发放的积分
-- 永远不会出现在有赞 `total` 里，于是任何一次外部变动都把本地已发积分抹掉；
-- 订单随后全额退款时按 `points:award` 流水收回这笔从未到账的积分，形成
-- **流水自洽但客户净损失**的结果，按流水对账查不出任何异常。
--
-- 本迁移把「外部权威总额」显式拆成独立锚点列，使余额恒等于
--     points = youzan_points_base（外部权威锚点） + 本地账本净额
-- 外部镜像只改锚点并按偏移量重算余额，本地账本只改余额（隐式改变净额），
-- 两种语义不再共用同一列的同一个含义。
--
-- 回填口径：既有行的 `youzan_points_base = points`，即「当前余额整体视为
-- 外部已镜像值，本地净额按 0 处理」。这是**唯一不发明数据**的保守口径——
-- 修复前的行为本就是「最近一次镜像后余额 == 有赞 total」，回填后首次镜像
-- 的结果与修复前完全一致，不产生回归。迁移前已被旧覆盖逻辑抹掉的本地发分
-- 无法从现有数据反推，本迁移不尝试追回（该场景只可能发生在从未对真实用户
-- 开放的开发期数据上，见上线红线）。

ALTER TABLE member_balance ADD COLUMN youzan_points_base INTEGER NOT NULL DEFAULT 0;

UPDATE member_balance SET youzan_points_base = points;
