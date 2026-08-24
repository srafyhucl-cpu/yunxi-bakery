ALTER TABLE youzan_products ADD COLUMN classification_ids_json TEXT DEFAULT '[]';
ALTER TABLE youzan_products ADD COLUMN group_ids_json TEXT DEFAULT '[]';
ALTER TABLE youzan_products ADD COLUMN second_group_ids_json TEXT DEFAULT '[]';
ALTER TABLE youzan_products ADD COLUMN leaf_category_ids_json TEXT DEFAULT '[]';

CREATE INDEX IF NOT EXISTS idx_yp_classification_ids ON youzan_products(classification_ids_json);
CREATE INDEX IF NOT EXISTS idx_yp_group_ids ON youzan_products(group_ids_json);
CREATE INDEX IF NOT EXISTS idx_yp_second_group_ids ON youzan_products(second_group_ids_json);
CREATE INDEX IF NOT EXISTS idx_yp_leaf_category_ids ON youzan_products(leaf_category_ids_json);
