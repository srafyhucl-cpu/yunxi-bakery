<script setup lang="ts">
import { ElMessage } from "element-plus";
import { ref, watch } from "vue";

import {
  productAdminService,
  type ProductAdminDetail,
  type ProductAdminOptionGroup,
  type ProductAdminVariant,
} from "@/services/products";

const props = defineProps<{
  visible: boolean;
  itemId: string;
  createMode?: boolean;
}>();

const emit = defineEmits<{
  "update:visible": [value: boolean];
  saved: [];
}>();

const loading = ref(false);
const saving = ref(false);
const uploading = ref(false);
const detail = ref<ProductAdminDetail | null>(null);

const form = ref({
  title: "",
  priceFen: 0,
  stock: 0,
  isActive: true,
  desc: "",
  tags: "",
  fulfillmentMode: "auto" as "auto" | "preorder" | "direct",
});
const variants = ref<ProductAdminVariant[]>([]);
const options = ref<ProductAdminOptionGroup[]>([]);

watch(
  () => [props.visible, props.itemId, props.createMode] as const,
  ([visible, itemId, createMode]) => {
    if (!visible) {
      return;
    }
    if (createMode) {
      resetForCreate();
      return;
    }
    if (itemId) {
      void load(itemId);
    }
  },
  { immediate: true },
);

function resetForCreate() {
  detail.value = null;
  form.value = {
    title: "",
    priceFen: 0,
    stock: 0,
    isActive: true,
    desc: "",
    tags: "",
    fulfillmentMode: "auto",
  };
  variants.value = [];
  options.value = [];
}

function yuan(fen: number): string {
  return (Number(fen || 0) / 100).toFixed(2);
}

async function load(itemId: string) {
  loading.value = true;
  try {
    const data = await productAdminService.detail(itemId);
    detail.value = data;
    form.value = {
      title: data.title,
      priceFen: data.priceFen,
      stock: data.stock,
      isActive: data.isActive,
      desc: data.desc,
      tags: data.tags,
      fulfillmentMode: data.fulfillmentMode,
    };
    variants.value = data.variants.map((variant) => ({ ...variant }));
    options.value = data.options.map((group) => ({
      ...group,
      choices: group.choices.map((choice) => ({ ...choice })),
    }));
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "加载商品失败");
  } finally {
    loading.value = false;
  }
}

function closeDrawer() {
  emit("update:visible", false);
}

function addVariant() {
  variants.value.push({ property: "尺寸", name: "", priceFen: 0, stock: 0 });
}

function removeVariant(index: number) {
  variants.value.splice(index, 1);
}

function addGroup() {
  options.value.push({
    name: "",
    required: true,
    multiple: false,
    choices: [{ name: "", priceDeltaFen: 0 }],
  });
}

function removeGroup(index: number) {
  options.value.splice(index, 1);
}

function addChoice(group: ProductAdminOptionGroup) {
  group.choices.push({ name: "", priceDeltaFen: 0 });
}

function removeChoice(group: ProductAdminOptionGroup, index: number) {
  group.choices.splice(index, 1);
}

async function handleUpload(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file || !props.itemId) {
    return;
  }
  uploading.value = true;
  try {
    await productAdminService.uploadImage(props.itemId, file);
    ElMessage.success("图片已上传");
    await load(props.itemId);
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "上传失败");
  } finally {
    uploading.value = false;
  }
}

async function save() {
  if (!props.createMode && !props.itemId) {
    return;
  }
  if (!form.value.title.trim()) {
    ElMessage.warning("商品标题不能为空");
    return;
  }
  for (const variant of variants.value) {
    if (!variant.name.trim()) {
      ElMessage.warning("规格名称不能为空");
      return;
    }
  }
  for (const group of options.value) {
    if (!group.name.trim()) {
      ElMessage.warning("属性组名称不能为空");
      return;
    }
    if (!group.choices.length || group.choices.some((choice) => !choice.name.trim())) {
      ElMessage.warning(`属性组「${group.name || "未命名"}」的选项不能为空`);
      return;
    }
  }
  saving.value = true;
  try {
    const payload = {
      title: form.value.title.trim(),
      priceFen: form.value.priceFen,
      stock: form.value.stock,
      isActive: form.value.isActive,
      desc: form.value.desc,
      tags: form.value.tags,
      fulfillmentMode: form.value.fulfillmentMode,
      variants: variants.value.map((variant) => ({
        name: variant.name.trim(),
        priceFen: variant.priceFen,
        stock: variant.stock,
      })),
      options: options.value.map((group) => ({
        name: group.name.trim(),
        required: group.required,
        multiple: group.multiple,
        choices: group.choices.map((choice) => ({
          name: choice.name.trim(),
          priceDeltaFen: choice.priceDeltaFen,
        })),
      })),
    };
    if (props.createMode) {
      const created = await productAdminService.create(payload);
      ElMessage.success(`已创建商品 ${created.itemId}`);
    } else {
      await productAdminService.save(props.itemId, payload);
      ElMessage.success("已保存");
    }
    emit("saved");
    closeDrawer();
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : "保存失败");
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <el-drawer
    :model-value="visible"
    :title="createMode ? '新建商品' : detail ? `编辑商品 · ${detail.title}` : '编辑商品'"
    size="min(720px, 100%)"
    destroy-on-close
    @close="closeDrawer"
    @update:model-value="emit('update:visible', $event)"
  >
    <div v-loading="loading" class="product-edit">
      <el-form label-width="96px" label-position="left">
        <el-form-item label="商品标题">
          <el-input v-model="form.title" maxlength="60" show-word-limit />
        </el-form-item>
        <el-form-item label="列表价">
          <el-input-number v-model="form.priceFen" :min="0" :step="100" />
          <span class="product-edit__hint">分；有规格时保存后自动取最低规格价（当前 ¥{{ yuan(form.priceFen) }}）</span>
        </el-form-item>
        <el-form-item label="库存">
          <el-input-number v-model="form.stock" :min="0" />
          <span class="product-edit__hint">有规格时保存后自动取各规格之和</span>
        </el-form-item>
        <el-form-item label="履约方式">
          <el-select v-model="form.fulfillmentMode" style="width: 220px">
            <el-option label="自动（按规格/属性推导）" value="auto" />
            <el-option label="提前预订" value="preorder" />
            <el-option label="现货直购" value="direct" />
          </el-select>
          <span class="product-edit__hint">
            当前生效：{{ detail?.effectiveOrderMode === "preorder" ? "预订" : "现货" }}
          </span>
        </el-form-item>
        <el-form-item label="上下架">
          <el-switch v-model="form.isActive" active-text="在售" inactive-text="下架" />
        </el-form-item>
        <el-form-item label="标签">
          <el-input v-model="form.tags" placeholder="逗号分隔，如：在售, 6寸" />
        </el-form-item>
        <el-form-item label="商品描述">
          <el-input v-model="form.desc" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="商品图">
          <div class="product-edit__image">
            <img v-if="detail?.imageLocal" :src="`/api/v1/miniapp/products/${detail.itemId}/image?v=${detail.imageLocal}`" alt="商品图" />
            <span v-else class="product-edit__hint">尚未上传本地图</span>
            <label class="product-edit__upload">
              <input type="file" accept="image/jpeg,image/png,image/webp" :disabled="uploading" @change="handleUpload" />
              {{ uploading ? "上传中…" : "上传图片" }}
            </label>
          </div>
        </el-form-item>
      </el-form>

      <el-divider content-position="left">规格表（尺寸决定价格）</el-divider>
      <el-table :data="variants" size="small" border>
        <el-table-column label="规格名" min-width="120">
          <template #default="{ row }">
            <el-input v-model="row.name" placeholder="如 6寸" />
          </template>
        </el-table-column>
        <el-table-column label="价格（分）" width="150">
          <template #default="{ row }">
            <el-input-number v-model="row.priceFen" :min="0" :step="100" controls-position="right" />
          </template>
        </el-table-column>
        <el-table-column label="库存" width="130">
          <template #default="{ row }">
            <el-input-number v-model="row.stock" :min="0" controls-position="right" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ $index }">
            <el-button link type="danger" @click="removeVariant($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-button class="product-edit__add" plain @click="addVariant">+ 添加规格</el-button>

      <el-divider content-position="left">属性组（夹心/甜度等，选项可加价）</el-divider>
      <el-empty v-if="!options.length" description="没有属性组，商品按规格直接下单" :image-size="60" />
      <div v-for="(group, groupIndex) in options" :key="groupIndex" class="product-edit__group">
        <div class="product-edit__group-head">
          <el-input v-model="group.name" placeholder="属性名，如 夹心" style="width: 160px" />
          <el-checkbox v-model="group.required">必选</el-checkbox>
          <el-checkbox v-model="group.multiple">可多选</el-checkbox>
          <el-button link type="danger" @click="removeGroup(groupIndex)">删除属性组</el-button>
        </div>
        <div v-for="(choice, choiceIndex) in group.choices" :key="choiceIndex" class="product-edit__choice">
          <el-input v-model="choice.name" placeholder="选项名，如 芒果" style="width: 180px" />
          <el-input-number v-model="choice.priceDeltaFen" :min="0" :step="100" controls-position="right" />
          <span class="product-edit__hint">加价（分）</span>
          <el-button link type="danger" @click="removeChoice(group, choiceIndex)">删除</el-button>
        </div>
        <el-button link type="primary" @click="addChoice(group)">+ 添加选项</el-button>
      </div>
      <el-button class="product-edit__add" plain @click="addGroup">+ 添加属性组</el-button>
    </div>

    <template #footer>
      <el-button @click="closeDrawer">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-drawer>
</template>

<style scoped>
.product-edit {
  padding-bottom: 12px;
}
.product-edit__hint {
  margin-left: 10px;
  color: #909399;
  font-size: 12px;
}
.product-edit__image {
  display: flex;
  align-items: center;
  gap: 16px;
}
.product-edit__image img {
  width: 96px;
  height: 96px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid #ebeef5;
}
.product-edit__upload {
  display: inline-block;
  padding: 6px 14px;
  border: 1px dashed #c0c4cc;
  border-radius: 4px;
  color: #606266;
  cursor: pointer;
}
.product-edit__upload input {
  display: none;
}
.product-edit__add {
  margin-top: 10px;
}
.product-edit__group {
  padding: 12px;
  margin-bottom: 12px;
  background: #fafafa;
  border-radius: 6px;
}
.product-edit__group-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.product-edit__choice {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}
</style>
