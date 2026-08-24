import { ROUTES } from "../../constants/routes";
import { ensureMiniappSession, getMiniappSession } from "../../services/auth";
import { getBalance } from "../../services/balance";
import { getMyCoupons } from "../../services/coupons";
import { getErrorMessage } from "../../services/http";
import { getPublishedPageConfig } from "../../services/page-config";
import { RECHARGE_READY } from "../../services/payment-gate";
import { getPoints } from "../../services/points";
import { getShopSettings } from "../../services/shop-settings";
import { getMiniappLayoutMetrics } from "../../utils/layout";
import { classifyCouponStatus } from "../../utils/member-assets";
import { formatFen } from "../../utils/money";
import { navigateByLink } from "../../utils/navigation";
import { buildMiniappSessionView } from "../../utils/session";
import { syncCustomTabBar } from "../../utils/tab-bar";
import type { MemberSummaryProps } from "../../types/page-config";

interface OrderEntry {
  id: string;
  title: string;
  emoji: string;
  linkType: string;
  linkTarget: string;
}

const PROFILE_ORDER_ENTRIES: OrderEntry[] = [
  { id: "to-pay", title: "待付款", emoji: "💳", linkType: "page", linkTarget: "orders" },
  { id: "making", title: "制作中", emoji: "👨‍🍳", linkType: "page", linkTarget: "orders" },
  { id: "delivery", title: "待配送", emoji: "🛵", linkType: "page", linkTarget: "orders" },
  { id: "refund", title: "退款/售后", emoji: "🔄", linkType: "policy", linkTarget: "afterSales" },
];

function normalizeMemberSummaryProps(props: Partial<MemberSummaryProps>): MemberSummaryProps {
  return {
    greeting: props.greeting || "HI",
    name: props.name || "微信用户",
    levelText: props.levelText || "注册会员",
    cardSubtitle: props.cardSubtitle || "单笔充值 1000 元升级",
    cardValidity: props.cardValidity || "永久有效",
    points: Number(props.points ?? 0),
    coupons: Number(props.coupons ?? 0),
    balanceFen: Number(props.balanceFen ?? 0),
    benefitCardCount: Number(props.benefitCardCount ?? 0)
  };
}

Page({
  data: {
    memberProps: {} as MemberSummaryProps,
    balanceText: "",
    assetBalanceFen: 0 as number | null,
    assetPoints: 0 as number | null,
    assetCouponCount: 0 as number | null,
    assetsLoaded: false,
    rechargeReady: RECHARGE_READY,
    serviceItems: [] as Array<{ id: string; title: string; emoji: string; subtitle?: string; linkType: string; linkTarget: string }>,
    session: getMiniappSession(),
    sessionView: buildMiniappSessionView(getMiniappSession()),
    loginStateText: "个人中心需要登录后使用",
    loaded: false,
    loading: false,
    refreshingSession: false,
    orderEntries: PROFILE_ORDER_ENTRIES,
    layoutStyle: getMiniappLayoutMetrics().pageShellStyle
  },
  onLoad() {
    void this.loadProfile();
  },
  onShow() {
    syncCustomTabBar(ROUTES.profile);
    // Refresh session view state on show to catch login state changes
    const session = getMiniappSession();
    this.setData({
      session,
      sessionView: buildMiniappSessionView(session)
    });
  },
  async loadProfile() {
    if (this.data.loaded || this.data.loading) {
      return;
    }
    this.setData({ loading: true });
    void this.loadMemberAssets();
    try {
      const config = await getPublishedPageConfig("profile");
      const shopSettings = await getShopSettings();
      const session = getMiniappSession();

      const memberBlock = config.blocks?.find((b) => b.type === "memberSummary");
      const rawProps = memberBlock ? memberBlock.props : {};
      const memberProps = normalizeMemberSummaryProps(rawProps);

      const serviceItems = [
        { id: "shop-phone", title: "客服电话", emoji: "📞", subtitle: shopSettings.customerPhone, linkType: "phone", linkTarget: shopSettings.customerPhone },
        { id: "shop-wechat", title: "客服微信", emoji: "💬", subtitle: shopSettings.customerWechat, linkType: "wechat", linkTarget: shopSettings.customerWechat },
        { id: "shop-after-sales", title: shopSettings.afterSalesPolicyTitle || "售后政策", emoji: "🛡️", linkType: "policy", linkTarget: "afterSales" },
        { id: "shop-agreement", title: shopSettings.userAgreementTitle || "用户协议", emoji: "📄", linkType: "policy", linkTarget: "agreement" },
        { id: "shop-privacy", title: shopSettings.privacyPolicyTitle || "隐私政策", emoji: "🔒", linkType: "policy", linkTarget: "privacy" }
      ];

      this.setData({
        memberProps,
        serviceItems,
        session,
        sessionView: buildMiniappSessionView(session),
        loginStateText:
          session.sessionReady && session.userId && !session.isDemo
            ? "已使用真实登录态进入个人中心"
            : "请先登录后使用个人中心",
        loaded: true
      });
    } finally {
      this.setData({ loading: false });
    }
  },
  async loadMemberAssets() {
    try {
      const [balance, points, couponsData] = await Promise.all([
        getBalance(),
        getPoints(),
        getMyCoupons()
      ]);
      const availableCoupons = (couponsData.coupons || []).filter(
        (coupon) => classifyCouponStatus(coupon).tab === "available"
      );
      this.setData({
        assetBalanceFen: balance.balanceFen,
        assetPoints: points.pointsBalance,
        assetCouponCount: availableCoupons.length,
        balanceText: formatFen(balance.balanceFen),
        assetsLoaded: true
      });
    } catch (error) {
      // 单项整体失败降级：保持 "--" 占位，不阻塞页面（401 由 http 层会话刷新兜底）
      this.setData({
        assetBalanceFen: null,
        assetPoints: null,
        assetCouponCount: null,
        assetsLoaded: true
      });
    }
  },
  async refreshSession() {
    if (this.data.refreshingSession) {
      return;
    }

    this.setData({ refreshingSession: true });
    try {
      const session = await ensureMiniappSession({ forceRefresh: true });
      this.setData({
        session,
        sessionView: buildMiniappSessionView(session)
      });
      // Re-load profile to fetch potential member details after login
      this.setData({ loaded: false, assetsLoaded: false });
      await this.loadProfile();
      wx.showToast({ title: "登录已更新", icon: "none" });
    } catch (error) {
      const message = getErrorMessage(error, "登录更新失败，请稍后重试");
      this.setData({ loginStateText: message });
      wx.showModal({
        title: "登录更新失败",
        content: message,
        showCancel: false
      });
    } finally {
      this.setData({ refreshingSession: false });
    }
  },
  openOrders() {
    wx.navigateTo({
      url: ROUTES.orders
    });
  },
  openRecharge() {
    if (!RECHARGE_READY) {
      wx.showToast({ title: "充值功能即将上线", icon: "none" });
      return;
    }
    wx.navigateTo({ url: ROUTES.recharge });
  },
  openPoints() {
    wx.navigateTo({ url: ROUTES.points });
  },
  openCoupons() {
    wx.navigateTo({ url: ROUTES.coupons });
  },
  handleOrderTap(event: WechatMiniprogram.TouchEvent) {
    const linkType = event.currentTarget.dataset.linkType as string;
    const linkTarget = event.currentTarget.dataset.linkTarget as string;
    navigateByLink({ linkType, linkTarget });
  },
  handleServiceTap(event: WechatMiniprogram.TouchEvent) {
    const linkType = event.currentTarget.dataset.linkType as string;
    const linkTarget = event.currentTarget.dataset.linkTarget as string;
    navigateByLink({ linkType, linkTarget });
  }
});
