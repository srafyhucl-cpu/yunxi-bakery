import { getShopSettings, type ShopSettings } from "../../services/shop-settings";
import { getMiniappLayoutMetrics } from "../../utils/layout";
import { goBackOrHome } from "../../utils/navigation";

type PolicyType = "privacy" | "agreement" | "afterSales";

interface PolicyView {
  title: string;
  content: string;
}

const POLICY_TYPE_LABELS: Record<PolicyType, string> = {
  privacy: "隐私政策",
  agreement: "用户协议",
  afterSales: "售后说明",
};

function normalizePolicyType(value: string | undefined): PolicyType {
  if (value === "agreement" || value === "afterSales") {
    return value;
  }
  return "privacy";
}

function buildPolicyView(settings: ShopSettings, type: PolicyType): PolicyView {
  if (type === "agreement") {
    return {
      title: settings.userAgreementTitle || POLICY_TYPE_LABELS.agreement,
      content: settings.userAgreementContent,
    };
  }
  if (type === "afterSales") {
    return {
      title: settings.afterSalesPolicyTitle || POLICY_TYPE_LABELS.afterSales,
      content: settings.afterSalesPolicyContent,
    };
  }
  return {
    title: settings.privacyPolicyTitle || POLICY_TYPE_LABELS.privacy,
    content: settings.privacyPolicyContent,
  };
}

Page({
  data: {
    policyTitle: POLICY_TYPE_LABELS.privacy,
    policyContent: "",
    loading: true,
    layoutStyle: getMiniappLayoutMetrics().pageShellStyle
  },
  onLoad(query: Record<string, string | undefined>) {
    const policyType = normalizePolicyType(query.type);
    void this.loadPolicy(policyType);
  },
  goBack() {
    goBackOrHome();
  },
  async loadPolicy(policyType: PolicyType) {
    this.setData({ loading: true });
    const settings = await getShopSettings();
    const policy = buildPolicyView(settings, policyType);
    this.setData({
      policyTitle: policy.title,
      policyContent: policy.content,
      loading: false,
    });
  },
});
