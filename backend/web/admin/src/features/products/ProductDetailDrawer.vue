<script setup lang="ts">
import type { ProductListItem } from "@/types/product";

defineProps<{
  visible: boolean;
  product: ProductListItem | null;
  togglingId: number;
}>();

const emit = defineEmits<{
  "update:visible": [value: boolean];
  toggle: [product: ProductListItem];
}>();

function closeDrawer() {
  emit("update:visible", false);
}

function triggerToggle(product: ProductListItem) {
  emit("toggle", product);
}

function formatDateTime(value: string): string {
  if (!value) {
    return "未记录";
  }
  return value.replace("T", " ").slice(0, 19);
}
</script>

<template>
  <el-drawer
    :model-value="visible"
    title="商品详情"
    size="min(560px, 100%)"
    destroy-on-close
    @close="closeDrawer"
    @update:model-value="emit('update:visible', $event)"
  >
    <template v-if="product">
      <div class="product-detail-drawer">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="商品标题">
            {{ product.title }}
          </el-descriptions-item>
          <el-descriptions-item label="商品状态">
            {{ product.isActive ? "在售" : "下架" }}
          </el-descriptions-item>
          <el-descriptions-item label="商品编码">
            {{ product.itemNo || "未记录" }}
          </el-descriptions-item>
          <el-descriptions-item label="有赞商品 ID">
            {{ product.youzanItemId || "未记录" }}
          </el-descriptions-item>
          <el-descriptions-item label="同步来源">
            {{ product.lastSyncSource || "未记录" }}
          </el-descriptions-item>
          <el-descriptions-item label="同步引用">
            {{ product.lastSyncRef || "未记录" }}
          </el-descriptions-item>
          <el-descriptions-item label="AI 可读状态">
            {{ product.vectorSyncStatus || "未记录" }}
          </el-descriptions-item>
          <el-descriptions-item label="关键词">
            {{ product.keywords || "未填写" }}
          </el-descriptions-item>
          <el-descriptions-item label="优先级">
            {{ product.priority }}
          </el-descriptions-item>
          <el-descriptions-item label="最近更新时间">
            {{ formatDateTime(product.updatedAt) }}
          </el-descriptions-item>
        </el-descriptions>

        <el-card shadow="never">
          <template #header>商品知识内容</template>
          <div class="product-detail-drawer__content">
            {{ product.content || "暂无内容" }}
          </div>
        </el-card>

        <div class="product-detail-drawer__actions">
          <el-button
            :loading="togglingId === product.id"
            :type="product.isActive ? 'warning' : 'success'"
            @click="triggerToggle(product)"
          >
            {{ product.isActive ? "下架该商品" : "上架该商品" }}
          </el-button>
        </div>
      </div>
    </template>
  </el-drawer>
</template>

<style scoped>
.product-detail-drawer {
  display: grid;
  gap: 16px;
}

.product-detail-drawer__content {
  white-space: pre-wrap;
  line-height: 1.7;
  color: var(--yx-text);
}

.product-detail-drawer__actions {
  display: flex;
  justify-content: flex-end;
}
</style>
