SELECT 'kb_products' AS label, COUNT(*) AS n FROM knowledge_base WHERE category='product';
SELECT 'kb_no_youzan_id' AS label, COUNT(*) AS n FROM knowledge_base WHERE category='product' AND (youzan_item_id IS NULL OR youzan_item_id='');
SELECT 'yp_sold_gt0' AS label, COUNT(*) AS n FROM youzan_products WHERE sold_num > 0;
SELECT 'yp_sold_zero' AS label, COUNT(*) AS n FROM youzan_products WHERE sold_num = 0 OR sold_num IS NULL;
SELECT 'kb_matched_no_soldnum' AS label, COUNT(*) AS n
  FROM knowledge_base kb
  JOIN youzan_products yp ON yp.item_id = CAST(kb.youzan_item_id AS INTEGER)
 WHERE kb.category='product' AND (yp.sold_num = 0 OR yp.sold_num IS NULL);
