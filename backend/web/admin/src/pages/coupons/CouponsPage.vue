<template>
  <div class="coupons-page">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="券模板" name="templates">
        <el-button type="primary" @click="openCreate">新建模板</el-button>
        <el-table :data="templates" border>
          <el-table-column prop="name" label="名称" />
          <el-table-column prop="coupon_type" label="类型" />
          <el-table-column prop="value_fen" label="面额(分)" />
          <el-table-column prop="status" label="状态" />
          <el-table-column label="操作">
            <template #default="{ row }">
              <el-button size="small" @click="openEdit(row)">编辑</el-button>
              <el-button size="small" @click="toggleStatus(row)">{{ row.status === 'active' ? '停用' : '启用' }}</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-dialog v-model="dialogVisible" :title="editing ? '编辑模板' : '新建模板'">
          <el-form :model="form" label-width="90px">
            <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
            <el-form-item label="类型">
              <el-select v-model="form.couponType">
                <el-option label="满减券" value="FULL_REDUCTION" />
                <el-option label="无门槛" value="NO_THRESHOLD" />
                <el-option label="折扣券" value="DISCOUNT" />
              </el-select>
            </el-form-item>
            <el-form-item label="门槛(分)"><el-input-number v-model="form.thresholdFen" :min="0" /></el-form-item>
            <el-form-item label="面额(分)"><el-input-number v-model="form.valueFen" :min="0" /></el-form-item>
            <el-form-item label="折扣万分比"><el-input-number v-model="form.discountBp" :min="0" :max="9999" /></el-form-item>
            <el-form-item label="上限(分)"><el-input-number v-model="form.capFen" :min="0" /></el-form-item>
            <el-form-item label="生效日"><el-input v-model="form.validFrom" placeholder="2026-08-01" /></el-form-item>
            <el-form-item label="失效日"><el-input v-model="form.validUntil" placeholder="2026-12-31" /></el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="dialogVisible = false">取消</el-button>
            <el-button type="primary" @click="saveTemplate">保存</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>
      <el-tab-pane label="核销/发券记录" name="records">
        <el-form inline>
          <el-form-item label="手机号"><el-input v-model="queryMobile" placeholder="13800000000" /></el-form-item>
          <el-button type="primary" @click="loadRecords">查询</el-button>
        </el-form>
        <el-table :data="records" border>
          <el-table-column prop="coupon_id" label="券ID" />
          <el-table-column prop="mobile" label="手机号" />
          <el-table-column prop="status" label="状态" />
          <el-table-column prop="order_no" label="订单号" />
          <el-table-column prop="deducted_fen" label="抵扣(分)" />
          <el-table-column prop="source" label="来源" />
          <el-table-column prop="occurred_at" label="时间" />
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="local 发券" name="grant">
        <el-form inline>
          <el-form-item label="模板">
            <el-select v-model="grantTemplateId">
              <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="手机号"><el-input v-model="grantMobile" placeholder="13800000000" /></el-form-item>
          <el-button type="primary" @click="doGrant">发券</el-button>
        </el-form>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  createTemplate,
  grantCoupon,
  listRecords,
  listTemplates,
  setTemplateStatus,
  updateTemplate,
  type CouponRecord,
  type CouponTemplate,
  type CouponTemplatePayload,
} from "@/services/coupons";

const activeTab = ref("templates");
const templates = ref<CouponTemplate[]>([]);
const records = ref<CouponRecord[]>([]);
const dialogVisible = ref(false);
const editing = ref<string | null>(null);
const queryMobile = ref("");
const grantTemplateId = ref("");
const grantMobile = ref("");
const form = ref<CouponTemplatePayload>({
  name: "",
  couponType: "FULL_REDUCTION",
  thresholdFen: 0,
  valueFen: 0,
  discountBp: 0,
  capFen: 0,
  validFrom: "",
  validUntil: "",
});

async function loadTemplates() {
  const data = await listTemplates();
  templates.value = data.templates ?? [];
}

async function loadRecords() {
  const data = await listRecords({ mobile: queryMobile.value });
  records.value = data.records ?? [];
}

function openCreate() {
  editing.value = null;
  form.value = {
    name: "",
    couponType: "FULL_REDUCTION",
    thresholdFen: 0,
    valueFen: 0,
    discountBp: 0,
    capFen: 0,
    validFrom: "",
    validUntil: "",
  };
  dialogVisible.value = true;
}

function openEdit(row: CouponTemplate) {
  editing.value = row.id;
  form.value = {
    name: row.name,
    couponType: row.coupon_type,
    thresholdFen: row.threshold_fen,
    valueFen: row.value_fen,
    discountBp: row.discount_bp,
    capFen: row.cap_fen,
    validFrom: row.valid_from,
    validUntil: row.valid_until,
  };
  dialogVisible.value = true;
}

async function saveTemplate() {
  if (editing.value) {
    await updateTemplate(editing.value, form.value);
  } else {
    await createTemplate(form.value);
  }
  dialogVisible.value = false;
  await loadTemplates();
  ElMessage.success("保存成功");
}

async function toggleStatus(row: CouponTemplate) {
  await setTemplateStatus(row.id, row.status === "active" ? "disabled" : "active");
  await loadTemplates();
}

async function doGrant() {
  if (!grantTemplateId.value || !grantMobile.value) {
    ElMessage.warning("请选择模板并填写手机号");
    return;
  }
  const result = await grantCoupon(grantTemplateId.value, grantMobile.value);
  ElMessage.success(`发券成功 ${result.couponCode}`);
  grantMobile.value = "";
}

onMounted(() => {
  loadTemplates();
});
</script>
