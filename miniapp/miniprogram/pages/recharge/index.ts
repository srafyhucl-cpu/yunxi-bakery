import { getBalance } from "../../services/balance";
import {
  createRecharge,
  mockPayRecharge,
  cancelRecharge,
  listRecharges,
  type RechargeRecord
} from "../../services/recharges";
import { RECHARGE_READY } from "../../services/payment-gate";
import {
  isValidRechargeAmount,
  MIN_RECHARGE_FEN,
  MAX_RECHARGE_FEN
} from "../../utils/member-assets";
import { RECHARGE_TIERS, hasRechargeBonus, type RechargeTier } from "../../utils/recharge-config";
import { formatFen } from "../../utils/money";
import { getErrorMessage } from "../../services/http";
import { getMiniappLayoutMetrics } from "../../utils/layout";
import { isMiniappLoggedIn } from "../../utils/session";
import { getMiniappSession } from "../../services/auth";
import { goBackOrHome } from "../../utils/navigation";

const STATUS_TEXT: Record<string, string> = {
  unpaid: "待支付",
  paid: "已到账",
  cancelled: "已取消",
  expired: "已过期"
};

Page({
  data: {
    ready: RECHARGE_READY,
    tiers: RECHARGE_TIERS as RechargeTier[],
    showBonus: hasRechargeBonus(),
    selectedTierFen: 10000,
    customFen: "",
    balanceFen: 0 as number | null,
    balanceText: "",
    statusTextMap: STATUS_TEXT,
    records: [] as RechargeRecord[],
    loading: true,
    submitting: false,
    loggedIn: false,
    layoutStyle: getMiniappLayoutMetrics().pageShellStyle
  },
  onShow() {
    void this.loadPage();
  },
  async loadPage() {
    const session = getMiniappSession();
    if (!isMiniappLoggedIn(session)) {
      this.setData({ loggedIn: false, loading: false });
      return;
    }
    this.setData({ loggedIn: true, loading: true });
    try {
      const [balance, records] = await Promise.all([getBalance(), listRecharges()]);
      this.setData({
        balanceFen: balance.balanceFen,
        balanceText: formatFen(balance.balanceFen),
        records,
        loading: false
      });
    } catch (error) {
      this.setData({ loading: false });
      wx.showToast({ title: getErrorMessage(error, "充值信息加载失败"), icon: "none" });
    }
  },
  selectTier(event: WechatMiniprogram.TouchEvent) {
    const amountFen = Number(event.currentTarget.dataset.fen);
    this.setData({ selectedTierFen: amountFen, customFen: "" });
  },
  onCustomInput(event: WechatMiniprogram.Input) {
    this.setData({ customFen: event.detail.value });
  },
  getAmountFen(): number {
    if (this.data.customFen) {
      const yuan = Number(this.data.customFen);
      return Math.round(yuan * 100);
    }
    return this.data.selectedTierFen;
  },
  async submitRecharge() {
    if (this.data.submitting) {
      return;
    }
    if (!RECHARGE_READY) {
      wx.showToast({ title: "充值功能即将上线", icon: "none" });
      return;
    }
    const amountFen = this.getAmountFen();
    if (!isValidRechargeAmount(amountFen)) {
      wx.showToast({
        title: `充值金额需在 ${MIN_RECHARGE_FEN / 100}~${MAX_RECHARGE_FEN / 100} 元之间`,
        icon: "none"
      });
      return;
    }
    this.setData({ submitting: true });
    try {
      const recharge = await createRecharge(amountFen);
      const confirmed = await new Promise<boolean>((resolve) => {
        wx.showModal({
          title: "确认充值",
          content: `充值金额 ${formatFen(recharge.amountFen)}，确认支付？`,
          confirmText: "确认支付",
          cancelText: "取消",
          success: (res) => resolve(Boolean(res.confirm)),
          fail: () => resolve(false)
        });
      });
      if (!confirmed) {
        this.setData({ submitting: false });
        return;
      }
      await mockPayRecharge(recharge.rechargeId);
      wx.showToast({ title: "充值成功", icon: "success" });
      await this.loadPage();
    } catch (error) {
      wx.showToast({ title: getErrorMessage(error, "充值失败，请稍后重试"), icon: "none" });
    } finally {
      this.setData({ submitting: false });
    }
  },
  cancelRecord(event: WechatMiniprogram.TouchEvent) {
    const rechargeId = event.currentTarget.dataset.id as string;
    wx.showModal({
      title: "取消充值",
      content: "确定取消这笔未支付充值？",
      success: async (res) => {
        if (!res.confirm) {
          return;
        }
        try {
          await cancelRecharge(rechargeId);
          await this.loadPage();
        } catch (error) {
          wx.showToast({ title: getErrorMessage(error, "取消失败"), icon: "none" });
        }
      }
    });
  },
  goBack() {
    goBackOrHome();
  }
});
