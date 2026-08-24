/**
 * 数据来源（SyncSource）中文标签映射。
 */
const SOURCE_LABEL_MAP: Record<string, string> = {
  admin_manual:      "人工录入",
  youzan_webhook:    "有赞推送",
  youzan_runtime:    "有赞推送",
  product_reconcile: "有赞对账同步",
  seed_knowledge:    "种子知识库",
  chat_live_refresh: "实时对话刷新",
  legacy_unknown:    "历史数据",
};

export function formatSyncSource(source: string | undefined | null): string {
  if (!source) {
    return "未记录";
  }
  return SOURCE_LABEL_MAP[source] ?? source;
}
