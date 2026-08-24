<script setup lang="ts">
import type { ObservabilityDetailField } from "@/types/observability";

const props = withDefaults(
  defineProps<{
    visible: boolean;
    loading: boolean;
    title: string;
    subtitle: string;
    summaryLines: string[];
    detailFields: ObservabilityDetailField[];
    errorMessage?: string;
    showTrackBtn?: boolean;
    entityKey?: string;
    entityType?: string;
  }>(),
  {
    showTrackBtn: false,
    entityKey: "",
    entityType: "",
  }
);

const emit = defineEmits<{
  (event: "update:visible", value: boolean): void;
  (event: "track-history", entityKey: string, entityType: string): void;
}>();
</script>

<template>
  <el-drawer
    :model-value="props.visible"
    size="520px"
    destroy-on-close
    @close="emit('update:visible', false)"
  >
    <template #header>
      <div class="observability-detail__header">
        <strong>{{ props.title }}</strong>
        <span v-if="props.subtitle">{{ props.subtitle }}</span>
      </div>
    </template>

    <div v-loading="props.loading" class="observability-detail">
      <el-alert
        v-if="props.errorMessage"
        class="observability-detail__alert"
        type="error"
        :closable="false"
        :title="props.errorMessage"
      />

      <!-- 快速追踪变更历史操作区 -->
      <section v-if="props.showTrackBtn && props.entityKey" class="observability-detail__track">
        <el-button
          type="primary"
          style="width: 100%; height: 38px; border-radius: 8px;"
          @click="emit('track-history', props.entityKey, props.entityType)"
        >
          追踪该对象的变更历史（回写流水）
        </el-button>
      </section>

      <section class="observability-detail__section">
        <h4>字段详情</h4>
        <div class="observability-detail__fields">
          <div
            v-for="field in props.detailFields"
            :key="field.label"
            class="observability-detail__field"
            :class="{ 'is-highlighted': field.highlight }"
          >
            <span class="observability-detail__label">
              {{ field.label }}
              <el-tag v-if="field.highlight" type="danger" size="small" effect="plain" style="margin-left: 6px; padding: 0 4px; height: 18px;">引发变动</el-tag>
            </span>
            <pre class="observability-detail__value">{{ field.value }}</pre>
          </div>
        </div>
      </section>
    </div>
  </el-drawer>
</template>

<style scoped>
.observability-detail {
  display: grid;
  gap: 16px;
}

.observability-detail__header {
  display: grid;
  gap: 6px;
}

.observability-detail__header span {
  color: var(--yx-text-muted);
  font-size: 13px;
}

.observability-detail__alert {
  margin-bottom: 4px;
}

.observability-detail__track {
  margin-bottom: 4px;
}

.observability-detail__section {
  display: grid;
  gap: 10px;
}

.observability-detail__section h4 {
  margin: 0;
  font-size: 14px;
}

.observability-detail__summary {
  margin: 0;
  padding-left: 18px;
  color: var(--yx-text-muted);
  font-size: 13px;
}

.observability-detail__fields {
  display: grid;
  gap: 12px;
}

.observability-detail__field {
  display: grid;
  gap: 6px;
  padding: 10px 14px;
  border: 1px solid var(--yx-border);
  border-radius: 8px;
  background: #faf7f2;
}

.observability-detail__field.is-highlighted {
  border-color: var(--el-color-danger-light-5);
  background: var(--el-color-danger-light-9);
}

.observability-detail__label {
  color: var(--yx-text-muted);
  font-size: 12px;
  display: flex;
  align-items: center;
}

.observability-detail__field.is-highlighted .observability-detail__label {
  color: var(--el-color-danger);
  font-weight: 600;
}

.observability-detail__value {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.5;
}

.observability-detail__field.is-highlighted .observability-detail__value {
  color: var(--el-color-danger);
}
</style>
