import {
  getMiniappSession,
  isUsableMiniappSession,
  persistSession
} from "./session-store";
import { sendTransportRequest } from "./transport";

interface WrappedApiResponse<TData> {
  code: number;
  data: TData;
}

interface MiniappLoginResponse {
  userId: string;
  openid: string;
  sessionReady: boolean;
  isDemo: boolean;
  accessToken: string;
  tokenType: string;
  expiresIn: number;
}

function unwrapResponse<TData>(response: WrappedApiResponse<TData> | TData): TData {
  if (response && typeof response === "object" && "data" in response) {
    return (response as WrappedApiResponse<TData>).data;
  }
  return response as TData;
}

function normalizeLoginResponse(payload: MiniappLoginResponse): MiniappSession {
  const expiresIn = Number(payload.expiresIn);
  const tokenType = String(payload.tokenType || "").trim();
  if (
    !payload.userId ||
    !payload.openid ||
    !payload.sessionReady ||
    payload.isDemo ||
    !payload.accessToken ||
    tokenType.toLowerCase() !== "bearer" ||
    !Number.isFinite(expiresIn) ||
    expiresIn <= 0
  ) {
    throw new Error("微信登录响应缺少有效服务端会话");
  }
  return {
    userId: String(payload.userId),
    openid: String(payload.openid),
    sessionReady: true,
    isDemo: false,
    accessToken: String(payload.accessToken),
    tokenType: "Bearer",
    expiresIn,
    expiresAt: Date.now() + expiresIn * 1000
  };
}

function requestLoginCode(): Promise<string> {
  return new Promise((resolve, reject) => {
    wx.login({
      success(result) {
        if (result.code) {
          resolve(result.code);
          return;
        }
        reject(new Error("wx.login failed"));
      },
      fail(error) {
        reject(new Error(error.errMsg));
      }
    });
  });
}

async function performMiniappLogin(): Promise<MiniappSession> {
  const loginCode = await requestLoginCode();
  const response = await sendTransportRequest<
    WrappedApiResponse<MiniappLoginResponse>,
    { code: string }
  >({
    method: "POST",
    path: "/api/v1/miniapp/auth/login",
    data: { code: loginCode }
  });
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw new Error("微信登录接口返回失败");
  }
  const payload = normalizeLoginResponse(unwrapResponse(response.data));
  return persistSession(payload);
}

let activeLoginPromise: Promise<MiniappSession> | null = null;

export async function ensureMiniappSession(
  options: { forceRefresh?: boolean } = {}
): Promise<MiniappSession> {
  const storedSession = getMiniappSession();
  if (isUsableMiniappSession(storedSession) && !options.forceRefresh) {
    return storedSession;
  }
  if (!activeLoginPromise) {
    activeLoginPromise = performMiniappLogin();
  }
  try {
    return await activeLoginPromise;
  } catch (error) {
    throw new Error(
      error instanceof Error && error.message ? error.message : "微信登录失败，请稍后重试"
    );
  } finally {
    activeLoginPromise = null;
  }
}

export { getMiniappSession, getMiniappUserId, persistDemoMiniappSession } from "./session-store";
