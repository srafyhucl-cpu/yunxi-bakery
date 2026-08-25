<template>
  <div class="invoices-page">
    <div class="invoices-page__toolbar">
      <el-button type="primary" @click="openCreate">登记发票</el-button>
      <el-select v-model="statusFilter" placeholder="状态筛选" clearable style="width: 140px" @change="load">
        <el-option label="待开具" value="applied" />
        <el-option label="已开具" value="issued" />
      </el-select>
      <el-button @click="load">刷新</el-button>
    </div>

    <el-table :data="invoices" border>
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="order_no" label="订单号" min-width="140" />
      <el-table-column prop="customer_name" label="客户名" min-width="100" />
      <el-table-column prop="company_title" label="企业抬头" min-width="140" />
      <el-table-column prop="tax_no" label="税号" min-width="130" />
      <el-table-column prop="email" label="接收邮箱" min-width="140" />
      <el-table-column label="金额(元)" width="100">
        <template #default="{ row }">
          {{ row.amount_fen == null ? "-" : (row.amount_fen / 100).toFixed(2) }}
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 'issued' ? 'success' : 'info'">
            {{ row.status === "issued" ? "已开具" : "待开具" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="issue_note" label="开票备注" min-width="120" />
      <el-table-column prop="created_at" label="登记时间" width="160" />
      <el-table-column label="操作" width="110" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.status !== 'issued'"
            size="small"
            type="success"
            @click="openMarkIssued(row)"
          >
            标记已开
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="createVisible" title="登记发票" width="480px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="订单号">
          <el-input v-model="form.orderNo" placeholder="如 mp_20260825_xxxx" />
        </el-form-item>
        <el-form-item label="客户名" required>
          <el-input v-model="form.customerName" placeholder="客户姓名" />
        </el-form-item>
        <el-form-item label="企业抬头" required>
          <el-input v-model="form.companyTitle" placeholder="公司全称" />
        </el-form-item>
        <el-form-item label="税号" required>
          <el-input v-model="form.taxNo" placeholder="统一社会信用代码" />
        </el-form-item>
        <el-form-item label="接收邮箱" required>
          <el-input v-model="form.email" placeholder="发票接收邮箱" />
        </el-form-item>
        <el-form-item label="金额(元)">
          <el-input-number v-model="amountYuan" :min="0" :precision="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="saveInvoice">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="markVisible" title="标记已开具" width="420px">
      <el-form :model="markForm" label-width="90px">
        <el-form-item label="开票备注">
          <el-input v-model="markForm.issueNote" placeholder="如：已开具电子普票" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="markVisible = false">取消</el-button>
        <el-button type="success" @click="saveMarkIssued">确认标记</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  createInvoice,
  listInvoices,
  markIssued,
  type InvoiceRecord,
} from "../../services/invoices";

const invoices = ref<InvoiceRecord[]>([]);
const statusFilter = ref("");

const createVisible = ref(false);
const form = reactive({
  orderNo: "",
  customerName: "",
  companyTitle: "",
  taxNo: "",
  email: "",
});
const amountYuan = ref<number>(0);

const markVisible = ref(false);
const markForm = reactive({ issueNote: "" });
const markingId = ref<number>(0);

async function load() {
  try {
    invoices.value = await listInvoices(statusFilter.value);
  } catch {
    ElMessage.error("加载发票列表失败");
  }
}

function openCreate() {
  Object.assign(form, {
    orderNo: "",
    customerName: "",
    companyTitle: "",
    taxNo: "",
    email: "",
  });
  amountYuan.value = 0;
  createVisible.value = true;
}

async function saveInvoice() {
  if (!form.customerName || !form.companyTitle || !form.taxNo || !form.email) {
    ElMessage.warning("请填写完整必填字段");
    return;
  }
  try {
    await createInvoice({
      ...form,
      amountFen: Math.round(amountYuan.value * 100),
    });
    ElMessage.success("发票已登记");
    createVisible.value = false;
    await load();
  } catch {
    ElMessage.error("登记失败");
  }
}

function openMarkIssued(row: InvoiceRecord) {
  markingId.value = row.id;
  markForm.issueNote = "";
  markVisible.value = true;
}

async function saveMarkIssued() {
  try {
    await markIssued(markingId.value, markForm.issueNote);
    ElMessage.success("已标记开具");
    markVisible.value = false;
    await load();
  } catch {
    ElMessage.error("标记失败");
  }
}

onMounted(load);
</script>

<style scoped>
.invoices-page {
  padding: 16px;
}

.invoices-page__toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 14px;
}
</style>
