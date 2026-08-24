import { computed, ref } from "vue";
import { ElMessage } from "element-plus";

import { transfersService } from "@/services/transfers";
import type { SessionMessage, TransferListItem, TransferStatus } from "@/types/transfer";

function normalizeRole(role: string): string {
  if (role === "user") {
    return "用户";
  }
  if (role === "assistant") {
    return "AI";
  }
  if (role === "human" || role === "agent") {
    return "人工";
  }
  return role || "消息";
}

export function useTransfersPage() {
  const loading = ref(false);
  const actionLoadingId = ref("");
  const detailLoading = ref(false);
  const replySending = ref(false);
  const drawerVisible = ref(false);
  const replyDraft = ref("");
  const transfers = ref<TransferListItem[]>([]);
  const selectedTransferId = ref("");
  const sessionMessages = ref<SessionMessage[]>([]);

  const selectedTransfer = computed(() =>
    transfers.value.find((item) => item.id === selectedTransferId.value) || null,
  );

  const pendingCount = computed(
    () => transfers.value.filter((item) => item.status === "pending").length,
  );
  const acceptedCount = computed(
    () => transfers.value.filter((item) => item.status === "accepted").length,
  );

  const listRows = computed(() =>
    transfers.value.map((item) => ({
      ...item,
      shortUserId: item.userId.length > 14 ? `${item.userId.slice(0, 14)}...` : item.userId,
      statusLabel: formatStatus(item.status),
    })),
  );

  async function loadTransfers() {
    loading.value = true;
    try {
      transfers.value = await transfersService.listPendingTransfers();
      if (selectedTransferId.value) {
        const exists = transfers.value.some((item) => item.id === selectedTransferId.value);
        if (!exists) {
          closeDrawer();
        }
      }
    } finally {
      loading.value = false;
    }
  }

  async function openDetail(transfer: TransferListItem) {
    selectedTransferId.value = transfer.id;
    drawerVisible.value = true;
    await loadSessionMessages(transfer.sessionId);
  }

  function closeDrawer() {
    drawerVisible.value = false;
    selectedTransferId.value = "";
    sessionMessages.value = [];
    replyDraft.value = "";
  }

  async function loadSessionMessages(sessionId: string) {
    detailLoading.value = true;
    try {
      sessionMessages.value = await transfersService.getSessionMessages(sessionId);
    } finally {
      detailLoading.value = false;
    }
  }

  async function acceptSelectedTransfer() {
    const transfer = selectedTransfer.value;
    if (!transfer || transfer.status !== "pending") {
      return;
    }
    actionLoadingId.value = transfer.id;
    try {
      await transfersService.acceptTransfer(transfer.id);
      updateTransferStatus(transfer.id, "accepted");
      ElMessage.success("已接单");
    } finally {
      actionLoadingId.value = "";
    }
  }

  async function closeSelectedTransfer() {
    const transfer = selectedTransfer.value;
    if (!transfer) {
      return;
    }
    actionLoadingId.value = transfer.id;
    try {
      await transfersService.closeTransfer(transfer.id);
      transfers.value = transfers.value.filter((item) => item.id !== transfer.id);
      ElMessage.success("已关闭");
      closeDrawer();
    } finally {
      actionLoadingId.value = "";
    }
  }

  async function sendReply() {
    const transfer = selectedTransfer.value;
    const content = replyDraft.value.trim();
    if (!transfer || !content) {
      return;
    }
    replySending.value = true;
    try {
      await transfersService.sendHumanReply(transfer.sessionId, content);
      replyDraft.value = "";
      ElMessage.success("已发送人工回复");
      await loadSessionMessages(transfer.sessionId);
    } finally {
      replySending.value = false;
    }
  }

  function updateTransferStatus(transferId: string, status: TransferStatus) {
    transfers.value = transfers.value.map((item) =>
      item.id === transferId ? { ...item, status } : item,
    );
  }

  return {
    loading,
    actionLoadingId,
    detailLoading,
    replySending,
    drawerVisible,
    replyDraft,
    transfers,
    selectedTransfer,
    sessionMessages,
    pendingCount,
    acceptedCount,
    listRows,
    normalizeRole,
    loadTransfers,
    openDetail,
    closeDrawer,
    acceptSelectedTransfer,
    closeSelectedTransfer,
    sendReply,
  };
}

function formatStatus(status: TransferStatus): string {
  if (status === "accepted") {
    return "已接单";
  }
  if (status === "closed") {
    return "已关闭";
  }
  return "待处理";
}
