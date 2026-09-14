export const SHOP_CONFIG = {
  name: "芸熙烘焙",
  branchName: "银河SOHO店",
  displayName: "芸熙烘焙（银河SOHO店）",
  customerWechat: "13240240418",
  customerPhone: "13240240418",
  businessHours: "09:00-19:30",
  pickupAddress: "北京市东城区南竹杆胡同2号银河SOHO",
  defaultNotice: "定制蛋糕 + 客服微信：13240240418"
} as const;

export const THEME_TOKENS = {
  primaryColor: "#e94b4b",
  accentColor: "#9bb879",
  backgroundColor: "#f7f7f7"
} as const;

const PICKUP_ADDRESS_PLACEHOLDER_MARKERS = ["请联系客服确认"];

/**
 * 解析门店自提地址：空值或后台占位文案一律回落本地门店地址，
 * 避免占位文案进入顾客界面、闪送报价起点和订单快照。
 */
export function resolvePickupAddress(value?: string | null): string {
  const normalized = (value ?? "").trim();
  if (!normalized) {
    return SHOP_CONFIG.pickupAddress;
  }
  const isPlaceholder = PICKUP_ADDRESS_PLACEHOLDER_MARKERS.some((marker) =>
    normalized.includes(marker)
  );
  return isPlaceholder ? SHOP_CONFIG.pickupAddress : normalized;
}
