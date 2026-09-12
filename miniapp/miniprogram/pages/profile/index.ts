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
import { buildMiniappSessionView, isMiniappLoggedIn } from "../../utils/session";
import { syncCustomTabBar } from "../../utils/tab-bar";
import type { MemberSummaryProps } from "../../types/page-config";

interface OrderEntry {
  id: string;
  title: string;
  iconText: string;
  linkType: string;
  linkTarget: string;
}

const PROFILE_ORDER_ENTRIES: OrderEntry[] = [
  { id: "to-pay", title: "待付款", iconText: "付", linkType: "page", linkTarget: "orders" },
  { id: "making", title: "制作中", iconText: "制", linkType: "page", linkTarget: "orders" },
  { id: "delivery", title: "待配送", iconText: "送", linkType: "page", linkTarget: "orders" },
  { id: "refund", title: "退款/售后", iconText: "售", linkType: "policy", linkTarget: "afterSales" },
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
    serviceItems: [] as Array<{ id: string; title: string; iconText: string; subtitle?: string; linkType: string; linkTarget: string }>,
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
    // 页面显示时刷新会话视图，及时反映登录状态变化
    const session = getMiniappSession();
    const wasLoggedIn = Boolean(this.data.sessionView?.loggedIn);
    const isLoggedIn = isMiniappLoggedIn(session);
    this.setData({
      session,
      sessionView: buildMiniappSessionView(session)
    });
    // 若从未登录转为登录状态，或已登录但资产尚未完成加载，则加载资产
    if (isLoggedIn && (!wasLoggedIn || !this.data.assetsLoaded)) {
      void this.loadMemberAssets();
    }
  },
  async loadProfile() {
    if (this.data.loaded || this.data.loading) {
      return;
    }
    this.setData({ loading: true });
    try {
      const config = await getPublishedPageConfig("profile");
      const shopSettings = await getShopSettings();
      const session = getMiniappSession();

      const memberBlock = config.blocks?.find((b) => b.type === "memberSummary");
      const rawProps = memberBlock ? memberBlock.props : {};
      const memberProps = normalizeMemberSummaryProps(rawProps);

      const serviceItems = [
        { id: "shop-phone", title: "客服电话", iconText: "电", subtitle: shopSettings.customerPhone, linkType: "phone", linkTarget: shopSettings.customerPhone },
        { id: "shop-wechat", title: "客服微信", iconText: "微", subtitle: shopSettings.customerWechat, linkType: "wechat", linkTarget: shopSettings.customerWechat },
        { id: "shop-after-sales", title: shopSettings.afterSalesPolicyTitle || "售后政策", iconText: "售", linkType: "policy", linkTarget: "afterSales" },
        { id: "shop-agreement", title: shopSettings.userAgreementTitle || "用户协议", iconText: "协", linkType: "policy", linkTarget: "agreement" },
        { id: "shop-privacy", title: shopSettings.privacyPolicyTitle || "隐私政策", iconText: "隐", linkType: "policy", linkTarget: "privacy" }
      ];

      this.setData({
        memberProps,
        serviceItems,
        session,
        sessionView: buildMiniappSessionView(session),
        loginStateText:
          isMiniappLoggedIn(session)
            ? "会员信息已关联当前微信身份"
            : "请先登录后使用个人中心",
        loaded: true
      });

      // 仅在登录状态有效时拉取资产，未登录不请求受保护接口
      if (isMiniappLoggedIn(session)) {
        void this.loadMemberAssets();
      } else {
        this.setData({
          assetBalanceFen: null,
          assetPoints: null,
          assetCouponCount: null,
          balanceText: "--",
          assetsLoaded: true
        });
      }
    } finally {
      this.setData({ loading: false });
    }
  },
  async loadMemberAssets() {
    const session = getMiniappSession();
    // 守卫：未登录直接将资产置为空态，严禁发出未授权请求
    if (!isMiniappLoggedIn(session)) {
      this.setData({
        assetBalanceFen: null,
        assetPoints: null,
        assetCouponCount: null,
        balanceText: "--",
        assetsLoaded: true
      });
      return;
    }

    try {
      const [balanceRes, pointsRes, couponsRes] = await Promise.allSettled([
        getBalance(),
        getPoints(),
        getMyCoupons()
      ]);

      const balanceFen = balanceRes.status === "fulfilled" ? balanceRes.value.balanceFen : 0;
      const points = pointsRes.status === "fulfilled" ? pointsRes.value.pointsBalance : 0;
      const couponsData = couponsRes.status === "fulfilled" ? couponsRes.value : { coupons: [] };

      const availableCoupons = (couponsData.coupons || []).filter(
        (coupon) => classifyCouponStatus(coupon).tab === "available"
      );
      this.setData({
        assetBalanceFen: balanceFen,
        assetPoints: points,
        assetCouponCount: availableCoupons.length,
        balanceText: formatFen(balanceFen),
        assetsLoaded: true
      });
    } catch {
      // 容错降级：保持稳定占位，不阻塞页面也不抛出未捕获错误
      this.setData({
        assetBalanceFen: null,
        assetPoints: null,
        assetCouponCount: null,
        balanceText: "--",
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
      // 登录后重新加载个人资料，获取可能新增的会员信息
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
