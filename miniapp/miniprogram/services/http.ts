import { ensureMiniappSession } from "./auth";
import {
  clearMiniappSessionIfToken,
  getMiniappSession,
  isUsableMiniappSession
} from "./session-store";
import {
  RequestData,
  sendTransportRequest,
  HttpMethod
} from "./transport";

interface RequestOptions<TBody extends RequestData> {
  method?: HttpMethod;
  path: string;
  data?: TBody;
  retryOnUnauthorized?: boolean;
}

export interface ApiResponse<TData> {
  data: TData;
}

interface ErrorPayload {
  detail?: string;
  message?: string;
}

export class ApiError extends Error {
  statusCode: number;

  constructor(message: string, statusCode: number) {
    super(message);
    this.name = "ApiError";
    this.statusCode = statusCode;
  }
}

function extractErrorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object") {
    const errorPayload = payload as ErrorPayload;
    return errorPayload.detail || errorPayload.message || fallback;
  }
  return fallback;
}

export function getErrorMessage(error: unknown, fallback = "操作失败，请稍后重试"): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function buildHeaders(session: MiniappSession): WechatMiniprogram.IAnyObject {
  const headers: WechatMiniprogram.IAnyObject = {
    "content-type": "application/json"
  };
  if (isUsableMiniappSession(session)) {
    headers.Authorization = `${session.tokenType} ${session.accessToken}`;
  }
  return headers;
}

async function refreshSessionAfterUnauthorized(staleToken: string): Promise<void> {
  const currentSession = getMiniappSession();
  if (
    isUsableMiniappSession(currentSession) &&
    currentSession.accessToken !== staleToken
  ) {
    return;
  }
  await ensureMiniappSession({ forceRefresh: true });
}

async function requestWithRetry<
  TData,
  TBody extends RequestData
>(
  options: RequestOptions<TBody>,
  retryOnUnauthorized: boolean
): Promise<TData> {
  const session = getMiniappSession();
  const response = await sendTransportRequest<TData, TBody>({
    method: options.method,
    path: options.path,
    data: options.data,
    header: buildHeaders(session)
  });
  if (response.statusCode >= 200 && response.statusCode < 300) {
    return response.data;
  }

  if (response.statusCode === 401 && retryOnUnauthorized) {
    const staleToken = isUsableMiniappSession(session) ? session.accessToken : "";
    clearMiniappSessionIfToken(staleToken);
    try {
      await refreshSessionAfterUnauthorized(staleToken);
    } catch (error) {
      throw new ApiError(getErrorMessage(error, "登录会话已失效，请重新登录"), 401);
    }
    return requestWithRetry(
      { ...options, retryOnUnauthorized: false },
      false
    );
  }

  throw new ApiError(
    extractErrorMessage(response.data, `HTTP ${response.statusCode}`),
    response.statusCode
  );
}

export function request<
  TData,
  TBody extends RequestData = WechatMiniprogram.IAnyObject
>(
  options: RequestOptions<TBody>
): Promise<TData> {
  return requestWithRetry(
    options,
    options.retryOnUnauthorized !== false
  );
}
