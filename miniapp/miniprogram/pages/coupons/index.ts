import { getMyCoupons } from "../../services/coupons";
import {
  classifyCouponStatus,
  type CouponTab,
  type MemberCoupon
} from "../../utils/member-assets";
import { formatFen } from "../../utils/money";
import { getErrorMessage } from "../../services/http";
import { getMiniappLayoutMetrics } from "../../utils/layout";
import { isMiniappLoggedIn } from "../../utils/session";
import { getMiniappSession } from "../../services/auth";
import { goBackOrHome } from "../../utils/navigation";

const TABS: Array<{ key: CouponTab; title: string }> = [
  { key: "available", title: "可用" },
  { key: "used", title: "已用" },
  { key: "refunded", title: "已退回" },
  { key: "expired", title: "已过期" }
];

interface CouponCard {
  couponId: string;
  title: string;
  valueFen: number;
  thresholdFen: number;
  validText: string;
  note: string;
  orderNo: string;
  deductedFen: number;
  deductedText: string;
}

function toCard(coupon: MemberCoupon): CouponCard {
  const view = classifyCouponStatus(coupon);
  const validText = coupon.validFrom
    ? `${coupon.validFrom} ~ ${coupon.validUntil || "长期"}`
    : coupon.validUntil || "";
  return {
    couponId: coupon.couponId,
    title: coupon.title || "优惠券",
    valueFen: coupon.valueFen,
    thresholdFen: coupon.thresholdFen,
    validText,
    note: view.note,
    orderNo: coupon.orderNo,
    deductedFen: coupon.deductedFen,
    deductedText: formatFen(coupon.deductedFen)
  };
}

Page({
  data: {
    tabs: TABS,
    activeTab: "available" as CouponTab,
    groups: {} as Record<CouponTab, CouponCard[]>,
    loading: true,
    loadFailed: false,
    loggedIn: false,
    layoutStyle: getMiniappLayoutMetrics().pageShellStyle
  },
  onShow() {
    void this.loadCoupons();
  },
  switchTab(event: WechatMiniprogram.TouchEvent) {
    const key = event.currentTarget.dataset.tab as CouponTab;
    this.setData({ activeTab: key });
  },
  async loadCoupons() {
    const session = getMiniappSession();
    if (!isMiniappLoggedIn(session)) {
      this.setData({ loggedIn: false, loading: false });
      return;
    }
    this.setData({ loggedIn: true, loading: true, loadFailed: false });
    try {
      const data = await getMyCoupons();
      const groups: Record<CouponTab, CouponCard[]> = {
        available: [],
        used: [],
        refunded: [],
        expired: []
      };
      (data.coupons || []).forEach((coupon) => {
        const tab = classifyCouponStatus(coupon).tab;
        groups[tab].push(toCard(coupon));
      });
      this.setData({ groups, loading: false });
    } catch (error) {
      this.setData({ loading: false, loadFailed: true });
      wx.showToast({ title: getErrorMessage(error, "优惠券加载失败"), icon: "none" });
    }
  },
  goLogin() {
    wx.switchTab({ url: "/pages/profile/index" });
  },
  goBack() {
    goBackOrHome();
  }
});