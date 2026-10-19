import { CHAT_DEFAULT_STATUS } from "../constants/chat";
import type {
  ChatMessage,
  ChatPayload,
  ChatStatus,
  CustomizationCard,
  CustomizationCardRequest
} from "../types/chat";
import { request } from "./http";

export type {
  ChatMessage,
  ChatPayload,
  ChatStatus,
  CustomizationCard,
  CustomizationCardRequest
} from "../types/chat";

interface SendChatMessageResponse {
  sessionId: string;
  reply: string;
  messages: ChatMessage[];
  status?: ChatStatus;
}

interface WrappedApiResponse<TData> {
  code: number;
  data: TData;
}

function unwrapResponse<TData>(response: WrappedApiResponse<TData> | TData): TData {
  if (response && typeof response === "object" && "data" in response) {
    return (response as WrappedApiResponse<TData>).data;
  }
  return response as TData;
}

export async function getChatPayload(): Promise<ChatPayload> {
  const response = await request<WrappedApiResponse<ChatPayload> | ChatPayload>({
    path: "/api/v1/miniapp/chat/messages"
  });
  const data = unwrapResponse(response);
  if (Array.isArray(data)) {
    return {
      messages: data,
      status: CHAT_DEFAULT_STATUS
    };
  }
  return data;
}

// AI 消息走 LLM（实测冷启动可达 48 秒），默认 12 秒必超时，故单独放宽
const CHAT_SEND_TIMEOUT_MS = 60000;

export async function sendChatMessage(content: string): Promise<SendChatMessageResponse> {
  const response = await request<WrappedApiResponse<SendChatMessageResponse>, { content: string }>({
    method: "POST",
    path: "/api/v1/miniapp/chat/messages",
    data: { content },
    timeoutMs: CHAT_SEND_TIMEOUT_MS
  });
  return unwrapResponse(response);
}

export async function requestHumanTransfer(reason = ""): Promise<ChatPayload> {
  const response = await request<WrappedApiResponse<ChatPayload>, { reason: string }>({
    method: "POST",
    path: "/api/v1/miniapp/chat/transfer",
    data: { reason }
  });
  return unwrapResponse(response);
}

// 需求卡校验包含预约时间规则，默认 12 秒超时偏紧，单独放宽到 20 秒。
const CUSTOMIZATION_CARD_TIMEOUT_MS = 20000;

/**
 * 提交定制需求并取回结构化需求卡。
 * 后端只做校验与文本化：不建单、不扣款、不占时段，因此本方法没有任何交易副作用。
 */
export async function buildCustomizationCard(
  payload: CustomizationCardRequest
): Promise<CustomizationCard> {
  const response = await request<
    WrappedApiResponse<CustomizationCard> | CustomizationCard,
    CustomizationCardRequest
  >({
    method: "POST",
    path: "/api/v1/miniapp/chat/customization-card",
    data: payload,
    timeoutMs: CUSTOMIZATION_CARD_TIMEOUT_MS
  });
  return unwrapResponse(response);
}
