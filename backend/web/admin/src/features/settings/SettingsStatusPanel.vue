<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { settingsService } from "@/services/settings";
import type { SettingsPanel, SettingsSummary } from "@/types/settings";

const props = defineProps<{
  panel: SettingsPanel;
}>();

const loading = ref(false);
const errorMessage = ref("");
const summary = ref<SettingsSummary | null>(null);

const pageTitle = computed(() => {
  if (props.panel === "shop") {
    return "店铺配置";
  }
  if (props.panel === "channel") {
    return "渠道配置";
  }
  return "API 配置";
});

const pageIntro = computed(() => {
  if (props.panel === "shop") {
    return "先把运行路径、商品规模和主推款数量巡检出来，方便判断店铺数据是否齐备。";
  }
  if (props.panel === "channel") {
    return "只展示有赞和企微关键项是否已配置，敏感密钥不会在后台明文回显。";
  }
  return "展示管理后台和 MiMo 接入状态，密钥仅显示配置状态，不展示具体值。";
});

const configuredCount = computed(() => {
  if (!summary.value) {
    return 0;
  }
  if (props.panel === "shop") {
    return summary.value.shop.featuredProductCount;
  }
  if (props.panel === "channel") {
    const flags = [
      summary.value.channels.youzan.clientIdConfigured,
      summary.value.channels.youzan.clientSecretConfigured,
      summary.value.channels.youzan.kdtIdConfigured,
      summary.value.channels.wecom.corpIdConfigured,
      summary.value.channels.wecom.agentIdConfigured,
      summary.value.channels.wecom.secretConfigured,
      summary.value.channels.wecom.tokenConfigured,
      summary.value.channels.wecom.encodingAesKeyConfigured,
      summary.value.channels.wecom.staffIdConfigured,
      summary.value.channels.wecom.robotWebhookConfigured,
    ];
    return flags.filter(Boolean).length;
  }
  return [summary.value.api.adminTokenConfigured, summary.value.api.mimoApiKeyConfigured].filter(Boolean).length;
});

async function loadSummary() {
  loading.value = true;
  errorMessage.value = "";
  try {
    summary.value = await settingsService.getSummary();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : "配置状态加载失败，请稍后重试";
  } finally {
    loading.value = false;
  }
}

function statusType(value: boolean): "success" | "warning" {
  return value ? "success" : "warning";
}

function statusText(value: boolean): string {
  return value ? "已配置" : "未配置";
}

onMounted(loadSummary);
</script>

<template>
  <section class="settings-status">
    <div class="settings-status__summary">
      <el-card shadow="never">
        <span>当前页面</span>
        <strong>{{ pageTitle }}</strong>
      </el-card>
      <el-card shadow="never">
        <span>{{ props.panel === "shop" ? "主推款数量" : "已配置项目" }}</span>
        <strong>{{ configuredCount }}</strong>
      </el-card>
      <el-card shadow="never">
        <span>安全策略</span>
        <strong>不回显密钥</strong>
      </el-card>
    </div>

    <el-card shadow="never" v-loading="loading">
      <template #header>
        <div class="settings-status__header">
          <div>
            <strong>{{ pageTitle }}</strong>
            <p>{{ pageIntro }}</p>
          </div>
          <el-button type="primary" plain @click="loadSummary">刷新状态</el-button>
        </div>
      </template>

      <el-alert
        v-if="errorMessage"
        class="settings-status__alert"
        type="error"
        show-icon
        :closable="false"
        :title="errorMessage"
      />

      <template v-if="summary && props.panel === 'shop'">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="服务监听">{{ summary.shop.serverHost }}:{{ summary.shop.serverPort }}</el-descriptions-item>
          <el-descriptions-item label="商品总数">{{ summary.shop.productTotal }}</el-descriptions-item>
          <el-descriptions-item label="主推款数量">{{ summary.shop.featuredProductCount }}</el-descriptions-item>
          <el-descriptions-item label="数据库路径">{{ summary.shop.databasePath }}</el-descriptions-item>
          <el-descriptions-item label="向量索引路径">{{ summary.shop.embeddingPath }}</el-descriptions-item>
        </el-descriptions>
      </template>

      <template v-else-if="summary && props.panel === 'channel'">
        <div class="settings-status__cards">
          <el-card shadow="never">
            <template #header>有赞渠道</template>
            <div class="settings-status__checks">
              <span>Client ID <el-tag :type="statusType(summary.channels.youzan.clientIdConfigured)">{{ statusText(summary.channels.youzan.clientIdConfigured) }}</el-tag></span>
              <span>Client Secret <el-tag :type="statusType(summary.channels.youzan.clientSecretConfigured)">{{ statusText(summary.channels.youzan.clientSecretConfigured) }}</el-tag></span>
              <span>KDT ID <el-tag :type="statusType(summary.channels.youzan.kdtIdConfigured)">{{ statusText(summary.channels.youzan.kdtIdConfigured) }}</el-tag></span>
              <span>仿真模式 <el-tag :type="summary.channels.youzan.mockMode ? 'warning' : 'success'">{{ summary.channels.youzan.mockMode ? "开启" : "关闭" }}</el-tag></span>
            </div>
          </el-card>

          <el-card shadow="never">
            <template #header>企微渠道</template>
            <div class="settings-status__checks">
              <span>Corp ID <el-tag :type="statusType(summary.channels.wecom.corpIdConfigured)">{{ statusText(summary.channels.wecom.corpIdConfigured) }}</el-tag></span>
              <span>Agent ID <el-tag :type="statusType(summary.channels.wecom.agentIdConfigured)">{{ statusText(summary.channels.wecom.agentIdConfigured) }}</el-tag></span>
              <span>Secret <el-tag :type="statusType(summary.channels.wecom.secretConfigured)">{{ statusText(summary.channels.wecom.secretConfigured) }}</el-tag></span>
              <span>Token <el-tag :type="statusType(summary.channels.wecom.tokenConfigured)">{{ statusText(summary.channels.wecom.tokenConfigured) }}</el-tag></span>
              <span>AES Key <el-tag :type="statusType(summary.channels.wecom.encodingAesKeyConfigured)">{{ statusText(summary.channels.wecom.encodingAesKeyConfigured) }}</el-tag></span>
              <span>值班客服 <el-tag :type="statusType(summary.channels.wecom.staffIdConfigured)">{{ statusText(summary.channels.wecom.staffIdConfigured) }}</el-tag></span>
              <span>群机器人 <el-tag :type="statusType(summary.channels.wecom.robotWebhookConfigured)">{{ statusText(summary.channels.wecom.robotWebhookConfigured) }}</el-tag></span>
            </div>
          </el-card>
        </div>
      </template>

      <template v-else-if="summary">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="管理员 Token">
            <el-tag :type="statusType(summary.api.adminTokenConfigured)">{{ statusText(summary.api.adminTokenConfigured) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="MiMo API Key">
            <el-tag :type="statusType(summary.api.mimoApiKeyConfigured)">{{ statusText(summary.api.mimoApiKeyConfigured) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="对话模型">{{ summary.api.mimoChatModel }}</el-descriptions-item>
          <el-descriptions-item label="视觉模型">{{ summary.api.mimoVisionModel }}</el-descriptions-item>
          <el-descriptions-item label="语音模型">{{ summary.api.mimoAsrModel }}</el-descriptions-item>
          <el-descriptions-item label="Base URL">{{ summary.api.mimoBaseUrl }}</el-descriptions-item>
        </el-descriptions>
      </template>
    </el-card>
  </section>
</template>

<style scoped>
.settings-status {
  display: grid;
  gap: 16px;
}

.settings-status__summary,
.settings-status__cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.settings-status__summary :deep(.el-card__body) {
  display: grid;
  gap: 8px;
}

.settings-status__summary span,
.settings-status__header p {
  color: var(--yx-text-muted);
  font-size: 13px;
}

.settings-status__summary strong {
  font-size: 24px;
}

.settings-status__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.settings-status__header p {
  margin: 6px 0 0;
}

.settings-status__alert {
  margin-bottom: 16px;
}

.settings-status__checks {
  display: grid;
  gap: 12px;
}

.settings-status__checks span {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

@media (max-width: 900px) {
  .settings-status__summary,
  .settings-status__cards {
    grid-template-columns: minmax(0, 1fr);
  }

  .settings-status__header {
    flex-direction: column;
  }
}
</style>
