/**
 * 下单失败文案转换。
 *
 * 后端订单校验抛出的异常文本面向门店运营（例如“未配置每日库存，请先在后台录入”），
 * 顾客既看不懂也做不了；这里只把顾客能照做的动作翻出来，技术细节留在接口响应和日志里。
 */

/** 内部运营口径的措辞：出现即说明顾客侧无法自助解决，必须换成可行动文案。 */
const OPERATOR_ONLY_PATTERN = /每日库存|后台录入|未配置/;

const STOCK_UNAVAILABLE_MESSAGE = "所选日期该商品暂不可预订，请换个日期或联系门店";

/** 业务错误末尾常带商品 ID，展示时去掉，避免顾客看到一串数字。 */
const TRAILING_PRODUCT_ID_PATTERN = /[:：]\s*\d{6,}\s*$/;

const FALLBACK_MESSAGE = "下单没成功，请稍后重试；多次失败请联系门店";

export function toCustomerOrderError(raw: string): string {
  const text = (raw || "").trim();
  if (!text) {
    return FALLBACK_MESSAGE;
  }
  if (OPERATOR_ONLY_PATTERN.test(text)) {
    return STOCK_UNAVAILABLE_MESSAGE;
  }
  return text.replace(TRAILING_PRODUCT_ID_PATTERN, "");
}
