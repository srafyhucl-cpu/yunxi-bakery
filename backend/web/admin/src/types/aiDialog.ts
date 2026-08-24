export interface AiDialogSession {
  id: string;
  name: string;
  userId: string;
  userDisplay: string;
  pinned: boolean;
  lastMsg: string;
  createdAt: string;
  updatedAt: string;
}

export interface AiDialogMessage {
  role: string;
  content: string;
  createdAt: string;
}

export interface AiDialogSendResult {
  reply: string;
  intent: string;
  sessionId: string;
}
