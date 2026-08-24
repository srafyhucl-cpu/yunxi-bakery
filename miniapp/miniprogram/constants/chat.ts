import type { ChatMessage, ChatStatus } from "../types/chat";

export const CHAT_POLLING_CONFIG = {
  humanReplyIntervalMs: 5000,
  humanReplyMaxTimes: 6,
} as const;

export const CHAT_DEFAULT_STATUS: ChatStatus = {
  sessionId: "",
  status: "active",
  label: "AI 客服接待中",
  description: "可继续咨询蛋糕、配送和定制问题。",
  isHumanHandoff: false,
} as const;

export const CHAT_WELCOME_MESSAGE: ChatMessage = {
  id: "welcome",
  role: "assistant",
  content: "您好，我是芸熙烘焙客服。想咨询蛋糕、配送或定制都可以直接问我。",
  createdAt: "",
} as const;

export const CHAT_COPY = {
  handoffActiveButton: "已转接",
  handoffButton: "转人工",
  handoffPolling: "正在等待人工回复...",
  handoffWaiting: "人工客服回复后会显示在这里",
  refreshButton: "刷新",
  loading: "正在连接客服...",
  inputPlaceholder: "输入想咨询的问题",
  sendButton: "发送",
  emptyInputToast: "请输入内容",
  loadFailed: "消息加载失败，仍可直接发送咨询",
  loadFailedToast: "消息加载失败",
  sendFailed: "发送失败，请稍后重试或复制客服微信咨询",
  sendFailedToast: "发送失败",
  transferSuccessToast: "已通知人工客服",
  transferFailed: "转人工失败，请稍后重试或继续留言",
  transferFailedToast: "转人工失败",
  refreshFailed: "刷新失败，请稍后重试",
  refreshFailedToast: "刷新失败",
  pollingFailed: "人工消息刷新失败，可手动点刷新",
} as const;
