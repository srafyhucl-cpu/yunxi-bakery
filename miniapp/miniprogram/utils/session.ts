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
    statusText: isDemo ? "演示会话" : "微信登录",
    badgeText: loggedIn ? "已连接" : "未就绪",
    hintText: loggedIn ? "当前使用真实登录态" : "请先登录后继续使用",
    actionText: loggedIn ? "重新登录" : "去登录",
    loggedIn
  };
}
