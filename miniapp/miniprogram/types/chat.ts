export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
}

export interface ChatStatus {
  sessionId: string;
  status: "active" | "transfer_pending" | "human_service" | "closed";
  label: string;
  description: string;
  isHumanHandoff: boolean;
}

export interface ChatPayload {
  messages: ChatMessage[];
  status: ChatStatus;
}
