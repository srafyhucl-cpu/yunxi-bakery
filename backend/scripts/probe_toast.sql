SELECT id, title, youzan_item_id, is_active, last_sync_source, updated_at
FROM knowledge_base
WHERE title LIKE '%吐司%' AND category = 'product'
ORDER BY updated_at DESC;

SELECT id, title, youzan_item_id, is_active, last_sync_source, updated_at
FROM knowledge_base
WHERE youzan_item_id = '2792747323';
