<script setup lang="ts">
import { onMounted } from "vue";
import {
  ChatDotRound,
  CircleCheckFilled,
  Clock,
  Goods,
  Histogram,
  MagicStick,
  RefreshRight,
  Service,
  Setting,
  Tickets,
  WarningFilled,
} from "@element-plus/icons-vue";

import { useOverviewPage } from "./useOverviewPage";

const {
  loading,
  errorMessage,
  lastRefreshedAt,
  productTotal,
  activeProductTotal,
  inactiveProductTotal,
  orderTotal,
  pendingOrderCount,
  orderAmountText,
  pendingTransferCount,
  failedHistoryTotal,
  failedWebhookTotal,
  slowWebhookTotal,
  processingWebhookTotal,
  configuredSettingCount,
  decorationStatusText,
  decorationUpdatedAt,
  recentOrders,
  recentIssues,
  healthLabel,
  healthType,
  loadOverview,
} = useOverviewPage();

const quickLinks = [
  { title: "店铺装修", desc: "编辑首页模块并发布到小程序", to: "/decoration", icon: MagicStick },
  { title: "订单管理", desc: "确认订单、推进制作和配送", to: "/orders", icon: Tickets },
  { title: "商品管理", desc: "上下架商品和设置主推款", to: "/products", icon: Goods },
  { title: "店铺配置", desc: "维护电话、微信和配送说明", to: "/settings/shop", icon: Setting },
];

const mobileOperationLinks = [
  { title: "待确认", desc: "立即处理新订单", to: "/orders?status=pending", icon: Tickets, tone: "red" },
  { title: "转人工", desc: "接待顾客咨询", to: "/transfers", icon: Service, tone: "green" },
  { title: "上下架", desc: "快速调整商品", to: "/products", icon: Goods, tone: "blue" },
  { title: "店铺配置", desc: "电话与配送说明", to: "/settings/shop", icon: Setting, tone: "orange" },
];

onMounted(loadOverview);
</script>

<template>
  <section class="overview-page">
    <el-card shadow="never" class="overview-page__hero" v-loading="loading">
      <div class="hero-left">
        <span class="hero-eyebrow">Yunxi Store MVP</span>
        <h2>商城经营台</h2>
        <p>订单 · 商品 · 装修 · 客服待处理一屏掌握</p>
      </div>
      <div class="hero-right">
        <el-tag :type="healthType" size="large" effect="dark" class="health-tag">
          <span class="health-dot" />
          {{ healthLabel }}
        </el-tag>
        <div class="hero-refresh">
          <el-button :icon="RefreshRight" plain size="small" @click="loadOverview">刷新</el-button>
          <span v-if="lastRefreshedAt" class="refresh-time">
            <el-icon size="11"><Clock /></el-icon>
            {{ lastRefreshedAt }}
          </span>
        </div>
      </div>
    </el-card>

    <el-alert v-if="errorMessage" type="warning" show-icon :closable="false" :title="errorMessage" />

    <div class="mobile-ops" data-testid="overview-mobile-ops">
      <router-link
        v-for="link in mobileOperationLinks"
        :key="link.to"
        class="mobile-op"
        :class="`mobile-op--${link.tone}`"
        :to="link.to"
        :data-testid="`overview-mobile-op-${link.tone}`"
      >
        <span class="mobile-op__icon">
          <el-icon size="18"><component :is="link.icon" /></el-icon>
        </span>
        <span class="mobile-op__body">
          <strong>{{ link.title }}</strong>
          <small>{{ link.desc }}</small>
        </span>
      </router-link>
    </div>

    <div class="metrics-grid">
      <router-link to="/orders" class="metric-card metric-card--orange">
        <div class="metric-card__header">
          <span class="metric-card__label">小程序订单</span>
          <span class="metric-icon metric-icon--orange"><el-icon size="18"><Tickets /></el-icon></span>
        </div>
        <strong class="metric-card__value">{{ orderTotal }}</strong>
        <span class="metric-card__cta">{{ orderAmountText }} · 查看订单 →</span>
      </router-link>

      <router-link to="/orders?status=pending" class="metric-card metric-card--red">
        <div class="metric-card__header">
          <span class="metric-card__label">待确认订单</span>
          <span class="metric-icon metric-icon--red"><el-icon size="18"><WarningFilled /></el-icon></span>
        </div>
        <strong class="metric-card__value" :class="{ 'is-danger': pendingOrderCount > 0 }">
          {{ pendingOrderCount }}
        </strong>
        <span class="metric-card__cta">马上处理 →</span>
      </router-link>

      <router-link to="/products" class="metric-card metric-card--blue">
        <div class="metric-card__header">
          <span class="metric-card__label">商品池</span>
          <span class="metric-icon metric-icon--blue"><el-icon size="18"><Goods /></el-icon></span>
        </div>
        <strong class="metric-card__value">{{ productTotal }}</strong>
        <span class="metric-card__cta">在售 {{ activeProductTotal }} · 下架 {{ inactiveProductTotal }}</span>
      </router-link>

      <router-link to="/transfers" class="metric-card metric-card--green">
        <div class="metric-card__header">
          <span class="metric-card__label">待处理客服</span>
          <span class="metric-icon metric-icon--green"><el-icon size="18"><Service /></el-icon></span>
        </div>
        <strong class="metric-card__value">{{ pendingTransferCount }}</strong>
        <span class="metric-card__cta">接待会话 →</span>
      </router-link>
    </div>

    <div class="overview-grid">
      <el-card shadow="never">
        <template #header>
          <div class="section-title">
            <strong>最近订单</strong>
            <router-link to="/orders">全部订单 →</router-link>
          </div>
        </template>
        <div v-if="recentOrders.length" class="order-list">
          <router-link
            v-for="order in recentOrders"
            :key="order.id"
            class="order-item"
            :to="`/orders?keyword=${encodeURIComponent(order.id)}`"
          >
            <div>
              <strong>{{ order.itemTitle || "未命名商品" }}</strong>
              <span>{{ order.receiverName || "未填写" }} · {{ order.expectTime || "时间待确认" }}</span>
            </div>
            <div class="order-item__right">
              <el-tag size="small" effect="light">{{ order.statusText }}</el-tag>
              <strong>{{ order.totalText }}</strong>
            </div>
          </router-link>
        </div>
        <el-empty v-else description="暂无小程序订单" :image-size="80" />
      </el-card>

      <el-card shadow="never">
        <template #header>
          <div class="section-title">
            <strong>上线检查</strong>
            <router-link to="/settings/shop">配置详情 →</router-link>
          </div>
        </template>
        <div class="readiness-list">
          <div class="readiness-item">
            <span>首页装修</span>
            <strong>{{ decorationStatusText }}</strong>
            <small>{{ decorationUpdatedAt || "未记录发布时间" }}</small>
          </div>
          <div class="readiness-item">
            <span>渠道配置</span>
            <strong>{{ configuredSettingCount }}/6</strong>
            <small>有赞、企微和管理 Token 状态</small>
          </div>
          <div class="readiness-item">
            <span>数据异常</span>
            <strong>{{ failedHistoryTotal + failedWebhookTotal + slowWebhookTotal }}</strong>
            <small>失败或慢处理事件</small>
          </div>
          <div class="readiness-item">
            <span>Webhook 队列</span>
            <strong>{{ processingWebhookTotal }}</strong>
            <small>处理中事件</small>
          </div>
        </div>
      </el-card>
    </div>

    <div class="overview-grid">
      <el-card shadow="never">
        <template #header>
          <div class="section-title">
            <strong>待办提醒</strong>
            <router-link to="/observability/failures">失败排查 →</router-link>
          </div>
        </template>
        <div class="issues-list">
          <router-link
            v-for="issue in recentIssues"
            :key="issue.title"
            class="issue-item"
            :class="`issue-item--${issue.level}`"
            :to="issue.route"
          >
            <el-icon class="issue-item__icon" size="20">
              <CircleCheckFilled v-if="issue.level === 'success'" />
              <WarningFilled v-else />
            </el-icon>
            <div class="issue-item__body">
              <strong>{{ issue.title }}</strong>
              <span>{{ issue.description }}</span>
            </div>
          </router-link>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header><strong>快捷入口</strong></template>
        <div class="quick-links">
          <router-link v-for="link in quickLinks" :key="link.to" class="quick-link" :to="link.to">
            <span class="quick-link__icon">
              <el-icon size="20"><component :is="link.icon" /></el-icon>
            </span>
            <div class="quick-link__body">
              <strong>{{ link.title }}</strong>
              <span>{{ link.desc }}</span>
            </div>
          </router-link>
          <router-link class="quick-link" to="/ai-dialog">
            <span class="quick-link__icon">
              <el-icon size="20"><ChatDotRound /></el-icon>
            </span>
            <div class="quick-link__body">
              <strong>AI 对话</strong>
              <span>验证客服回复和知识命中</span>
            </div>
          </router-link>
          <router-link class="quick-link" to="/observability/sessions">
            <span class="quick-link__icon">
              <el-icon size="20"><Histogram /></el-icon>
            </span>
            <div class="quick-link__body">
              <strong>数据观察台</strong>
              <span>查看回写、Webhook 和同步状态</span>
            </div>
          </router-link>
        </div>
      </el-card>
    </div>
  </section>
</template>

<style scoped>
.overview-page {
  display: grid;
  gap: 16px;
}

.overview-page__hero {
  background: linear-gradient(135deg, #fff7ee 0%, #ffffff 52%, #eef6ff 100%);
}

.overview-page__hero :deep(.el-card__body) {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 24px;
}

.hero-eyebrow {
  color: var(--yx-brand);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.hero-left h2 {
  margin: 6px 0 4px;
  font-size: 28px;
}

.hero-left p {
  margin: 0;
  font-size: 14px;
  color: var(--yx-text-muted);
}

.hero-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
  flex-shrink: 0;
}

.health-tag,
.hero-refresh,
.refresh-time {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.health-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}

.refresh-time {
  font-size: 12px;
  color: var(--yx-text-muted);
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.mobile-ops {
  display: none;
}

.mobile-op {
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--yx-border);
  border-radius: 10px;
  background: #fff;
  color: var(--yx-text);
  text-decoration: none;
}

.mobile-op__icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  flex-shrink: 0;
}

.mobile-op__body {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.mobile-op__body strong,
.mobile-op__body small {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.mobile-op__body small {
  color: var(--yx-text-muted);
  font-size: 12px;
}

.mobile-op--red .mobile-op__icon { background: #fff1f2; color: #e11d48; }
.mobile-op--green .mobile-op__icon { background: #ecfdf5; color: #10b981; }
.mobile-op--blue .mobile-op__icon { background: #eff6ff; color: #3b82f6; }
.mobile-op--orange .mobile-op__icon { background: #fff7ed; color: #f59e0b; }

.metric-card {
  display: grid;
  gap: 6px;
  padding: 20px;
  background: #fff;
  border: 1px solid var(--yx-border);
  border-radius: 12px;
  color: var(--yx-text);
  text-decoration: none;
  transition: box-shadow 0.2s, transform 0.2s;
}

.metric-card:hover {
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
  transform: translateY(-2px);
}

.metric-card__header,
.section-title,
.order-item,
.readiness-item,
.quick-link {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.metric-card__label,
.order-item span,
.readiness-item span,
.readiness-item small,
.quick-link__body span {
  font-size: 13px;
  color: var(--yx-text-muted);
}

.metric-icon {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.metric-icon--orange { background: #fff7ed; color: #f59e0b; }
.metric-icon--red { background: #fff1f2; color: #e11d48; }
.metric-icon--blue { background: #eff6ff; color: #3b82f6; }
.metric-icon--green { background: #ecfdf5; color: #10b981; }

.metric-card__value {
  margin: 6px 0 2px;
  font-size: 36px;
  line-height: 1;
  font-weight: 700;
}

.metric-card__value.is-danger {
  color: #e11d48;
}

.metric-card__cta,
.section-title a {
  color: var(--yx-brand);
  font-size: 12px;
  text-decoration: none;
}

.overview-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  gap: 16px;
}

.order-list,
.readiness-list,
.issues-list,
.quick-links {
  display: grid;
  gap: 10px;
}

.order-item,
.issue-item,
.quick-link {
  padding: 14px;
  border: 1px solid var(--yx-border);
  border-radius: 10px;
  color: var(--yx-text);
  text-decoration: none;
}

.order-item > div:first-child,
.quick-link__body,
.issue-item__body {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.order-item__right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.readiness-item {
  align-items: flex-start;
  padding: 12px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.readiness-item:last-child {
  border-bottom: 0;
}

.readiness-item strong {
  margin-left: auto;
  color: var(--yx-text);
}

.readiness-item small {
  width: 100%;
  margin-left: 0;
}

.issue-item {
  display: flex;
  justify-content: flex-start;
  border-left-width: 4px;
}

.issue-item--success { border-left-color: #10b981; }
.issue-item--warning { border-left-color: #f59e0b; }
.issue-item--danger { border-left-color: #ef4444; }
.issue-item--info { border-left-color: var(--yx-border); }

.issue-item__icon {
  flex-shrink: 0;
}

.quick-link {
  justify-content: flex-start;
}

.quick-link__icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: var(--yx-brand-soft);
  color: var(--yx-brand);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

@media (max-width: 1100px) {
  .metrics-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .overview-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 720px) {
  .overview-page__hero :deep(.el-card__body) {
    flex-direction: column;
  }

  .hero-right {
    align-items: flex-start;
  }

  .metrics-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .mobile-ops {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }

  .mobile-op {
    display: flex;
  }
}
</style>
