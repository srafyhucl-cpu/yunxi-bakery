ALTER TABLE youzan_product_categories ADD COLUMN is_public INTEGER DEFAULT 1;
UPDATE youzan_product_categories SET is_public = 0 WHERE title LIKE '有赞分组 %';
