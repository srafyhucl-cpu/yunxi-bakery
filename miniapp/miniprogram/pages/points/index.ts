import { getPoints } from "../../services/points";
import { mapPointsSourceLabel, type PointsLedgerItem } from "../../utils/member-assets";
import { getErrorMessage } from "../../services/http";
import { getMiniappLayoutMetrics } from "../../utils/layout";
import { isMiniappLoggedIn } from "../../utils/session";
import { getMiniappSession } from "../../services/auth";
import { goBackOrHome } from "../../utils/navigation";

interface PointsRow {
  amount: number;
  total: number;
  label: string;
  occurredAt: string;
  displayTime: string;
}

function formatTime(value: string): string {
  const raw = value || "";
  return raw.replace("T", " ").slice(0, 16);
}

function toRow(item: PointsLedgerItem): PointsRow {
  return {
    amount: Number(item.amount || 0),
    total: Number(item.total || 0),
    label: mapPointsSourceLabel(item),
    occurredAt: item.occurred_at || "",
    displayTime: formatTime(item.occurred_at)
  };
}

Page({
  data: {
    pointsBalance: 0 as number | null,
    rows: [] as PointsRow[],
    loading: true,
    loadFailed: false,
    loggedIn: false,
    layoutStyle: getMiniappLayoutMetrics().pageShellStyle
  },
  onShow() {
    void this.loadPoints();
  },
  async loadPoints() {
    const session = getMiniappSession();
    if (!isMiniappLoggedIn(session)) {
      this.setData({ loggedIn: false, loading: false });
      return;
    }
    this.setData({ loggedIn: true, loading: true, loadFailed: false });
    try {
      const points = await getPoints();
      this.setData({
        pointsBalance: points.pointsBalance,
        rows: (points.ledger || []).map(toRow),
        loading: false
      });
    } catch (error) {
      this.setData({ loading: false, loadFailed: true });
      wx.showToast({ title: getErrorMessage(error, "积分明细加载失败"), icon: "none" });
    }
  },
  goLogin() {
    wx.switchTab({ url: "/pages/profile/index" });
  },
  goBack() {
    goBackOrHome();
  }
});
