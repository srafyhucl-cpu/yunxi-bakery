/**
 * 数据观察台业务语义翻译与格式化工具函数。
 * 
 * 职责：
 * - 将冷冰冰的原始英文接口事件名、数据来源、修改动作翻译为直观的大白话中文；
 * - 从变更历史 (change_summary) 中提取具体的字段变化细节；
 * - 从 Webhook payload 摘要中提取关联业务的直观语义。
 */

// ── 来源接口映射 ──
const SOURCE_MAP: Record<string, string> = {
  youzan_webhook: "有赞云消息回调接口",
  admin_knowledge: "管理后台配置接口",
  admin_manual: "管理员手动操作",
  seed_knowledge: "种子数据初始化",
};

// ── Webhook 事件类型大白话映射 ──
const EVENT_TYPE_MAP: Record<string, string> = {
  // 商品相关
  item_info: "商品基本信息同步",
  item_state: "商品上下架状态变更",
  item_sku_info: "商品规格(SKU)信息更新",
  youzan_item_skustockorsoldnumupdated: "商品库存与销量变动",
  
  // 交易/订单相关
  trade_order_create: "买家提交订单",
  trade_order_pay: "买家付款完成",
  trade_order_confirm: "卖家确认发货",
  trade_order_success: "订单交易成功",
  trade_order_close: "订单交易关闭",
  trade_order_refund: "退款流程更新",
};

// ── 数据回写动作映射 ──
const ACTION_MAP: Record<string, string> = {
  insert: "新增数据入库",
  update: "修改/更新现有数据",
  delete: "物理删除数据",
  sync: "向量数据库同步",
};

// ── 实体类型映射 ──
const ENTITY_TYPE_MAP: Record<string, string> = {
  product: "商品知识",
  knowledge: "通用知识",
};

/**
 * 翻译数据来源
 */
export function formatSource(source: string): string {
  if (!source) return "系统后台";
  return SOURCE_MAP[source] || source;
}

/**
 * 翻译回写动作
 */
export function formatAction(action: string): string {
  if (!action) return "同步";
  return ACTION_MAP[action.toLowerCase()] || action;
}

/**
 * 翻译 Webhook 事件类型
 */
export function formatEventType(eventType: string): string {
  if (!eventType) return "通用事件推送";
  const lower = eventType.toLowerCase();
  return EVENT_TYPE_MAP[lower] || `事件: ${eventType}`;
}

/**
 * 翻译实体类型
 */
export function formatEntityType(entityType: string): string {
  if (!entityType) return "未知对象";
  return ENTITY_TYPE_MAP[entityType.toLowerCase()] || entityType;
}

const FIELD_NAME_MAP: Record<string, string> = {
  price_fen: "价格",
  stock: "可用库存",
  is_active: "上下架状态",
  tags: "配方标签",
  title: "商品名称/标题",
  alias: "有赞别名",
  category: "知识分类",
  priority: "检索优先级",
  skus_json: "规格规格/价格明细",
  item_props_json: "定制属性/加料",
  desc: "商品介绍正文",
  content: "知识内容正文",
  keywords: "检索关键词",
  youzan_item_id: "关联有赞商品 ID",
};

/**
 * 解析回写历史 change_summary (即 details)，并结合动作与来源，提取“具体做了什么”、覆盖字段与变动诱因
 */
export function parseChangeSummary(details: any, entityType: string, action?: string, source?: string): string {
  const changes: string[] = [];

  const typeLower = entityType?.toLowerCase() || "";
  const actionLower = action?.toLowerCase() || "";
  const sourceLower = source?.toLowerCase() || "";

  // 1. 如果有明确的对账联动下架原因
  if (details && details.reason === "youzan_not_onsale") {
    return "对账软下架 ── 每日全量对账发现有赞已下架，联动禁用本地记录，防止 AI 误推荐";
  }

  // 2. 软下架行为原因解释
  if (actionLower === "deactivate") {
    if (sourceLower === "product_reconcile") {
      return "对账软下架 ── 每日全量对账发现有赞已下架，联动禁用本地记录，防止 AI 误推荐";
    }
    if (sourceLower === "youzan_webhook") {
      return "本地防御性软下架 ── 收到有赞商品下架事件通知 (ITEM_STATE / ITEM_OFFSHELVE)，安全起见自动将本地记录置为禁用";
    }
    if (sourceLower === "admin_manual") {
      return "手动软下架 ── 管理员在后台手动关闭了该项知识的启用状态，暂停参与 AI 对话检索";
    }
    return `软下架 ── 该记录被置为禁用状态（触发源: ${formatSource(source || "")}）`;
  }

  // 3. 向量索引同步动作
  if (actionLower === "sync" || actionLower === "sync_retry") {
    changes.push("同步向量 ── 对知识点文本重新编码并同步至向量索引库以供 AI 检索");
    if (details && details.operator) {
      changes.push(`操作人: ${details.operator}`);
    }
    return changes.join(" | ");
  }

  // 4. 种子导入动作
  if (actionLower === "seed" || sourceLower === "seed_knowledge") {
    changes.push("系统初始化 ── 自动导入预设的种子 FAQ / 规则条目");
    if (details && details.title) {
      changes.push(`导入: ${details.title}`);
    }
    return changes.join(" | ");
  }

  // 5. 属性深度解释与覆盖字段说明
  if (details && typeof details === "object" && Object.keys(details).length > 0) {
    const bizKeys = Object.keys(details).filter(
      k => !["product_write_result", "knowledge_write_result", "updated_at", "item_id", "old_price_fen", "old_stock"].includes(k)
    );
    const translatedFields = bizKeys.map(k => FIELD_NAME_MAP[k] || k);

    // 分析修改的主导目的（为什么覆盖这些字段）
    let purpose = "";
    if (sourceLower === "chat_live_refresh") {
      purpose = "实时同步 ── 顾客咨询时，实时调取有赞最新数据以确保 AI 报价和库存准确";
    } else if (sourceLower === "product_reconcile") {
      purpose = "对账同步 ── 每日例行拉取有赞最新销量和编码以校正数据";
    } else if (bizKeys.includes("price_fen") && bizKeys.includes("stock")) {
      purpose = "业务同步 ── 同步有赞后台最新的商品价格和库存变动";
    } else if (bizKeys.includes("price_fen")) {
      purpose = "调价同步 ── 同步有赞后台最新的价格调整";
    } else if (bizKeys.includes("stock")) {
      purpose = "库存同步 ── 同步有赞后台最新的可用库存";
    } else if (bizKeys.includes("is_active")) {
      purpose = "状态同步 ── 同步商品在售/下架状态变动";
    } else if (typeLower === "product") {
      purpose = "信息同步 ── 同步有赞后台更新的商品基本信息(如标题/介绍/配方)";
    } else {
      purpose = "内容更新 ── 同步管理员在后台修改的知识条目正文与配置";
    }

    const highlightStyle = 'color: var(--el-color-danger); background-color: var(--el-color-danger-light-9); padding: 2px 6px; border-radius: 4px; margin-left: 4px; font-weight: bold; border: 1px solid var(--el-color-danger-light-7);';

    // 透出核心修改值与差异
    if (details.old_price_fen !== undefined && details.price_fen !== undefined && details.old_price_fen !== details.price_fen) {
      changes.push(`<span style="${highlightStyle}">价格变动: ¥${(details.old_price_fen / 100).toFixed(2)} → ¥${(details.price_fen / 100).toFixed(2)}</span>`);
    }

    if (details.old_stock !== undefined && details.stock !== undefined && details.old_stock !== details.stock) {
      changes.push(`<span style="${highlightStyle}">库存变动: ${details.old_stock} 件 → ${details.stock} 件</span>`);
    }

    let result = purpose;
    if (changes.length > 0) {
      result += ' ' + changes.join(' ');
    }
    
    return result;
  }

  // 6. 兜底动作解释
  if (actionLower === "activate") {
    return "启用 ── 本地数据库将该记录状态激活，重新参与 AI 检索";
  }
  if (actionLower === "create") {
    return "新增 ── 写入全新数据并自动触发向量编码";
  }

  return "同步属性 ── 覆盖写入该对象的数据字段";
}

/**
 * 解析 Webhook payload_summary 并提炼业务关联详情
 */
export function parseWebhookSummary(details: any, eventType: string, businessType: string, businessKey: string): string {
  const typeLower = eventType?.toLowerCase() || "";
  const bizTypeLower = businessType?.toLowerCase() || "";

  if (bizTypeLower === "trade" || typeLower.startsWith("trade_")) {
    return `订单协同 ── 关联单号: ${businessKey || details.id || "-"}`;
  }

  if (bizTypeLower === "item" || typeLower.startsWith("item_") || typeLower.includes("skustock")) {
    return `商品联动 ── 关联商品 ID: ${businessKey || "-"}`;
  }

  if (bizTypeLower === "chat") {
    return `在线咨询 ── 关联顾客 ID: ${businessKey || details.buyer_id || "-"}`;
  }

  return `其他业务 ── 标识: ${businessKey || "-"}`;
}
