<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { ChatLineRound, CopyDocument, Plus, Refresh, Search } from "@element-plus/icons-vue";

import { customerGroupsService } from "@/services/customerGroups";
import type {
  CampaignSummary,
  CustomerGroup,
  CustomerGroupDraft,
  GroupCampaign,
  GroupCampaignDraft,
  GroupRegistration,
} from "@/types/customerGroup";

const loading = ref(false);
const summaryLoading = ref(false);
const keyword = ref("");
const groups = ref<CustomerGroup[]>([]);
const campaigns = ref<GroupCampaign[]>([]);
const selectedGroupId = ref("");
const selectedCampaignId = ref("");
const selectedSummary = ref<CampaignSummary | null>(null);
const groupFormVisible = ref(false);
const campaignFormVisible = ref(false);
const formSubmitting = ref(false);
const actionLoadingKey = ref("");
const groupDraft = ref<CustomerGroupDraft>(createEmptyGroupDraft());
const campaignDraft = ref<GroupCampaignDraft>(createEmptyCampaignDraft());

const selectedGroup = computed(() => groups.value.find((group) => group.id === selectedGroupId.value) ?? null);
const activeCampaigns = computed(() => campaigns.value.filter((campaign) => campaign.status === "active"));
const selectedCampaign = computed(
  () => campaigns.value.find((campaign) => campaign.id === selectedCampaignId.value) ?? null,
);
const pendingCount = computed(() => selectedSummary.value?.statusCounts.pending ?? 0);
const confirmedCount = computed(() => selectedSummary.value?.statusCounts.confirmed ?? 0);
const cancelledCount = computed(() => selectedSummary.value?.statusCounts.cancelled ?? 0);

function createEmptyGroupDraft(): CustomerGroupDraft {
  return {
    chatId: "",
    opengid: "",
    name: "",
    ownerUserid: "",
    source: "",
  };
}

function createEmptyCampaignDraft(): GroupCampaignDraft {
  return {
    groupId: selectedGroupId.value,
    title: "",
    startsAt: "",
    endsAt: "",
    summaryNote: "",
  };
}

function formatTime(value: string): string {
  return value ? value.replace("T", " ").slice(0, 19) : "未记录";
}

function fulfillmentLabel(value: string): string {
  return value === "delivery" ? "配送" : "自提";
}

function registrationStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: "待确认",
    confirmed: "已确认",
    cancelled: "已取消",
  };
  return labels[status] || status;
}

function registrationStatusType(status: string): "success" | "warning" | "info" | "danger" {
  if (status === "confirmed") return "success";
  if (status === "pending") return "warning";
  if (status === "cancelled") return "info";
  return "danger";
}

function appendMiniappQuery(params: URLSearchParams, key: string, value: string): void {
  if (value) {
    params.set(key, value);
  }
}

function buildRegistrationPath(): string {
  const campaign = selectedCampaign.value;
  if (!campaign) {
    return "";
  }
  const params = new URLSearchParams();
  appendMiniappQuery(params, "campaignId", campaign.id);
  appendMiniappQuery(params, "title", campaign.title);
  appendMiniappQuery(params, "groupName", selectedGroup.value?.name || "");
  return `/pages/group-registration/index?${params.toString()}`;
}

async function loadGroups(): Promise<void> {
  loading.value = true;
  try {
    groups.value = await customerGroupsService.listGroups(keyword.value);
    if (!selectedGroupId.value && groups.value.length) {
      selectedGroupId.value = groups.value[0].id;
    }
  } catch {
    ElMessage.error("客户群加载失败");
  } finally {
    loading.value = false;
  }
}

async function loadCampaigns(): Promise<void> {
  campaigns.value = await customerGroupsService.listCampaigns(selectedGroupId.value);
  if (!selectedCampaignId.value && campaigns.value.length) {
    selectedCampaignId.value = campaigns.value[0].id;
  }
}

async function loadSummary(): Promise<void> {
  if (!selectedCampaignId.value) {
    selectedSummary.value = null;
    return;
  }
  summaryLoading.value = true;
  try {
    selectedSummary.value = await customerGroupsService.getCampaignSummary(selectedCampaignId.value);
  } catch {
    selectedSummary.value = null;
    ElMessage.error("汇总加载失败");
  } finally {
    summaryLoading.value = false;
  }
}

async function refreshAll(): Promise<void> {
  await loadGroups();
  await loadCampaigns();
  await loadSummary();
}

async function submitSearch(): Promise<void> {
  selectedGroupId.value = "";
  selectedCampaignId.value = "";
  await refreshAll();
}

async function selectGroup(group: CustomerGroup): Promise<void> {
  selectedGroupId.value = group.id;
  selectedCampaignId.value = "";
  await loadCampaigns();
  await loadSummary();
}

async function selectCampaign(campaign: GroupCampaign): Promise<void> {
  selectedCampaignId.value = campaign.id;
  await loadSummary();
}

function openGroupForm(): void {
  groupDraft.value = createEmptyGroupDraft();
  groupFormVisible.value = true;
}

function openCampaignForm(): void {
  campaignDraft.value = createEmptyCampaignDraft();
  campaignFormVisible.value = true;
}

async function saveGroup(): Promise<void> {
  formSubmitting.value = true;
  try {
    const saved = await customerGroupsService.bindGroup(groupDraft.value);
    ElMessage.success("客户群已绑定");
    groupFormVisible.value = false;
    selectedGroupId.value = saved.id;
    await refreshAll();
  } catch {
    ElMessage.error("保存客户群失败，请检查 chat_id");
  } finally {
    formSubmitting.value = false;
  }
}

async function saveCampaign(): Promise<void> {
  formSubmitting.value = true;
  try {
    const saved = await customerGroupsService.createCampaign(campaignDraft.value);
    ElMessage.success("团购批次已创建");
    campaignFormVisible.value = false;
    selectedCampaignId.value = saved.id;
    await loadCampaigns();
    await loadSummary();
  } catch {
    ElMessage.error("创建批次失败，请先选择客户群并填写标题");
  } finally {
    formSubmitting.value = false;
  }
}

async function updateRegistrationStatus(
  row: GroupRegistration,
  status: GroupRegistration["status"],
): Promise<void> {
  const loadingKey = `${row.id}:${status}`;
  actionLoadingKey.value = loadingKey;
  try {
    await customerGroupsService.updateRegistrationStatus(row.id, status);
    ElMessage.success(`登记已更新为${registrationStatusLabel(status)}`);
    await loadSummary();
  } catch {
    ElMessage.error("登记状态更新失败");
  } finally {
    actionLoadingKey.value = "";
  }
}

async function copySummaryText(): Promise<void> {
  const text = selectedSummary.value?.summaryText || "";
  if (!text) {
    ElMessage.warning("暂无可复制的汇总文案");
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success("汇总文案已复制");
  } catch {
    ElMessage.error("复制失败，请手动选择文案复制");
  }
}

async function copyRegistrationPath(): Promise<void> {
  const text = buildRegistrationPath();
  if (!text) {
    ElMessage.warning("请先选择团购批次");
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success("登记路径已复制");
  } catch {
    ElMessage.error("复制失败，请手动复制登记路径");
  }
}

onMounted(() => {
  void refreshAll();
});
</script>

<template>
  <section class="customer-groups-page" data-testid="customer-groups-page">
    <el-card shadow="never" class="customer-groups-page__card">
      <template #header>
        <div class="customer-groups-page__header">
          <div>
            <span class="customer-groups-page__title">客户群运营</span>
            <span class="customer-groups-page__subtitle">客户群团购登记、批次汇总和群内文案</span>
          </div>
          <div class="customer-groups-page__stats">
            <span>{{ groups.length }} 个客户群</span>
            <span>{{ activeCampaigns.length }} 个进行中批次</span>
          </div>
        </div>
      </template>

      <div class="customer-groups-page__layout">
        <aside class="customer-groups-page__side">
          <div class="customer-groups-page__toolbar">
            <el-input
              v-model="keyword"
              placeholder="搜索群名、chat_id、群主"
              clearable
              data-testid="customer-groups-search"
              @keyup.enter="submitSearch"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
            <el-button :icon="Refresh" data-testid="customer-groups-refresh" @click="refreshAll" />
            <el-button type="primary" :icon="Plus" data-testid="customer-groups-create" @click="openGroupForm" />
          </div>

          <div v-loading="loading" class="customer-groups-page__group-list">
            <button
              v-for="group in groups"
              :key="group.id"
              class="customer-groups-page__group"
              :class="{ 'customer-groups-page__group--active': group.id === selectedGroupId }"
              :data-testid="`customer-groups-select-${group.id}`"
              @click="selectGroup(group)"
            >
              <strong>{{ group.name || group.chatId }}</strong>
              <span>{{ group.chatId }}</span>
              <em>{{ group.ownerUserid || "未记录群主" }}</em>
            </button>
            <el-empty v-if="!loading && !groups.length" description="暂无客户群" :image-size="80" />
          </div>
        </aside>

        <main class="customer-groups-page__main">
          <div class="customer-groups-page__campaign-bar">
            <div>
              <span class="customer-groups-page__section-title">团购批次</span>
              <span class="customer-groups-page__muted">
                {{ selectedGroup?.name || "请先选择客户群" }}
              </span>
            </div>
            <div class="customer-groups-page__actions">
              <el-select
                v-model="selectedCampaignId"
                placeholder="选择批次"
                style="width: 240px"
                data-testid="customer-groups-campaign-select"
                @change="loadSummary"
              >
                <el-option
                  v-for="campaign in campaigns"
                  :key="campaign.id"
                  :label="campaign.title"
                  :value="campaign.id"
                />
              </el-select>
              <el-button
                plain
                :icon="CopyDocument"
                :disabled="!selectedCampaignId"
                data-testid="customer-groups-copy-registration-path"
                @click="copyRegistrationPath"
              >
                复制登记路径
              </el-button>
              <el-button
                type="primary"
                :icon="Plus"
                :disabled="!selectedGroupId"
                data-testid="customer-groups-create-campaign"
                @click="openCampaignForm"
              >
                新建批次
              </el-button>
            </div>
          </div>

          <div class="customer-groups-page__summary-cards" v-loading="summaryLoading">
            <div class="customer-groups-page__summary-card">
              <span>登记人数</span>
              <strong>{{ selectedSummary?.totalRegistrations ?? 0 }}</strong>
            </div>
            <div class="customer-groups-page__summary-card">
              <span>商品数量</span>
              <strong>{{ selectedSummary?.totalQuantity ?? 0 }}</strong>
            </div>
            <div class="customer-groups-page__summary-card">
              <span>待确认</span>
              <strong>{{ pendingCount }}</strong>
            </div>
            <div class="customer-groups-page__summary-card">
              <span>已确认</span>
              <strong>{{ confirmedCount }}</strong>
            </div>
            <div class="customer-groups-page__summary-card">
              <span>已取消</span>
              <strong>{{ cancelledCount }}</strong>
            </div>
          </div>

          <div class="customer-groups-page__content">
            <section class="customer-groups-page__panel">
              <div class="customer-groups-page__panel-head">
                <span class="customer-groups-page__section-title">商品汇总</span>
              </div>
              <el-table
                :data="selectedSummary?.productTotals ?? []"
                stripe
                height="220"
                data-testid="customer-groups-product-totals"
              >
                <el-table-column prop="productName" label="商品" min-width="180" show-overflow-tooltip />
                <el-table-column prop="quantity" label="数量" width="90" align="right" />
              </el-table>
            </section>

            <section class="customer-groups-page__panel">
              <div class="customer-groups-page__panel-head">
                <span class="customer-groups-page__section-title">群内文案</span>
                <el-button
                  type="primary"
                  plain
                  :icon="CopyDocument"
                  data-testid="customer-groups-copy-summary"
                  @click="copySummaryText"
                >
                  复制
                </el-button>
              </div>
              <pre class="customer-groups-page__summary-text" data-testid="customer-groups-summary-text">{{
                selectedSummary?.summaryText || "暂无汇总文案"
              }}</pre>
            </section>
          </div>

          <section class="customer-groups-page__registrations">
            <div class="customer-groups-page__panel-head">
              <span class="customer-groups-page__section-title">登记明细</span>
              <span class="customer-groups-page__muted">
                {{ selectedCampaign?.title || "未选择批次" }}
              </span>
            </div>
            <el-table
              :data="selectedSummary?.registrations ?? []"
              v-loading="summaryLoading"
              stripe
              class="customer-groups-page__table"
              data-testid="customer-groups-registrations-table"
            >
              <el-table-column prop="customerName" label="客户" min-width="100" show-overflow-tooltip />
              <el-table-column prop="customerPhone" label="手机号" min-width="130" show-overflow-tooltip />
              <el-table-column prop="productName" label="商品" min-width="170" show-overflow-tooltip />
              <el-table-column prop="quantity" label="数量" width="80" align="right" />
              <el-table-column label="履约" width="90" align="center">
                <template #default="{ row }">{{ fulfillmentLabel(row.fulfillmentMethod) }}</template>
              </el-table-column>
              <el-table-column prop="desiredTime" label="期望时间" min-width="130" show-overflow-tooltip />
              <el-table-column prop="remark" label="备注" min-width="150" show-overflow-tooltip />
              <el-table-column label="状态" width="90" align="center">
                <template #default="{ row }">
                  <el-tag :type="registrationStatusType(row.status)" effect="light" size="small">
                    {{ registrationStatusLabel(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="提交时间" width="160" align="center">
                <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
              </el-table-column>
              <el-table-column label="操作" width="180" fixed="right" align="center">
                <template #default="{ row }">
                  <div class="customer-groups-page__row-actions">
                    <el-button
                      v-if="row.status !== 'confirmed'"
                      type="success"
                      plain
                      size="small"
                      :loading="actionLoadingKey === `${row.id}:confirmed`"
                      @click="updateRegistrationStatus(row, 'confirmed')"
                    >
                      确认
                    </el-button>
                    <el-button
                      v-if="row.status !== 'cancelled'"
                      type="info"
                      plain
                      size="small"
                      :loading="actionLoadingKey === `${row.id}:cancelled`"
                      @click="updateRegistrationStatus(row, 'cancelled')"
                    >
                      取消
                    </el-button>
                  </div>
                </template>
              </el-table-column>
            </el-table>
          </section>
        </main>
      </div>
    </el-card>

    <el-drawer v-model="groupFormVisible" title="绑定客户群" size="420px" append-to-body>
      <el-form label-position="top" class="customer-groups-page__form" @submit.prevent>
        <el-form-item label="客户群 chat_id" required>
          <el-input v-model.trim="groupDraft.chatId" placeholder="企业微信客户群 chat_id" />
        </el-form-item>
        <el-form-item label="群名称">
          <el-input v-model.trim="groupDraft.name" placeholder="例如 周末团购群" />
        </el-form-item>
        <el-form-item label="opengid">
          <el-input v-model.trim="groupDraft.opengid" placeholder="小程序群入口 opengid" />
        </el-form-item>
        <el-form-item label="群主 userid">
          <el-input v-model.trim="groupDraft.ownerUserid" placeholder="企业微信员工 userid" />
        </el-form-item>
        <el-form-item label="来源">
          <el-input v-model.trim="groupDraft.source" placeholder="例如 六月团购活动" />
        </el-form-item>
        <div class="customer-groups-page__form-actions">
          <el-button @click="groupFormVisible = false">取消</el-button>
          <el-button type="primary" :loading="formSubmitting" @click="saveGroup">保存</el-button>
        </div>
      </el-form>
    </el-drawer>

    <el-drawer v-model="campaignFormVisible" title="新建团购批次" size="420px" append-to-body>
      <el-form label-position="top" class="customer-groups-page__form" @submit.prevent>
        <el-form-item label="客户群" required>
          <el-select v-model="campaignDraft.groupId" placeholder="选择客户群" style="width: 100%">
            <el-option v-for="group in groups" :key="group.id" :label="group.name || group.chatId" :value="group.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="批次标题" required>
          <el-input v-model.trim="campaignDraft.title" placeholder="例如 周六蛋糕团购" />
        </el-form-item>
        <el-form-item label="开始时间">
          <el-input v-model.trim="campaignDraft.startsAt" placeholder="例如 2026-06-22 10:00" />
        </el-form-item>
        <el-form-item label="截止时间">
          <el-input v-model.trim="campaignDraft.endsAt" placeholder="例如 2026-06-22 20:00" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model.trim="campaignDraft.summaryNote" type="textarea" :rows="3" placeholder="内部说明" />
        </el-form-item>
        <div class="customer-groups-page__form-actions">
          <el-button @click="campaignFormVisible = false">取消</el-button>
          <el-button type="primary" :loading="formSubmitting" @click="saveCampaign">保存</el-button>
        </div>
      </el-form>
    </el-drawer>
  </section>
</template>

<style scoped>
.customer-groups-page,
.customer-groups-page__card {
  height: 100%;
}

.customer-groups-page__card :deep(.el-card__body) {
  height: calc(100% - 57px);
}

.customer-groups-page__header,
.customer-groups-page__campaign-bar,
.customer-groups-page__panel-head,
.customer-groups-page__toolbar,
.customer-groups-page__actions,
.customer-groups-page__row-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.customer-groups-page__header,
.customer-groups-page__campaign-bar,
.customer-groups-page__panel-head {
  justify-content: space-between;
}

.customer-groups-page__title,
.customer-groups-page__section-title {
  display: block;
  color: var(--yx-text);
  font-size: 15px;
  font-weight: 600;
}

.customer-groups-page__subtitle,
.customer-groups-page__stats,
.customer-groups-page__muted {
  color: var(--yx-text-muted);
  font-size: 13px;
}

.customer-groups-page__stats {
  display: flex;
  gap: 12px;
}

.customer-groups-page__layout {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 14px;
  height: 100%;
  min-height: 0;
}

.customer-groups-page__side,
.customer-groups-page__main,
.customer-groups-page__panel,
.customer-groups-page__registrations {
  min-height: 0;
}

.customer-groups-page__side,
.customer-groups-page__main {
  display: grid;
  gap: 12px;
}

.customer-groups-page__side {
  grid-template-rows: auto minmax(0, 1fr);
  padding-right: 14px;
  border-right: 1px solid var(--el-border-color-lighter);
}

.customer-groups-page__main {
  grid-template-rows: auto auto minmax(250px, 0.72fr) minmax(260px, 1fr);
}

.customer-groups-page__group-list {
  display: grid;
  align-content: start;
  gap: 8px;
  overflow: auto;
}

.customer-groups-page__group {
  display: grid;
  gap: 5px;
  width: 100%;
  min-height: 78px;
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
  color: var(--yx-text);
  text-align: left;
  cursor: pointer;
}

.customer-groups-page__group strong {
  font-size: 14px;
}

.customer-groups-page__group span,
.customer-groups-page__group em {
  color: var(--yx-text-muted);
  font-size: 12px;
  font-style: normal;
}

.customer-groups-page__group--active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.customer-groups-page__summary-cards {
  display: grid;
  grid-template-columns: repeat(5, minmax(110px, 1fr));
  gap: 10px;
}

.customer-groups-page__summary-card {
  display: grid;
  gap: 6px;
  min-height: 74px;
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
}

.customer-groups-page__summary-card span {
  color: var(--yx-text-muted);
  font-size: 12px;
}

.customer-groups-page__summary-card strong {
  color: var(--yx-text);
  font-size: 24px;
  line-height: 1;
}

.customer-groups-page__content {
  display: grid;
  grid-template-columns: minmax(260px, 0.9fr) minmax(320px, 1.1fr);
  gap: 12px;
  min-height: 0;
}

.customer-groups-page__panel,
.customer-groups-page__registrations {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
}

.customer-groups-page__summary-text {
  min-height: 0;
  margin: 0;
  padding: 12px;
  overflow: auto;
  border-radius: 6px;
  background: var(--el-fill-color-light);
  color: var(--yx-text);
  font-family: inherit;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.customer-groups-page__table {
  min-height: 0;
}

.customer-groups-page__row-actions {
  justify-content: center;
  flex-wrap: wrap;
}

.customer-groups-page__form {
  display: grid;
  gap: 2px;
}

.customer-groups-page__form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding-top: 8px;
}

@media (max-width: 900px) {
  .customer-groups-page__layout,
  .customer-groups-page__content {
    grid-template-columns: 1fr;
  }

  .customer-groups-page__layout {
    height: auto;
  }

  .customer-groups-page__side {
    padding-right: 0;
    border-right: 0;
  }

  .customer-groups-page__summary-cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .customer-groups-page__header,
  .customer-groups-page__campaign-bar {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
