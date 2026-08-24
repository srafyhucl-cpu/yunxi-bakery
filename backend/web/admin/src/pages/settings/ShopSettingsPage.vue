<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import SettingsStatusPanel from "@/features/settings/SettingsStatusPanel.vue";
import { shopSettingsService } from "@/services/shopSettings";
import type { ShopOperationsSettings } from "@/types/shopSettings";

const loading = ref(false);
const saving = ref(false);
const settings = ref<ShopOperationsSettings>(shopSettingsService.defaults);
const businessHoursError = ref("");
const businessHoursPattern = /^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$/;

const paymentModeLabel = computed(() => {
  if (settings.value.paymentMode === "mock") {
    return "模拟支付";
  }
  if (settings.value.paymentMode === "wechat") {
    return "微信支付";
  }
  return "门店确认";
});

function parseBusinessHourMinutes(value: string): [number, number] | null {
  const match = value.trim().match(businessHoursPattern);
  if (!match) {
    return null;
  }
  const startHour = Number(match[1]);
  const startMinute = Number(match[2]);
  const endHour = Number(match[3]);
  const endMinute = Number(match[4]);
  const isValidTime =
    startHour >= 0 &&
    startHour <= 23 &&
    endHour >= 0 &&
    endHour <= 23 &&
    startMinute >= 0 &&
    startMinute <= 59 &&
    endMinute >= 0 &&
    endMinute <= 59;
  if (!isValidTime) {
    return null;
  }
  return [startHour * 60 + startMinute, endHour * 60 + endMinute];
}

function validateBusinessHours(): boolean {
  const normalized = settings.value.businessHours.trim();
  const minutes = parseBusinessHourMinutes(normalized);
  if (!minutes) {
    businessHoursError.value = "营业时间格式应为 HH:mm-HH:mm，例如 09:00-20:00";
    return false;
  }
  if (minutes[1] <= minutes[0]) {
    businessHoursError.value = "结束时间必须晚于开始时间";
    return false;
  }
  businessHoursError.value = "";
  settings.value = { ...settings.value, businessHours: normalized };
  return true;
}

async function loadSettings(): Promise<void> {
  loading.value = true;
  try {
    settings.value = await shopSettingsService.getSettings();
  } catch {
    ElMessage.error("店铺配置加载失败");
  } finally {
    loading.value = false;
  }
}

async function saveSettings(): Promise<void> {
  if (!validateBusinessHours()) {
    ElMessage.warning(businessHoursError.value);
    return;
  }
  saving.value = true;
  try {
    settings.value = await shopSettingsService.saveSettings(settings.value);
    ElMessage.success("店铺配置已保存");
  } catch {
    ElMessage.error("店铺配置保存失败");
  } finally {
    saving.value = false;
  }
}

function resetSettings(): void {
  settings.value = { ...shopSettingsService.defaults };
  businessHoursError.value = "";
}

onMounted(() => {
  void loadSettings();
});
</script>

<template>
  <section class="shop-settings-page" data-testid="shop-settings-page">
    <el-card shadow="never">
      <template #header>
        <div class="shop-settings-page__header">
          <div>
            <strong>店铺配置</strong>
            <p>统一维护小程序公开运营信息，避免在页面里写死客服电话、营业时间和说明文案。</p>
          </div>
          <div class="shop-settings-page__actions">
            <el-button data-testid="shop-settings-reset" @click="resetSettings">重置</el-button>
            <el-button data-testid="shop-settings-refresh" :loading="loading" @click="loadSettings">刷新</el-button>
            <el-button
              type="primary"
              :loading="saving"
              data-testid="shop-settings-save"
              @click="saveSettings"
            >
              保存
            </el-button>
          </div>
        </div>
      </template>

      <el-form label-width="120px" class="shop-settings-page__form">
        <el-form-item label="店铺名称">
          <el-input v-model="settings.shopName" maxlength="20" data-testid="shop-settings-shop-name" />
        </el-form-item>
        <el-form-item label="客服电话">
          <el-input v-model="settings.customerPhone" maxlength="20" data-testid="shop-settings-customer-phone" />
        </el-form-item>
        <el-form-item label="客服微信">
          <el-input v-model="settings.customerWechat" maxlength="30" data-testid="shop-settings-customer-wechat" />
        </el-form-item>
        <el-form-item label="营业时间">
          <el-input
            v-model="settings.businessHours"
            maxlength="30"
            data-testid="shop-settings-business-hours"
            placeholder="09:00-20:00"
            @blur="validateBusinessHours"
          />
          <p class="shop-settings-page__field-tip" data-testid="shop-settings-business-hours-tip">
            用于限制小程序 checkout 可选择的下单时段，格式：09:00-20:00。
          </p>
          <p
            v-if="businessHoursError"
            class="shop-settings-page__field-error"
            data-testid="shop-settings-business-hours-error"
          >
            {{ businessHoursError }}
          </p>
        </el-form-item>
        <el-form-item label="自提地址说明">
          <el-input v-model="settings.pickupAddress" type="textarea" :rows="2" data-testid="shop-settings-pickup-address" />
        </el-form-item>
        <el-form-item label="配送说明">
          <el-input v-model="settings.deliveryNotice" type="textarea" :rows="2" data-testid="shop-settings-delivery-notice" />
        </el-form-item>
        <el-form-item label="自提说明">
          <el-input v-model="settings.pickupNotice" type="textarea" :rows="2" data-testid="shop-settings-pickup-notice" />
        </el-form-item>
        <el-divider content-position="left">协议与售后</el-divider>
        <el-form-item label="隐私标题">
          <el-input
            v-model="settings.privacyPolicyTitle"
            maxlength="20"
            data-testid="shop-settings-privacy-title"
          />
        </el-form-item>
        <el-form-item label="隐私内容">
          <el-input
            v-model="settings.privacyPolicyContent"
            type="textarea"
            :rows="4"
            maxlength="600"
            show-word-limit
            data-testid="shop-settings-privacy-content"
          />
        </el-form-item>
        <el-form-item label="协议标题">
          <el-input
            v-model="settings.userAgreementTitle"
            maxlength="20"
            data-testid="shop-settings-agreement-title"
          />
        </el-form-item>
        <el-form-item label="协议内容">
          <el-input
            v-model="settings.userAgreementContent"
            type="textarea"
            :rows="4"
            maxlength="600"
            show-word-limit
            data-testid="shop-settings-agreement-content"
          />
        </el-form-item>
        <el-form-item label="售后标题">
          <el-input
            v-model="settings.afterSalesPolicyTitle"
            maxlength="20"
            data-testid="shop-settings-after-sales-title"
          />
        </el-form-item>
        <el-form-item label="售后内容">
          <el-input
            v-model="settings.afterSalesPolicyContent"
            type="textarea"
            :rows="4"
            maxlength="600"
            show-word-limit
            data-testid="shop-settings-after-sales-content"
          />
        </el-form-item>
        <el-form-item label="支付模式">
          <el-tag :type="paymentModeLabel === '微信支付' ? 'success' : paymentModeLabel === '模拟支付' ? 'warning' : 'info'">
            {{ paymentModeLabel }}
          </el-tag>
        </el-form-item>
      </el-form>
    </el-card>

    <SettingsStatusPanel panel="shop" />
  </section>
</template>

<style scoped>
.shop-settings-page {
  display: grid;
  gap: 16px;
}

.shop-settings-page__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.shop-settings-page__header p {
  margin: 6px 0 0;
  color: var(--yx-text-muted);
  font-size: 13px;
}

.shop-settings-page__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.shop-settings-page__form {
  max-width: 920px;
}

.shop-settings-page__field-tip,
.shop-settings-page__field-error {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.5;
}

.shop-settings-page__field-tip {
  color: var(--yx-text-muted);
}

.shop-settings-page__field-error {
  color: var(--el-color-danger);
}

@media (max-width: 767px) {
  .shop-settings-page__header {
    flex-direction: column;
  }
}
</style>
