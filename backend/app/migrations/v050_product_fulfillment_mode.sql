-- 迁移 v050：商品履约方式覆盖
--
-- 背景：履约方式目前由「有赞 SKU 是否带尺寸 / 是否有定制属性」自动推导。
-- 少数固定尺寸蛋糕在有赞里没有规格数据，会被误判成现货；后台需要能按商品覆盖。
--
-- 取值：'' 自动推导，'preorder' 强制提前预订，'direct' 强制现货直购。
-- 默认空串，历史数据行为不变。

ALTER TABLE youzan_products ADD COLUMN fulfillment_mode TEXT NOT NULL DEFAULT '';
