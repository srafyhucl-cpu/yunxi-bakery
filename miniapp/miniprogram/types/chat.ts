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

/**
 * 定制蛋糕需求卡（只读产物）。
 * 字段与后端 `POST /api/v1/miniapp/chat/customization-card` 返回结构保持一致。
 */
export interface CustomizationCard {
  size: string;
  filling: string;
  sweetness: string;
  greeting: string;
  accessories: string;
  expectTime: string;
  remark: string;
  summary: string;
}

/**
 * 需求卡提交参数。
 * 必填项：size / filling / greeting / accessories；expectTime、remark 可为空。
 * 使用 type 别名以便直接作为请求体传给统一 request 封装。
 */
export type CustomizationCardRequest = {
  size: string;
  filling: string;
  sweetness: string;
  greeting: string;
  accessories: string;
  expectTime: string;
  remark: string;
};
