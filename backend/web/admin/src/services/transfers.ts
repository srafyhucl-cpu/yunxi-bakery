import http from "./http";

import type { SessionMessage, TransferListItem } from "@/types/transfer";

interface PendingTransfersResponse {
  code: number;
  data: Array<{
    id: string;
    session_id: string;
    user_id: string;
    reason: string;
    conversation_summary: string;
    created_at: string;
  }>;
}

interface SessionMessagesResponse {
  code: number;
  data: Array<{
    role: string;
    content: string;
    created_at: string;
  }>;
}

interface ActionResponse {
  code: number;
  message?: string;
}

async function listPendingTransfers(): Promise<TransferListItem[]> {
  const response = await http.get<PendingTransfersResponse>("/transfers/pending");
  return response.data.data.map((item) => ({
    id: item.id,
    sessionId: item.session_id,
    userId: item.user_id,
    reason: item.reason || "未记录原因",
    conversationSummary: item.conversation_summary || "",
    createdAt: item.created_at,
    status: "pending",
  }));
}

async function getSessionMessages(sessionId: string): Promise<SessionMessage[]> {
  const response = await http.get<SessionMessagesResponse>(`/sessions/${sessionId}/messages`);
  return response.data.data.map((item) => ({
    role: item.role,
    content: item.content,
    createdAt: item.created_at,
  }));
}

async function acceptTransfer(transferId: string): Promise<void> {
  const response = await http.post<ActionResponse>(`/transfers/${transferId}/accept`);
  if (response.data.code !== 0) {
    throw new Error(response.data.message || "接单失败");
  }
}

async function closeTransfer(transferId: string): Promise<void> {
  const response = await http.post<ActionResponse>(`/transfers/${transferId}/close`);
  if (response.data.code !== 0) {
    throw new Error(response.data.message || "关闭失败");
  }
}

async function sendHumanReply(sessionId: string, content: string): Promise<void> {
  const response = await http.post<ActionResponse>(`/sessions/${sessionId}/reply`, null, {
    params: { content },
  });
  if (response.data.code !== 0) {
    throw new Error(response.data.message || "发送失败");
  }
}

export const transfersService = {
  listPendingTransfers,
  getSessionMessages,
  acceptTransfer,
  closeTransfer,
  sendHumanReply,
};
