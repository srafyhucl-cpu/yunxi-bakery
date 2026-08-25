import {
  CHAT_COPY,
  CHAT_DEFAULT_STATUS,
  CHAT_POLLING_CONFIG,
  CHAT_WELCOME_MESSAGE,
} from "../../constants/chat";
import {
  ChatMessage,
  ChatStatus,
  getChatPayload,
  requestHumanTransfer,
  sendChatMessage,
} from "../../services/chat";
import { getErrorMessage } from "../../services/http";
import { formatMsgTime as formatMsgTimeUtil } from "../../utils/time-format";
import { ROUTES } from "../../constants/routes";
import { getMiniappSession } from "../../services/auth";
import { getMiniappLayoutMetrics } from "../../utils/layout";
import { syncCustomTabBar } from "../../utils/tab-bar";
import { buildMiniappSessionView, isMiniappLoggedIn } from "../../utils/session";

/** 将后端可能返回的各种非标准 role 归一化为 user | assistant */
function normalizeRole(role: string): "user" | "assistant" {
  if (role === "user") return "user";
  return "assistant"; // bot / ai / system / assistant 全部归一
}

/** 将 ISO 时间字符串格式化为 HH:MM */
function formatMsgTime(iso: string): string {
  // iOS 兼容：归一化空格分隔时间串后再 new Date（见 utils/time-format.ts）
  return formatMsgTimeUtil(iso);
}

/** 归一化并注入 timeText 到消息列表 */
function normalizeMessages(raw: ChatMessage[]): (ChatMessage & { timeText: string })[] {
  return raw.map((m) => ({
    ...m,
    role: normalizeRole(m.role),
    timeText: formatMsgTime(m.createdAt)
  }));
}

Page({
  data: {
    inputValue: "",
    canSendMessage: false,
    messages: [CHAT_WELCOME_MESSAGE],
    chatStatus: CHAT_DEFAULT_STATUS,
    loading: false,
    sending: false,
    transferring: false,
    refreshing: false,
    pollingHumanReply: false,
    errorMessage: "",
    sessionView: buildMiniappSessionView(getMiniappSession()),
    loginStateText: "客服需要登录后可用",
    // 直接从本地 session 初始化，不等 API，避免输入栏延迟出现
    canUseChat: isMiniappLoggedIn(getMiniappSession()),
    copy: CHAT_COPY,
    layoutStyle: getMiniappLayoutMetrics().pageShellStyle,
    lastMessageId: "",
    isAssistantTyping: false
  },
  onShow() {
    syncCustomTabBar(ROUTES.chat);
    void this.loadMessages();
  },
  onHide() {
    this.stopHumanReplyPolling();
  },
  onUnload() {
    this.stopHumanReplyPolling();
  },
  async loadMessages() {
    const session = getMiniappSession();
    const loggedIn = isMiniappLoggedIn(session);
    // 同步更新登录状态和 session 视图（本地操作，立即生效）
    this.setData({
      canUseChat: loggedIn,
      sessionView: buildMiniappSessionView(session),
      loginStateText: loggedIn ? "已连接在线客服" : "请先登录后使用客服"
    });
    if (!loggedIn) {
      this.setData({
        messages: normalizeMessages([CHAT_WELCOME_MESSAGE]),
        lastMessageId: "",
        isAssistantTyping: false
      });
      this.stopHumanReplyPolling();
      return;
    }
    this.setData({ loading: true });
    try {
      const payload = await getChatPayload();
      const rawMessages = payload.messages.length ? payload.messages : [CHAT_WELCOME_MESSAGE];
      const chatMessages = normalizeMessages(rawMessages);
      const lastMsg = chatMessages[chatMessages.length - 1];
      const initId = lastMsg ? `msg-${lastMsg.id}` : "";
      this.setData({
        messages: chatMessages,
        chatStatus: payload.status,
        errorMessage: ""
      });
      wx.nextTick(() => { this.setData({ lastMessageId: initId }); });
      this.syncHumanReplyPolling(payload.status);

    } catch (error) {
      this.setData({ errorMessage: CHAT_COPY.loadFailed });
      wx.showToast({ title: CHAT_COPY.loadFailedToast, icon: "none" });
    } finally {
      this.setData({ loading: false });
    }
  },
  updateInput(event: WechatMiniprogram.Input) {
    const inputValue = event.detail.value;
    this.setData({
      inputValue,
      canSendMessage: inputValue.trim().length > 0
    });
  },
  async sendMessage() {
    if (this.data.sending) return;
    const content = this.data.inputValue.trim();
    if (!content) {
      // \u8f93\u5165\u4e3a\u7a7a\uff1a\u8f7b\u6491\u63d0\u793a\u800c\u4e0d\u662f\u65e0\u53cd\u5e94
      wx.showToast({ title: CHAT_COPY.emptyInputToast, icon: "none" });
      return;
    }
    await this.sendTextContent(content);
  },

  async sendQuickQuestion(event: WechatMiniprogram.TouchEvent) {
    if (this.data.sending) {
      return;
    }
    const content = String(event.currentTarget.dataset.content || "").trim();
    await this.sendTextContent(content);
  },
  async sendTextContent(content: string) {
    if (!content) {
      wx.showToast({
        title: CHAT_COPY.emptyInputToast,
        icon: "none"
      });
      return;
    }
    if (!this.data.canUseChat) {
      wx.showToast({ title: "请先登录后使用客服", icon: "none" });
      return;
    }
    const optimisticMessage = {
      id: `local-${Date.now()}`,
      role: "user" as const,
      content,
      createdAt: new Date().toISOString(),
      timeText: formatMsgTime(new Date().toISOString())
    };

    const baseMessages = this.data.messages.filter((message) => message.id !== CHAT_WELCOME_MESSAGE.id);

    // Stage user message & switch assistant to typing state, scroll to bottom
    this.setData({
      inputValue: "",
      canSendMessage: false,
      sending: true,
      errorMessage: "",
      messages: [...baseMessages, optimisticMessage],
      isAssistantTyping: true
    });
    // Defer scroll anchor update so DOM has rendered the new node first
    wx.nextTick(() => { this.setData({ lastMessageId: "typing" }); });

    try {
      const result = await sendChatMessage(content);
      let rawMessages = result.messages.length ? result.messages : [];

      // 如果 messages 数组里没有 assistant 消息，但 result.reply 存在，
      // 则说明后端把 AI 回复放在 reply 字段而非 messages 数组，手动补充一条
      const hasAssistant = rawMessages.some((m) => m.role === "assistant" || (m.role !== "user"));
      if (!hasAssistant && result.reply) {
        rawMessages = [
          ...rawMessages,
          {
            id: `reply-${Date.now()}`,
            role: "assistant" as const,
            content: result.reply,
            createdAt: new Date().toISOString()
          }
        ];
      }

      if (!rawMessages.length) rawMessages = [CHAT_WELCOME_MESSAGE];
      const chatMessages = normalizeMessages(rawMessages);
      const lastMsg = chatMessages[chatMessages.length - 1];
      const nextId = lastMsg ? `msg-${lastMsg.id}` : "";
      this.setData({
        messages: chatMessages,
        chatStatus: result.status || this.data.chatStatus,
        isAssistantTyping: false
      });
      // Defer scroll anchor update so DOM renders the final message first
      wx.nextTick(() => { this.setData({ lastMessageId: nextId }); });
      this.syncHumanReplyPolling(result.status || this.data.chatStatus);

    } catch (error) {
      const errorMessage = getErrorMessage(error, CHAT_COPY.sendFailed);
      this.setData({
        inputValue: content,
        canSendMessage: true,
        errorMessage,
        messages: baseMessages.length ? baseMessages : normalizeMessages([CHAT_WELCOME_MESSAGE]),
        isAssistantTyping: false,
        lastMessageId: ""
      });
      wx.showToast({
        title: errorMessage,
        icon: "none"
      });
    } finally {
      this.setData({ sending: false });
    }
  },
  async requestHumanService() {
    if (!this.data.canUseChat) {
      wx.showToast({ title: "请先登录后转人工", icon: "none" });
      return;
    }
    if (this.data.chatStatus.isHumanHandoff || this.data.transferring) {
      return;
    }
    this.setData({
      transferring: true,
      errorMessage: "",
      isAssistantTyping: true,
      lastMessageId: "typing"
    });
    try {
      const payload = await requestHumanTransfer();
      const chatMessages = normalizeMessages(payload.messages.length ? payload.messages : [CHAT_WELCOME_MESSAGE]);
      const lastMsg = chatMessages[chatMessages.length - 1];
      const nextId = lastMsg ? `msg-${lastMsg.id}` : "";
      this.setData({
        messages: chatMessages,
        chatStatus: payload.status,
        isAssistantTyping: false
      });
      wx.nextTick(() => { this.setData({ lastMessageId: nextId }); });
      this.syncHumanReplyPolling(payload.status);
      wx.showToast({
        title: CHAT_COPY.transferSuccessToast,
        icon: "none"
      });
    } catch {
      this.setData({
        errorMessage: CHAT_COPY.transferFailed,
        isAssistantTyping: false,
        lastMessageId: ""
      });
      wx.showToast({
        title: CHAT_COPY.transferFailedToast,
        icon: "none"
      });
    } finally {
      this.setData({ transferring: false });
    }
  },
  async refreshMessages() {
    if (this.data.refreshing) {
      return;
    }
    if (!this.data.canUseChat) {
      wx.showToast({ title: "请先登录后刷新客服", icon: "none" });
      return;
    }
    this.setData({
      refreshing: true,
      errorMessage: ""
    });
    try {
      const payload = await getChatPayload();
      const chatMessages = normalizeMessages(payload.messages.length ? payload.messages : [CHAT_WELCOME_MESSAGE]);
      const lastMsg = chatMessages[chatMessages.length - 1];
      const nextId = lastMsg ? `msg-${lastMsg.id}` : "";
      this.setData({ messages: chatMessages, chatStatus: payload.status });
      wx.nextTick(() => { this.setData({ lastMessageId: nextId }); });
      this.syncHumanReplyPolling(payload.status);
    } catch {
      this.setData({
        errorMessage: CHAT_COPY.refreshFailed
      });
      wx.showToast({
        title: CHAT_COPY.refreshFailedToast,
        icon: "none"
      });
    } finally {
      this.setData({ refreshing: false });
    }
  },
  goProfile() {
    wx.switchTab({ url: ROUTES.profile });
  },
  syncHumanReplyPolling(status: ChatStatus) {
    if (status.isHumanHandoff) {
      this.startHumanReplyPolling();
      return;
    }
    this.stopHumanReplyPolling();
  },
  startHumanReplyPolling() {
    if (this.data.pollingHumanReply) {
      return;
    }
    this.setData({ pollingHumanReply: true });
    this.pollHumanReply(0);
  },
  stopHumanReplyPolling() {
    if ((this as any).humanReplyPollTimer) {
      clearTimeout((this as any).humanReplyPollTimer);
      (this as any).humanReplyPollTimer = 0;
    }
    if (this.data && this.data.pollingHumanReply) {
      this.setData({ pollingHumanReply: false });
    }
  },
  pollHumanReply(count: number) {
    if (count >= CHAT_POLLING_CONFIG.humanReplyMaxTimes || !this.data.chatStatus.isHumanHandoff) {
      this.stopHumanReplyPolling();
      return;
    }
    (this as any).humanReplyPollTimer = setTimeout(async () => {
      try {
        const payload = await getChatPayload();
        const chatMessages = normalizeMessages(payload.messages.length ? payload.messages : [CHAT_WELCOME_MESSAGE]);
        const lastMsg = chatMessages[chatMessages.length - 1];
        const nextId = lastMsg ? `msg-${lastMsg.id}` : "";
        this.setData({ messages: chatMessages, chatStatus: payload.status });
        wx.nextTick(() => { this.setData({ lastMessageId: nextId }); });
        if (!payload.status.isHumanHandoff) {
          this.stopHumanReplyPolling();
          return;
        }
      } catch {
        this.setData({
          errorMessage: CHAT_COPY.pollingFailed
        });
      }
      this.pollHumanReply(count + 1);
    }, CHAT_POLLING_CONFIG.humanReplyIntervalMs);
  }
});
