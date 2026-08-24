-- 隐私生命周期：检索日志不再保存原始 query，只保存摘要和低敏分类
ALTER TABLE knowledge_retrieval_logs ADD COLUMN query_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE knowledge_retrieval_logs ADD COLUMN query_category TEXT NOT NULL DEFAULT '';
