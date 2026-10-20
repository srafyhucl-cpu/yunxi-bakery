-- Stage 2.5.4 每日现烤库存（M42）
-- 日常现烤（DAILY_READY）按“北京时间日期 + 商品”独立管理每日库存：
-- total_qty 为当日计划可售总量，reserved_qty 为已下单预占量，后台在 2.5.4B 录入。
-- 定制蛋糕（PREORDER_CAKE）继续使用 youzan_products.stock，不进入本表。
-- 约束保证预占量永不超过当日总量，避免并发预占超卖。

CREATE TABLE IF NOT EXISTS product_daily_stock (
    stock_date TEXT NOT NULL,
    product_id TEXT NOT NULL,
    total_qty INTEGER NOT NULL DEFAULT 0,
    reserved_qty INTEGER NOT NULL DEFAULT 0,
    updated_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (stock_date, product_id),
    CHECK(total_qty >= 0),
    CHECK(reserved_qty >= 0),
    CHECK(reserved_qty <= total_qty)
);

CREATE INDEX IF NOT EXISTS idx_pds_stock_date ON product_daily_stock(stock_date);

CREATE INDEX IF NOT EXISTS idx_pds_product_id ON product_daily_stock(product_id);
