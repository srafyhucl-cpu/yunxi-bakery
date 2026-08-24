<script setup lang="ts">
/* =================================================================
 *  AI 对话页面 — 企业微信风格重构
 *  基于 prototype.html 样式系统，全面优化 UI/UX
 * ================================================================= */

import { ref, onMounted, onUnmounted, nextTick } from "vue";
import { parseMessageSegments } from "@/utils/umpParser";
import { INTENT_LABELS } from "@/utils/constants";
import { fmtTime } from "@/utils/date";
import { useAiDialogPage } from "./useAiDialogPage";

const {
  sessions, messages, currentSessionId, currentDisplay,
  draftInput, lastIntent, loadingSessions, loadingMessages,
  sending, messageViewport, hasSession, headerTitle,
  showRolePicker, selectedRole, customRole, pickerValid, PRESET_ROLES,
  ctxVisible, ctxX, ctxY, ctxSession,
  mobileChatActive,
  openSession, onNewChat, selectPreset, onCustomInput,
  cancelRolePicker, confirmRolePicker,
  sendMessage: doSend, showCtxMenu, lpStart, lpEnd,
  ctxPinSession, ctxDeleteSession, mobileBack,
} = useAiDialogPage();

import type { AiDialogSession, AiDialogMessage } from "@/types/aiDialog";

/* ---- 表情列表 ---- */
const EMOJI_LIST = [
  "😀","😃","😄","😁","😆","😅","🤣","😂",
  "🙂","😊","😇","🥰","😍","🤩","😘","😗",
  "😚","😋","😛","😜","🤪","😝","🤑","🤗",
  "🤭","🤫","🤔","🤐","🤨","😐","😑","😶",
  "😏","😒","🙄","😬","😮","🤯","😴","😪",
  "🌸","🌺","🌻","🌹","💐","🎂","🍰","🧁",
  "🍞","🥖","🥐","🥨","🍪","🍩","🍫","💝",
  "👍","👎","👏","🙌","🤝","💪","❤️","🔥",
  "⭐","✨","💯","✅","❌","🎉","🎊","🎈",
  "🐱","🐶","🐰","🦊","🐼","🐨","🐣","🦋",
  "☕","🍵","🥛","🧋","🍺","🍷","🥂","🍾",
  "🌞","🌙","⭐","☁️","🌈","⛈","❄️","💧",
];

const ROLE_ICONS: Record<string, string> = {
  "难缠的老太太": "👵",
  "正常的顾客": "😊",
  "价格敏感型": "💰",
  "催单狂人": "⏰",
  "售后维权": "😤",
  "初次购买": "🆕",
};

/* ---- 会话列表头像 ---- */
function sessionLabel(s: AiDialogSession): string {
  return s.name || s.userDisplay || s.userId;
}

function sessionAvatarChar(s: AiDialogSession): string {
  const label = sessionLabel(s);
  return label ? label[0].toUpperCase() : "?";
}

const SESSION_COLORS = [
  "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
  "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)",
  "linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)",
  "linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)",
  "linear-gradient(135deg, #fa709a 0%, #fee140 100%)",
  "linear-gradient(135deg, #30cfd0 0%, #330867 100%)",
];

function sessionAvatarColor(s: AiDialogSession): string {
  const label = sessionLabel(s);
  let h = 0;
  for (let i = 0; i < label.length; i++) h = (h * 31 + label.charCodeAt(i)) >>> 0;
  return SESSION_COLORS[h % SESSION_COLORS.length];
}

/* ---- 日期分组 ---- */
function dateLabel(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso.replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const MS_DAY = 86_400_000;
  if (diff < MS_DAY && d.getDate() === now.getDate()) return "今天";
  if (diff < MS_DAY * 2) return "昨天";
  if (diff < MS_DAY * 7) {
    const weekDay = ["日","一","二","三","四","五","六"];
    return "周" + weekDay[d.getDay()];
  }
  return (d.getMonth() + 1) + "月" + d.getDate() + "日";
}

function groupedMessages(): { date: string; items: AiDialogMessage[] }[] {
  const groups: { date: string; items: AiDialogMessage[] }[] = [];
  for (const msg of messages.value) {
    const key = dateLabel(msg.createdAt);
    const last = groups[groups.length - 1];
    if (last && last.date === key) {
      last.items.push(msg);
    } else {
      groups.push({ date: key, items: [msg] });
    }
  }
  return groups;
}

/* ---- 表情面板 ---- */
const showEmoji = ref(false);
const composerTextarea = ref<HTMLTextAreaElement | null>(null);

function toggleEmojiPanel() {
  showEmoji.value = !showEmoji.value;
  if (showEmoji.value) {
    composerTextarea.value?.focus();
  }
}

function insertEmoji(emoji: string) {
  const el = composerTextarea.value;
  if (!el) return;
  const start = el.selectionStart;
  const end = el.selectionEnd;
  draftInput.value = draftInput.value.substring(0, start) + emoji + draftInput.value.substring(end);
  showEmoji.value = false;
  nextTick(() => {
    el.focus();
    const pos = start + emoji.length;
    el.setSelectionRange(pos, pos);
  });
}

function onWindowClick(e: MouseEvent) {
  const target = e.target as HTMLElement;
  if (showEmoji.value && !target.closest(".emoji-panel") && !target.closest(".composer-tool-btn")) {
    showEmoji.value = false;
  }
}

function onDraftInput() {
  const el = composerTextarea.value;
  if (el) {
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
  }
}

/* ---- 回到底部按钮 ---- */
const isScrolledUp = ref(false);

function onMsgScroll() {
  const vp = messageViewport.value;
  if (!vp) return;
  isScrolledUp.value = vp.scrollHeight - vp.scrollTop - vp.clientHeight > 80;
}

function scrollToBottomManual() {
  const vp = messageViewport.value;
  if (vp) vp.scrollTo({ top: vp.scrollHeight, behavior: "smooth" });
}

/* 发送消息包装，发送后自动滚动到底 */
async function sendMessage() {
  await doSend();
  nextTick(() => {
    scrollToBottomManual();
    isScrolledUp.value = false;
  });
}

onMounted(() => {
  document.addEventListener("click", onWindowClick);
  const vp = messageViewport.value;
  if (vp) vp.addEventListener("scroll", onMsgScroll, { passive: true });
});

onUnmounted(() => {
  document.removeEventListener("click", onWindowClick);
  const vp = messageViewport.value;
  if (vp) vp.removeEventListener("scroll", onMsgScroll);
});
</script>

<template>
  <section class="ctp" :class="{ 'ctp--chat': mobileChatActive }">

    <!-- ===== 左侧会话列表 ===== -->
    <aside class="ctp-sb">
      <div class="ctp-sb__hd">
        <span class="ctp-sb__title">AI 对话</span>
        <button class="new-chat-btn" @click="onNewChat">＋ 新建</button>
      </div>
      <div v-loading="loadingSessions" class="ctp-sb__list">
        <div v-if="!loadingSessions && sessions.length === 0" class="session-empty">
          <span class="session-empty__icon">💬</span>
          <span class="session-empty__text">暂无对话</span>
        </div>
        <button
          v-for="s in sessions"
          :key="s.id"
          type="button"
          class="session-item"
          :class="{
            'session-item--active': s.id === currentSessionId,
            'session-item--pinned': s.pinned,
          }"
          @click="openSession(s)"
          @contextmenu.prevent="showCtxMenu($event, s)"
          @touchstart.passive="lpStart($event, s)"
          @touchend.passive="lpEnd()"
          @touchmove.passive="lpEnd()"
        >
          <div class="session-avatar" :style="{ background: sessionAvatarColor(s) }">
            {{ sessionAvatarChar(s) }}
          </div>
          <div class="session-info">
            <div class="session-top">
              <span class="session-name">{{ sessionLabel(s) }}</span>
              <span class="session-time">{{ fmtTime(s.updatedAt || s.createdAt) }}</span>
            </div>
            <div class="session-preview">{{ s.lastMsg || "\u200b" }}</div>
          </div>
        </button>
      </div>
    </aside>

    <!-- ===== 右侧聊天区 ===== -->
    <div class="ctp-main">

      <!-- 空状态 -->
      <div v-if="!hasSession && !messages.length" class="ctp-empty">
        <div class="empty-state">
          <div class="empty-icon">💬</div>
          <div class="empty-text">
            <h2>AI 对话测试</h2>
            <p>点击「新建」选择角色，模拟顾客与 AI 客服对话</p>
          </div>
          <button class="empty-action-btn" @click="onNewChat">选择角色开始</button>
        </div>
      </div>

      <template v-else>
        <!-- 顶栏 -->
        <header class="ctp-hd">
          <button class="ctp-back" @click="mobileBack">←</button>
          <div class="ctp-hd__avatar">{{ headerTitle.charAt(0) }}</div>
          <div class="ctp-hd__text">
            <h3 class="ctp-hd__name">{{ headerTitle }}</h3>
            <span v-if="lastIntent" class="ctp-hd__badge">
              {{ INTENT_LABELS[lastIntent] || lastIntent }}
            </span>
          </div>
          <div class="ctp-hd__spacer" />
        </header>

        <!-- 消息流 -->
        <div ref="messageViewport" v-loading="loadingMessages" class="ctp-msgs">

          <template v-for="(group, gi) in groupedMessages()" :key="'g' + gi">
            <!-- 日期分隔线 -->
            <div v-if="group.date" class="date-sep">
              <div class="date-sep__line" />
              <span class="date-sep__text">{{ group.date }}</span>
              <div class="date-sep__line" />
            </div>

            <!-- 消息气泡 -->
            <div
              v-for="(msg, mi) in group.items"
              :key="gi + '-' + mi"
              class="ct-msg"
              :class="msg.role === 'user' ? 'ct-msg--user' : 'ct-msg--ai'"
            >
              <div class="ct-msg__avatar">
                <span v-if="msg.role === 'user'" class="avatar avatar--user">你</span>
                <span v-else class="avatar avatar--ai">芸</span>
              </div>
              <div class="ct-msg__body">
                <div class="ct-msg__bubble">
                  <template v-for="(seg, si) in parseMessageSegments(msg.content)" :key="si">
                    <span v-if="seg.type === 'text'" class="ct-msg__text">{{ seg.value }}</span>
                    <a
                      v-else-if="seg.type === 'card'"
                      :href="seg.url"
                      target="_blank"
                      rel="noopener"
                      class="ump-card"
                    >
                      <img
                        v-if="seg.src"
                        :src="seg.src"
                        :alt="seg.title"
                        class="ump-card__img"
                      />
                      <div class="ump-card__info">
                        <div class="ump-card__title">{{ seg.title }}</div>
                        <div class="ump-card__price">¥{{ seg.price }}</div>
                      </div>
                    </a>
                  </template>
                </div>
                <div v-if="msg.createdAt" class="ct-msg__time">{{ fmtTime(msg.createdAt) }}</div>
              </div>
            </div>
          </template>

          <!-- AI 正在输入 -->
          <div v-if="sending" class="ct-msg ct-msg--ai ct-msg--typing">
            <div class="ct-msg__avatar"><span class="avatar avatar--ai">芸</span></div>
            <div class="ct-msg__body">
              <div class="ct-msg__bubble">
                <div class="typing-indicator">
                  <span class="typing-dot" />
                  <span class="typing-dot" />
                  <span class="typing-dot" />
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 回到底部按钮 -->
        <button
          class="scroll-bottom-btn"
          :class="{ 'scroll-bottom-btn--show': isScrolledUp && messages.length > 0 }"
          title="回到底部"
          @click="scrollToBottomManual"
        >
          ↓
        </button>

        <!-- 输入区域 -->
        <div class="ctp-composer">
          <div class="composer-toolbar">
            <button class="composer-tool-btn" title="表情" @click="toggleEmojiPanel">
              😊
            </button>
          </div>
          <div class="composer-input-wrap">
            <!-- 表情面板 -->
            <div class="emoji-panel" :class="{ 'emoji-panel--show': showEmoji }">
              <div class="emoji-grid">
                <button
                  v-for="(emoji, ei) in EMOJI_LIST"
                  :key="ei"
                  class="emoji-item"
                  @click="insertEmoji(emoji)"
                >{{ emoji }}</button>
              </div>
            </div>
            <textarea
              ref="composerTextarea"
              v-model="draftInput"
              class="composer-textarea"
              placeholder=""
              rows="1"
              @keydown.enter.exact.prevent="sendMessage"
              @input="onDraftInput"
            />
          </div>
          <button
            class="send-btn"
            :disabled="!draftInput.trim() || sending"
            @click="sendMessage"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </div>
      </template>
    </div>

    <!-- ===== 角色选择弹窗 ===== -->
    <teleport to="body">
      <div
        v-if="showRolePicker"
        class="modal-overlay"
        @click.self="cancelRolePicker"
        @keydown.escape="cancelRolePicker"
      >
        <div class="modal-dialog">
          <div class="modal-header">
            <h2>选择用户角色</h2>
            <p>模拟不同类型顾客发起测试对话，验证 AI 客服表现</p>
          </div>

          <div class="role-grid">
            <button
              v-for="role in PRESET_ROLES"
              :key="role"
              class="role-card"
              :class="{ 'role-card--sel': selectedRole === role }"
              @click="selectPreset(role)"
            >
              <span class="role-card__icon">{{ ROLE_ICONS[role] || "👤" }}</span>
              <span class="role-card__name">{{ role }}</span>
            </button>
          </div>

          <div class="custom-divider">或自定义角色</div>
          <input
            v-model="customRole"
            type="text"
            class="custom-input"
            placeholder="输入自定义角色名称…"
            @input="onCustomInput(customRole)"
          />

          <div class="modal-footer">
            <button class="btn-cancel" @click="cancelRolePicker">退出</button>
            <button class="btn-confirm" :disabled="!pickerValid" @click="confirmRolePicker">
              开始对话
            </button>
          </div>
        </div>
      </div>
    </teleport>

    <!-- ===== 右键 / 长按菜单 ===== -->
    <teleport to="body">
      <div
        v-if="ctxVisible"
        class="ctx-menu"
        :style="{ left: ctxX + 'px', top: ctxY + 'px' }"
        @click.stop
      >
        <button class="ctx-item" @click="ctxPinSession">
          {{ ctxSession?.pinned ? "取消置顶" : "置顶对话" }}
        </button>
        <button class="ctx-item ctx-item--danger" @click="ctxDeleteSession">删除对话</button>
      </div>
    </teleport>

  </section>
</template>

<style scoped>
/* =================================================================
 *   企业微信风格 AI 对话页面 — 样式系统
 *   由 prototype.html 提炼，适配 Vue scoped 架构
 * ================================================================= */

/* ── 容器 ── */
.ctp {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background: #f0f2f5;
  position: fixed;
  top: 0;
  left: 0;
}

/* ========== 左侧会话列表 ========== */
.ctp-sb {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: #f0f2f5;
  border-right: none;
}

.ctp-sb__hd {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  background: #f0f2f5;
  border-bottom: none;
  flex-shrink: 0;
}

.ctp-sb__title {
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
}

.new-chat-btn {
  padding: 8px 16px;
  background: linear-gradient(135deg, #07c160 0%, #06ad56 100%);
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 2px 8px rgba(7, 193, 96, 0.25);
}
.new-chat-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(7, 193, 96, 0.35);
}

.ctp-sb__list {
  flex: 1;
  overflow-y: auto;
  padding: 12px 8px;
}

.ctp-sb__list::-webkit-scrollbar { width: 6px; }
.ctp-sb__list::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.15);
  border-radius: 3px;
}

.session-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  gap: 12px;
  color: #9ca3af;
}
.session-empty__icon { font-size: 40px; }
.session-empty__text { font-size: 13px; }

/* 会话项 */
.session-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 14px 12px;
  margin-bottom: 4px;
  border-radius: 10px;
  border: none;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s ease;
  user-select: none;
}
.session-item:hover {
  background: #e4e7ec;
  transform: translateX(2px);
}
.session-item--active {
  background: #dce8df;
}

.session-avatar {
  width: 46px; height: 46px;
  border-radius: 4px;
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 17px; font-weight: 600; color: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.session-info { flex: 1; min-width: 0; }
.session-top {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px; margin-bottom: 4px;
}
.session-name {
  font-size: 15px; font-weight: 500; color: #1f2937;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.session-time { font-size: 12px; color: #9ca3af; flex-shrink: 0; }
.session-preview {
  font-size: 13px; color: #9ca3af;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

/* ========== 右侧聊天区 ========== */
.ctp-main {
  display: flex; flex-direction: column; height: 100%;
  overflow: hidden; background: #f0f2f5; position: relative;
}

.ctp-empty { flex: 1; display: flex; align-items: center; justify-content: center; }

.empty-state {
  display: flex; flex-direction: column; align-items: center;
  gap: 20px; padding: 40px;
}
.empty-icon {
  width: 160px; height: 160px;
  background: linear-gradient(135deg, rgba(7, 193, 96, 0.08) 0%, rgba(7, 193, 96, 0.03) 100%);
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 72px;
  animation: float 3s ease-in-out infinite;
}
@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}
.empty-text h2 { font-size: 22px; font-weight: 600; color: #1f2937; margin: 0 0 8px; }
.empty-text p { font-size: 14px; color: #9ca3af; margin: 0; }
.empty-action-btn {
  padding: 12px 32px;
  background: linear-gradient(135deg, #07c160 0%, #06ad56 100%);
  color: #fff; border: none; border-radius: 10px;
  font-size: 15px; font-weight: 600; cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 4px 16px rgba(7, 193, 96, 0.3);
  margin-top: 12px;
}
.empty-action-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(7, 193, 96, 0.4);
}

/* 顶栏 */
.ctp-hd {
  display: flex; align-items: center;
  height: 64px; padding: 0 24px;
  background: #f5f7fa; border-bottom: none;
  flex-shrink: 0; gap: 12px;
}
.ctp-back {
  display: none;
  width: 34px; height: 34px;
  border: none; background: #f7f8fa;
  font-size: 20px; color: #1f2937; cursor: pointer;
  border-radius: 10px; flex-shrink: 0;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  transition: all 0.2s ease;
}
.ctp-back:hover { background: #e8f5ec; color: #07c160; transform: translateX(-2px); }
.ctp-hd__avatar {
  width: 38px; height: 38px; border-radius: 4px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-weight: 600; font-size: 15px; flex-shrink: 0;
}
.ctp-hd__text { display: flex; flex-direction: column; gap: 2px; }
.ctp-hd__name { font-size: 16px; font-weight: 600; color: #1f2937; margin: 0; }
.ctp-hd__badge {
  display: inline-flex; align-items: center;
  padding: 4px 10px;
  background: rgba(7, 193, 96, 0.08); color: #07c160;
  border-radius: 12px; font-size: 12px; font-weight: 500;
  width: fit-content;
}
.ctp-hd__spacer { width: 40px; flex-shrink: 0; }

/* 消息流 */
.ctp-msgs {
  flex: 1; overflow-y: auto;
  padding: 24px 32px;
  display: flex; flex-direction: column; gap: 20px;
}
.ctp-msgs::-webkit-scrollbar { width: 6px; }
.ctp-msgs::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.15); border-radius: 3px;
}

/* 日期分隔线 */
.date-sep { display: flex; align-items: center; justify-content: center; margin: 16px 0; }
.date-sep__line {
  flex: 1; height: 1px;
  background: linear-gradient(to right, transparent, #e5e6eb, transparent);
}
.date-sep__text {
  padding: 6px 16px; background: #fff;
  color: #9ca3af; font-size: 12px; border-radius: 12px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06); margin: 0 16px;
}

/* 消息气泡 */
.ct-msg { display: flex; gap: 12px; align-items: flex-start; animation: messageIn 0.3s ease-out; }
@keyframes messageIn {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}
.ct-msg--user { flex-direction: row-reverse; }
.ct-msg--user .ct-msg__body { align-items: flex-end; }

.ct-msg__avatar { flex-shrink: 0; }
.avatar {
  display: flex; align-items: center; justify-content: center;
  width: 40px; height: 40px; border-radius: 4px;
  font-size: 14px; font-weight: 600; color: #fff;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
}
.avatar--user { background: linear-gradient(135deg, #576b95 0%, #4a5a7a 100%); }
.avatar--ai   { background: linear-gradient(135deg, #07c160 0%, #06ad56 100%); }

.ct-msg__body { display: flex; flex-direction: column; gap: 6px; max-width: 65%; }
.ct-msg__bubble {
  position: relative; padding: 12px 16px;
  border-radius: 12px; font-size: 14px; line-height: 1.65;
  word-break: break-word;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  transition: box-shadow 0.2s ease;
}
.ct-msg__bubble:hover { box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1); }
.ct-msg--ai .ct-msg__bubble {
  background: #fff; color: #1f2937; border-top-left-radius: 4px;
}
.ct-msg--user .ct-msg__bubble {
  background: linear-gradient(135deg, #95ec69 0%, #89df5d 100%);
  color: #1a1a1a; border-top-right-radius: 4px;
}
.ct-msg__text { white-space: pre-wrap; }
.ct-msg__time { font-size: 11px; color: #9ca3af; padding: 0 4px; }

/* 打字指示器 */
.typing-indicator { display: inline-flex; gap: 5px; padding: 14px 18px; }
.typing-dot {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: #07c160; animation: typingBounce 1.4s infinite ease-in-out;
}
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes typingBounce {
  0%, 80%, 100% { transform: translateY(0); opacity: 0.4; }
  40%           { transform: translateY(-8px); opacity: 1; }
}

/* 商品卡片 */
.ump-card {
  display: flex; align-items: center; gap: 12px; margin-top: 10px;
  padding: 12px; background: #fafbfc; border: 1px solid #e5e6eb;
  border-radius: 10px; text-decoration: none; color: inherit;
  transition: all 0.2s ease; cursor: pointer; max-width: 260px;
}
.ump-card:hover {
  border-color: #07c160; background: #fff;
  box-shadow: 0 4px 12px rgba(7, 193, 96, 0.12);
  transform: translateY(-2px);
}
.ump-card__img { width: 60px; height: 60px; object-fit: cover; border-radius: 8px; flex-shrink: 0; }
.ump-card__info { flex: 1; display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.ump-card__title {
  font-size: 13px; font-weight: 600; color: #1f2937;
  overflow: hidden; text-overflow: ellipsis;
  display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical;
}
.ump-card__price { font-size: 15px; font-weight: 700; color: #ec6f5e; }

/* 回到底部按钮 */
.scroll-bottom-btn {
  position: absolute; bottom: 100px; right: 32px;
  width: 44px; height: 44px; border-radius: 50%;
  background: #fff; border: 1px solid #e5e6eb;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  cursor: pointer; font-size: 20px; color: #667085; z-index: 2;
  opacity: 0; transform: translateY(10px); pointer-events: none;
  transition: all 0.3s ease;
}
.scroll-bottom-btn--show {
  opacity: 1; transform: translateY(0); pointer-events: auto;
}
.scroll-bottom-btn:hover {
  background: #07c160; color: #fff;
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(7, 193, 96, 0.35);
}

/* ========== 输入区域 ========== */
.ctp-composer {
  display: flex; align-items: flex-end; gap: 10px;
  padding: 12px 20px 16px; background: #f5f7fa;
  border-top: none;
  flex-shrink: 0;
}
.composer-toolbar { display: flex; align-items: center; padding-bottom: 6px; }
.composer-tool-btn {
  width: 36px; height: 36px; border: none; background: transparent;
  color: #8e929a; font-size: 20px; border-radius: 8px; cursor: pointer;
  transition: all 0.2s ease;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.composer-tool-btn:hover { background: #f0f2f5; color: #07c160; }
.composer-input-wrap { flex: 1; position: relative; }

.composer-textarea {
  width: 100%; padding: 10px 16px;
  border: 1.5px solid #e5e6eb; border-radius: 10px;
  font-size: 14px; font-family: inherit;
  resize: none; outline: none;
  transition: all 0.25s ease;
  background: #fafbfc; line-height: 1.55;
  min-height: 44px; max-height: 120px; color: #1f2937;
}
.composer-textarea:focus {
  border-color: #07c160; background: #fff;
  box-shadow: 0 0 0 3px rgba(7, 193, 96, 0.08);
}
.composer-textarea::placeholder { color: #9ca3af; font-size: 13px; }

.send-btn {
  width: 44px; height: 44px; padding: 0;
  background: linear-gradient(135deg, #07c160 0%, #06ad56 100%);
  color: #fff; border: none; border-radius: 10px; cursor: pointer;
  transition: all 0.25s ease;
  box-shadow: 0 3px 10px rgba(7, 193, 96, 0.2);
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
}
.send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 5px 16px rgba(7, 193, 96, 0.35);
  background: linear-gradient(135deg, #08d46a 0%, #07c160 100%);
}
.send-btn:active:not(:disabled) { transform: scale(0.94); transition: all 0.1s ease; }
.send-btn:disabled { background: #d0d5dd; box-shadow: none; cursor: not-allowed; }

/* 表情面板 */
.emoji-panel {
  position: absolute; left: 0; bottom: calc(100% + 8px);
  width: 290px; background: #fff; border: 1px solid #e5e6eb;
  border-radius: 12px; padding: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  display: none; z-index: 10;
}
.emoji-panel--show { display: block; animation: slideUpSmall 0.2s ease; }
@keyframes slideUpSmall {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
.emoji-grid { display: grid; grid-template-columns: repeat(8, 1fr); gap: 6px; }
.emoji-item {
  width: 30px; height: 30px; border: none; background: transparent;
  font-size: 20px; cursor: pointer; border-radius: 6px;
  transition: all 0.15s ease;
  display: flex; align-items: center; justify-content: center; padding: 0;
}
.emoji-item:hover { background: #f0f2f5; transform: scale(1.2); }
.emoji-item:active { transform: scale(0.9); }

/* ========== 角色选择弹窗 ========== */
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.45); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  z-index: 9999; animation: fadeIn 0.3s ease;
}
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
.modal-dialog {
  background: #fff; border-radius: 20px; padding: 32px;
  width: 90%; max-width: 520px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
  animation: slideUp 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}
@keyframes slideUp {
  from { opacity: 0; transform: translateY(30px) scale(0.95); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}
.modal-header { text-align: center; margin-bottom: 28px; }
.modal-header h2 { font-size: 22px; font-weight: 700; color: #1f2937; margin: 0 0 8px; }
.modal-header p { font-size: 14px; color: #9ca3af; margin: 0; }
.role-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 24px; }
.role-card {
  padding: 16px 12px; border: 2px solid #e5e6eb; border-radius: 12px;
  text-align: center; cursor: pointer; transition: all 0.3s ease;
  background: #fafbfc;
  display: flex; flex-direction: column; align-items: center; gap: 8px;
}
.role-card:hover {
  border-color: #07c160; background: #fff;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(7, 193, 96, 0.15);
}
.role-card--sel {
  border-color: #07c160; background: rgba(7, 193, 96, 0.05);
  box-shadow: 0 4px 12px rgba(7, 193, 96, 0.2);
}
.role-card__icon { font-size: 28px; }
.role-card__name { font-size: 14px; font-weight: 600; color: #1f2937; }
.custom-divider {
  display: flex; align-items: center; gap: 12px;
  color: #9ca3af; font-size: 13px; margin: 24px 0 16px;
}
.custom-divider::before, .custom-divider::after {
  content: ""; flex: 1; height: 1px; background: #e5e6eb;
}
.custom-input {
  width: 100%; padding: 14px 18px; border: 2px solid #e5e6eb;
  border-radius: 10px; font-size: 14px; outline: none;
  transition: all 0.3s ease; background: #fafbfc; box-sizing: border-box;
}
.custom-input:focus {
  border-color: #07c160; background: #fff;
  box-shadow: 0 0 0 4px rgba(7, 193, 96, 0.1);
}
.modal-footer { display: flex; gap: 12px; margin-top: 28px; }
.btn-cancel {
  flex: 1; padding: 14px; border: 2px solid #e5e6eb; border-radius: 10px;
  background: #fff; color: #667085; font-size: 15px; font-weight: 600;
  cursor: pointer; transition: all 0.3s ease;
}
.btn-cancel:hover { background: #f5f7fa; border-color: #d0d5dd; }
.btn-confirm {
  flex: 1; padding: 14px; border: none; border-radius: 10px;
  background: linear-gradient(135deg, #07c160 0%, #06ad56 100%);
  color: #fff; font-size: 15px; font-weight: 600; cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 4px 12px rgba(7, 193, 96, 0.3);
}
.btn-confirm:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(7, 193, 96, 0.4);
}
.btn-confirm:disabled { opacity: 0.5; cursor: not-allowed; }

/* ========== 右键菜单 ========== */
.ctx-menu {
  position: fixed; z-index: 9998; background: #fff;
  border-radius: 8px; box-shadow: 0 4px 24px rgba(0, 0, 0, 0.16);
  overflow: hidden; min-width: 120px;
}
.ctx-item {
  display: block; width: 100%; padding: 12px 18px; border: none;
  background: none; text-align: left; font-size: 14px; cursor: pointer; color: #333;
}
.ctx-item:hover { background: #f5f5f5; }
.ctx-item--danger { color: #e74c3c; }

/* ========== 响应式：移动端全屏导航 ========== */
@media (max-width: 900px) {
  .ctp {
    display: block; position: relative; overflow: hidden;
    height: 100%;
  }
  .ctp-sb {
    position: absolute; inset: 0; z-index: 1;
    border-right: none;
    transition: transform 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  }
  .ctp--chat .ctp-sb { transform: translateX(-100%); }
  .ctp-main {
    position: absolute; inset: 0; z-index: 2;
    transition: transform 0.35s cubic-bezier(0.4, 0, 0.2, 1);
    transform: translateX(100%);
  }
  .ctp--chat .ctp-main { transform: translateX(0); }
  .ctp-back { display: flex; align-items: center; justify-content: center; }
  .ctp-msgs { padding: 16px; }
  .ct-msg__body { max-width: 85%; }
  .ctp-composer { padding: 12px 16px; }
  .modal-dialog { width: 94%; padding: 24px; }
  .session-item:active { background: #e8f5ec; transform: scale(0.98); }
}
</style>
