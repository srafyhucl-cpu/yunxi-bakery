export type TransferStatus = "pending" | "accepted" | "closed";

export interface TransferListItem {
  id: string;
  sessionId: string;
  userId: string;
  reason: string;
  conversationSummary: string;
  createdAt: string;
  status: TransferStatus;
}

export interface SessionMessage {
  role: string;
  content: string;
  createdAt: string;
}
