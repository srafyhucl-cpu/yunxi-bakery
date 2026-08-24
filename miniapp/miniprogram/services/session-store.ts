import { STORAGE_KEYS } from "../constants/storage";

const DEFAULT_TOKEN_TYPE = "Bearer";
export const SESSION_EXPIRY_SKEW_MS = 60_000;

export function buildAnonymousSession(): MiniappSession {
  return {
    userId: "",
    openid: "",
    sessionReady: false,
    isDemo: false,
    accessToken: "",
    tokenType: DEFAULT_TOKEN_TYPE,
    expiresIn: 0,
    expiresAt: 0
  };
}

function normalizeStoredSession(value: unknown): MiniappSession | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const session = value as Partial<MiniappSession>;
  if (!session.userId) {
    return null;
  }
  const hasTokenMetadata = ["accessToken", "tokenType", "expiresIn", "expiresAt"].every((key) =>
    Object.prototype.hasOwnProperty.call(session, key)
  );
  if (!hasTokenMetadata && !session.isDemo) {
    return null;
  }
  return {
    userId: String(session.userId),
    openid: String(session.openid || ""),
    sessionReady: Boolean(session.sessionReady),
    isDemo: Boolean(session.isDemo),
    accessToken: String(session.accessToken || ""),
    tokenType: String(session.tokenType || DEFAULT_TOKEN_TYPE),
    expiresIn: Number(session.expiresIn || 0),
    expiresAt: Number(session.expiresAt || 0)
  };
}

function getStoredSession(): MiniappSession | null {
  return normalizeStoredSession(wx.getStorageSync(STORAGE_KEYS.miniappSession));
}

export function persistSession(session: MiniappSession): MiniappSession {
  const normalized: MiniappSession = {
    userId: session.userId || "",
    openid: session.openid || "",
    sessionReady: Boolean(session.sessionReady),
    isDemo: Boolean(session.isDemo),
    accessToken: session.accessToken || "",
    tokenType: session.tokenType || DEFAULT_TOKEN_TYPE,
    expiresIn: Number(session.expiresIn || 0),
    expiresAt: Number(session.expiresAt || 0)
  };
  wx.setStorageSync(STORAGE_KEYS.miniappSession, normalized);
  wx.setStorageSync(STORAGE_KEYS.miniappUserId, normalized.userId);
  return normalized;
}

export function clearMiniappSession(): void {
  wx.removeStorageSync(STORAGE_KEYS.miniappSession);
  wx.removeStorageSync(STORAGE_KEYS.miniappUserId);
}

export function clearMiniappSessionIfToken(accessToken: string): void {
  const storedSession = getStoredSession();
  if (storedSession?.accessToken === accessToken && accessToken) {
    clearMiniappSession();
  }
}

export function isUsableMiniappSession(
  session: MiniappSession | null | undefined
): session is MiniappSession {
  return Boolean(
    session &&
      session.sessionReady &&
      session.userId &&
      !session.isDemo &&
      session.accessToken &&
      session.tokenType.toLowerCase() === DEFAULT_TOKEN_TYPE.toLowerCase() &&
      Number.isFinite(session.expiresAt) &&
      session.expiresAt - Date.now() > SESSION_EXPIRY_SKEW_MS
  );
}

export function getMiniappSession(): MiniappSession {
  return getStoredSession() || buildAnonymousSession();
}

export function getMiniappUserId(): string {
  const session = getMiniappSession();
  return isUsableMiniappSession(session) ? session.userId : "";
}

export function buildDemoSession(): MiniappSession {
  return {
    ...buildAnonymousSession(),
    isDemo: true
  };
}

export function persistDemoMiniappSession(): MiniappSession {
  return persistSession(buildDemoSession());
}
