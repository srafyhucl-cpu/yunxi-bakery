import { isUsableMiniappSession } from "../services/session-store";

export interface MiniappSessionView {
  userId: string;
  openid: string;
  statusText: string;
  badgeText: string;
  hintText: string;
  actionText: string;
  loggedIn: boolean;
}

export function isMiniappLoggedIn(session: MiniappSession | null | undefined): boolean {
  return isUsableMiniappSession(session);
}

export function buildMiniappSessionView(session: MiniappSession | null | undefined): MiniappSessionView {
  const loggedIn = isMiniappLoggedIn(session);
  const isDemo = Boolean(session && session.isDemo);

  return {
    userId: session?.userId || "",
    openid: session?.openid || "",
    statusText: isDemo ? "体验账号" : "微信身份",
    badgeText: loggedIn ? "已登录" : "未登录",
    hintText: loggedIn ? "当前身份可用于查询订单和会员资产" : "登录后可查询订单和会员资产",
    actionText: loggedIn ? "刷新信息" : "去登录",
    loggedIn
  };
}
