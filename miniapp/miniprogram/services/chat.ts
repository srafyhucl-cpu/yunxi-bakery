import { CHAT_DEFAULT_STATUS } from "../constants/chat";
import type { ChatMessage, ChatPayload, ChatStatus } from "../types/chat";
import { request } from "./http";

export type { ChatMessage, ChatPayload, ChatStatus } from "../types/chat";

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

export async function listChatMessages(): Promise<ChatMessage[]> {
  const response = await request<WrappedApiResponse<ChatPayload | ChatMessage[]> | ChatPayload | ChatMessage[]>({
    path: "/api/v1/miniapp/chat/messages"
  });
  const data = unwrapResponse(response);
  if (Array.isArray(data)) {
    return data;
  }
  return data.messages || [];
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

export async function sendChatMessage(content: string): Promise<SendChatMessageResponse> {
  const response = await request<WrappedApiResponse<SendChatMessageResponse>, { content: string }>({
    method: "POST",
    path: "/api/v1/miniapp/chat/messages",
    data: { content }
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
