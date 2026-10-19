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
  // 平台客服队列（后台工单）与微信原生客服是两套入口，文案必须能让顾客分清。
  platformHandoffButton: "平台客服转人工",
  wechatContactButton: "微信客服",
  serviceEntryHint: "平台客服转人工进门店队列；复杂定制与报价请走微信客服。",
  customizationCardTitle: "定制需求卡",
  customizationCardDesc: "填写需求生成可复制摘要；本卡片不创建订单、不扣款、不锁定档期。",
  customizationCardEntry: "定制需求卡",
  customizationCardSubmit: "生成需求卡",
  customizationCardResubmit: "重新生成需求卡",
  customizationCardReset: "重置",
  customizationCardCopy: "复制需求卡",
  customizationCardContact: "微信客服确认",
  customizationCardContactHint: "复杂定制、报价与档期请转微信人工确认后再下单。",
  customizationCardCreatedToast: "需求卡已生成",
  customizationCardCopyToast: "需求卡已复制",
  customizationCardCopyFailedToast: "复制失败，请手动长按选择文本复制",
  customizationCardNotReadyToast: "请先生成需求卡",
  customizationCardSubmittingToast: "需求卡生成中，请稍候",
  customizationCardFailed: "需求卡生成失败，请稍后重试",
  customizationCardRequiredSize: "请选择尺寸规格",
  customizationCardRequiredCustomSize: "请填写定制尺寸",
  customizationCardRequiredFilling: "请填写夹心口味",
  customizationCardRequiredGreeting: "请填写祝福语（没有请填无）",
  customizationCardRequiredAccessories: "请填写配件（没有请填无）",
  customizationCardLoginToast: "请先登录后使用定制需求卡",
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
