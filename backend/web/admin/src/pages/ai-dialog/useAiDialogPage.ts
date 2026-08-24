import { computed, nextTick, onMounted, onUnmounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { aiDialogService } from "@/services/aiDialog";
import type { AiDialogMessage, AiDialogSession } from "@/types/aiDialog";

export const PRESET_ROLES = ["难缠的老太太", "正常的顾客", "价格敏感型", "催单狂人", "售后维权", "初次购买"];

function nowTimeStr(): string {
  return new Date().toTimeString().slice(0, 5);
}

export function useAiDialogPage() {
  // ── 会话列表 ──
  const sessions = ref<AiDialogSession[]>([]);
  const loadingSessions = ref(false);

  // ── 当前对话 ──
  const messages = ref<AiDialogMessage[]>([]);
  const currentSessionId = ref("");
  const currentUserId = ref("");
  const currentDisplay = ref("");
  const loadingMessages = ref(false);
  const sending = ref(false);
  const draftInput = ref("");
  const lastIntent = ref("");
  const messageViewport = ref<HTMLElement | null>(null);

  // ── 自动命名 ──
  const pendingName = ref("");
  const pendingDisplay = ref("");

  // ── 角色选择弹窗 ──
  const showRolePicker = ref(false);
  const selectedRole = ref("");
  const customRole = ref("");
  const pickerValid = computed(() => !!(selectedRole.value || customRole.value.trim()));

  // ── 右键/长按菜单 ──
  const ctxVisible = ref(false);
  const ctxX = ref(0);
  const ctxY = ref(0);
  const ctxSession = ref<AiDialogSession | null>(null);
  let longPressTimer: ReturnType<typeof setTimeout> | null = null;

  // ── 移动端：是否显示聊天面板（覆盖侧栏）──
  const mobileChatActive = ref(false);

  const hasSession = computed(() => currentSessionId.value.length > 0);
  const headerTitle = computed(() => currentDisplay.value || "新对话");

  async function scrollToBottom() {
    await nextTick();
    if (messageViewport.value) {
      messageViewport.value.scrollTop = messageViewport.value.scrollHeight;
    }
  }

  // ── 加载对话列表 ──
  async function loadSessions() {
    loadingSessions.value = true;
    try {
      sessions.value = await aiDialogService.listSessions();
    } finally {
      loadingSessions.value = false;
    }
  }

  // ── 打开历史对话 ──
  async function openSession(session: AiDialogSession) {
    currentSessionId.value = session.id;
    currentUserId.value = session.userId;
    currentDisplay.value = session.name || session.userDisplay || session.userId;
    pendingName.value = "";
    pendingDisplay.value = "";
    lastIntent.value = "";
    hideCtxMenu();
    mobileChatActive.value = true;

    loadingMessages.value = true;
    try {
      messages.value = await aiDialogService.getMessagesBySessionId(session.id);
      await scrollToBottom();
    } finally {
      loadingMessages.value = false;
    }
  }

  // ── 角色选择弹窗 ──
  function onNewChat() {
    selectedRole.value = "";
    customRole.value = "";
    showRolePicker.value = true;
  }

  function selectPreset(name: string) {
    selectedRole.value = name;
    customRole.value = "";
  }

  function onCustomInput(val: string) {
    customRole.value = val;
    selectedRole.value = "";
  }

  function cancelRolePicker() {
    showRolePicker.value = false;
  }

  function confirmRolePicker() {
    const name = selectedRole.value || customRole.value.trim();
    if (!name) return;
    showRolePicker.value = false;
    currentUserId.value = "ai_" + encodeURIComponent(name) + "_" + Date.now();
    currentDisplay.value = name;
    currentSessionId.value = "";
    pendingName.value = name + " · " + nowTimeStr();
    pendingDisplay.value = name;
    draftInput.value = "";
    lastIntent.value = "";
    messages.value = [{
      role: "assistant",
      content: "👋 你好，我是在线客服，有什么可以帮你的~",
      createdAt: new Date().toISOString(),
    }];
    mobileChatActive.value = true;
  }

  // ── 发送消息 ──
  async function sendMessage() {
    const content = draftInput.value.trim();
    if (!content || sending.value) return;

    messages.value.push({ role: "user", content, createdAt: new Date().toISOString() });
    draftInput.value = "";
    sending.value = true;
    await scrollToBottom();

    try {
      const result = await aiDialogService.sendMessage(content, currentUserId.value);
      lastIntent.value = result.intent;
      const isFirst = !currentSessionId.value;
      currentSessionId.value = result.sessionId;

      if (isFirst && pendingName.value && result.sessionId) {
        try {
          await aiDialogService.saveSession(result.sessionId, pendingName.value, pendingDisplay.value);
          pendingName.value = "";
          pendingDisplay.value = "";
        } catch {}
        await loadSessions();
      }

      messages.value.push({ role: "assistant", content: result.reply, createdAt: new Date().toISOString() });
      await scrollToBottom();

      if (!isFirst) {
        await loadSessions();
      }
    } catch {
      ElMessage.error("发送失败，请重试");
      messages.value.pop();
    } finally {
      sending.value = false;
    }
  }

  // ── 右键/长按菜单 ──
  function showCtxMenu(event: MouseEvent, session: AiDialogSession) {
    event.preventDefault();
    ctxX.value = Math.min(event.clientX, window.innerWidth - 150);
    ctxY.value = Math.min(event.clientY, window.innerHeight - 100);
    ctxSession.value = session;
    ctxVisible.value = true;
  }

  function hideCtxMenu() {
    ctxVisible.value = false;
    ctxSession.value = null;
  }

  function lpStart(event: TouchEvent, session: AiDialogSession) {
    lpEnd();
    const touch = event.touches[0];
    longPressTimer = setTimeout(() => {
      showCtxMenu(
        { clientX: touch.clientX, clientY: touch.clientY, preventDefault: () => {} } as MouseEvent,
        session,
      );
    }, 500);
  }

  function lpEnd() {
    if (longPressTimer !== null) {
      clearTimeout(longPressTimer);
      longPressTimer = null;
    }
  }

  async function ctxPinSession() {
    if (!ctxSession.value) return;
    const target = ctxSession.value;
    hideCtxMenu();
    try {
      await aiDialogService.pinSession(target.id);
      await loadSessions();
    } catch {
      ElMessage.error("操作失败");
    }
  }

  async function ctxDeleteSession() {
    if (!ctxSession.value) return;
    const target = ctxSession.value;
    hideCtxMenu();
    try {
      await ElMessageBox.confirm("删除后该对话记录将关闭，无法恢复。", "确认删除", {
        confirmButtonText: "删除",
        cancelButtonText: "取消",
        type: "warning",
      });
    } catch {
      return;
    }
    try {
      await aiDialogService.deleteSession(target.id);
      if (target.id === currentSessionId.value) {
        currentSessionId.value = "";
        currentDisplay.value = "";
        messages.value = [];
        mobileChatActive.value = false;
      }
      await loadSessions();
    } catch {
      ElMessage.error("删除失败");
    }
  }

  function mobileBack() {
    mobileChatActive.value = false;
  }

  function onDocumentClick() {
    if (ctxVisible.value) hideCtxMenu();
  }

  onMounted(async () => {
    await loadSessions();
    document.addEventListener("click", onDocumentClick);
  });

  onUnmounted(() => {
    document.removeEventListener("click", onDocumentClick);
    lpEnd();
  });

  return {
    sessions, messages, currentSessionId, currentDisplay,
    draftInput, lastIntent, loadingSessions, loadingMessages,
    sending, messageViewport, hasSession, headerTitle,
    showRolePicker, selectedRole, customRole, pickerValid, PRESET_ROLES,
    ctxVisible, ctxX, ctxY, ctxSession,
    mobileChatActive,
    openSession, onNewChat, selectPreset, onCustomInput,
    cancelRolePicker, confirmRolePicker,
    sendMessage, scrollToBottom, showCtxMenu, hideCtxMenu, lpStart, lpEnd,
    ctxPinSession, ctxDeleteSession, mobileBack, loadSessions,
  };
}
