import http from "./http";

import type {
  AiDialogMessage,
  AiDialogSendResult,
  AiDialogSession,
} from "@/types/aiDialog";

interface ListSessionsResponse {
  code: number;
  data: Array<{
    id: string;
    name: string;
    user_id: string;
    user_display: string;
    pinned: boolean;
    last_msg: string;
    created_at: string;
    updated_at: string;
  }>;
}

interface ChatHistoryResponse {
  code: number;
  data: Array<{ role: string; content: string; created_at: string }>;
}

interface SendMessageResponse {
  code: number;
  reply: string;
  intent: string;
  session_id: string;
}

export const aiDialogService = {
  async listSessions(): Promise<AiDialogSession[]> {
    const response = await http.get<ListSessionsResponse>("/ai-dialog/sessions");
    return response.data.data.map((item) => ({
      id: item.id,
      name: item.name,
      userId: item.user_id,
      userDisplay: item.user_display,
      pinned: item.pinned,
      lastMsg: item.last_msg,
      createdAt: item.created_at,
      updatedAt: item.updated_at,
    }));
  },

  async getMessagesBySessionId(sessionId: string): Promise<AiDialogMessage[]> {
    const response = await http.get<ChatHistoryResponse>(`/sessions/${sessionId}/messages`);
    return response.data.data.map((item) => ({
      role: item.role,
      content: item.content,
      createdAt: item.created_at,
    }));
  },

  async sendMessage(content: string, userId: string): Promise<AiDialogSendResult> {
    const response = await http.post<SendMessageResponse>("/ai-dialog", { content, user_id: userId });
    return {
      reply: response.data.reply,
      intent: response.data.intent,
      sessionId: response.data.session_id,
    };
  },

  async saveSession(sessionId: string, name: string, userDisplay = ""): Promise<void> {
    await http.post("/ai-dialog/save", { session_id: sessionId, name, user_display: userDisplay });
  },

  async pinSession(sessionId: string): Promise<boolean> {
    const response = await http.post<{ code: number; pinned: boolean }>(`/ai-dialog/session/${sessionId}/pin`);
    return response.data.pinned;
  },

  async deleteSession(sessionId: string): Promise<void> {
    await http.delete(`/ai-dialog/session/${sessionId}`);
  },
};
