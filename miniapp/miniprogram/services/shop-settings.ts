import { request } from "./http";
import { SHOP_CONFIG } from "../config/shop";
import { createCachedLoader, type CachedLoaderOptions } from "../utils/cache";

export interface ShopSettings {
  shopName: string;
  customerWechat: string;
  customerPhone: string;
  businessHours: string;
  pickupAddress: string;
  deliveryNotice: string;
  pickupNotice: string;
  paymentMode: string;
  privacyPolicyTitle: string;
  privacyPolicyContent: string;
  userAgreementTitle: string;
  userAgreementContent: string;
  afterSalesPolicyTitle: string;
  afterSalesPolicyContent: string;
}

const DEFAULT_POLICY_TEXT = {
  privacyPolicyTitle: "隐私政策",
  privacyPolicyContent:
    "我们仅在下单、配送、客服和售后所必需的范围内收集联系人、手机号、地址、订单备注等信息，并用于完成蛋糕预订、履约通知和售后服务。未经用户授权，不会将个人信息用于无关用途。",
  userAgreementTitle: "用户协议",
  userAgreementContent:
    "用户在芸熙烘焙小程序下单前，应确认商品规格、取货或配送时间、联系人和备注信息。定制蛋糕请提前与客服确认可制作内容；订单提交后如需修改，请尽快联系客服处理。",
  afterSalesPolicyTitle: "售后说明",
  afterSalesPolicyContent:
    "蛋糕属于即时制作食品，请在约定时间取货或收货。若出现配送破损、商品错漏或质量问题，请保留照片和订单信息并第一时间联系客服，我们会按实际情况协助补救、重做或退款。",
};

interface WrappedApiResponse<TData> {
  code: number;
  data: TData;
}

const SHOP_SETTINGS_CACHE_TTL_MS = 5 * 60 * 1000;

function normalizeSettings(value: Partial<ShopSettings> | null | undefined): ShopSettings {
  return {
    shopName: value?.shopName?.trim() || SHOP_CONFIG.name,
    customerWechat: value?.customerWechat?.trim() || SHOP_CONFIG.customerWechat,
    customerPhone: value?.customerPhone?.trim() || SHOP_CONFIG.customerPhone,
    businessHours: value?.businessHours?.trim() || SHOP_CONFIG.businessHours,
    pickupAddress: value?.pickupAddress?.trim() || SHOP_CONFIG.pickupAddress,
    deliveryNotice:
      value?.deliveryNotice?.trim() || "门店配送需提前预约，配送范围和费用以客服确认为准",
    pickupNotice:
      value?.pickupNotice?.trim() || "蛋糕建议提前 24 小时预订，到店自提前请确认取货时间",
    paymentMode: value?.paymentMode?.trim() || "mock",
    privacyPolicyTitle: value?.privacyPolicyTitle?.trim() || DEFAULT_POLICY_TEXT.privacyPolicyTitle,
    privacyPolicyContent:
      value?.privacyPolicyContent?.trim() || DEFAULT_POLICY_TEXT.privacyPolicyContent,
    userAgreementTitle: value?.userAgreementTitle?.trim() || DEFAULT_POLICY_TEXT.userAgreementTitle,
    userAgreementContent:
      value?.userAgreementContent?.trim() || DEFAULT_POLICY_TEXT.userAgreementContent,
    afterSalesPolicyTitle:
      value?.afterSalesPolicyTitle?.trim() || DEFAULT_POLICY_TEXT.afterSalesPolicyTitle,
    afterSalesPolicyContent:
      value?.afterSalesPolicyContent?.trim() || DEFAULT_POLICY_TEXT.afterSalesPolicyContent,
  };
}

async function fetchShopSettings(): Promise<ShopSettings> {
  try {
    const response = await request<WrappedApiResponse<ShopSettings>>({
      path: "/api/v1/miniapp/shop-settings",
    });
    if (response && typeof response === "object" && "data" in response) {
      return normalizeSettings(response.data);
    }
  } catch {
    // 后台运营配置不可用时回落本地默认值，保证小程序可运行。
  }
  return normalizeSettings(null);
}

const cachedFetchShopSettings = createCachedLoader(fetchShopSettings, () => "shop-settings");

export async function getShopSettings(
  cacheOptions: Partial<CachedLoaderOptions> = {}
): Promise<ShopSettings> {
  return cachedFetchShopSettings({
    ttlMs: SHOP_SETTINGS_CACHE_TTL_MS,
    ...cacheOptions
  });
}
