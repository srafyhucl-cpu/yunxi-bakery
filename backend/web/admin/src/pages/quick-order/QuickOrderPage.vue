<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { staffQuickOrderService } from "@/services/staffQuickOrder";
import type {
  QuickOrderItem,
  QuickOrderMode,
  QuickOrderPayload,
  QuickOrderResult,
  StaffMember,
  StaffPrincipal,
  StaffProduct,
} from "@/types/staffQuickOrder";

/** 购物车行的定制信息草稿（后端按字段强校验，前端允许留空）。 */
interface CartCustomization {
  size: string;
  filling: string;
  greeting: string;
  accessories: string;
}

interface CartLine {
  product: StaffProduct;
  quantity: number;
  /** 由店员显式勾选“按定制蛋糕处理”，默认 false，不按标题自动判定。 */
  isCakeOrder: boolean;
  customization: CartCustomization;
}

const CAKE_TITLE_KEYWORDS = ["蛋糕", "定制", "生日"];
const ROLE_LABELS: Record<string, string> = {
  owner: "店主",
  manager: "店长",
  staff: "店员",
  admin: "管理员",
};
const HISTORY_STATUS_LABELS: Record<string, string> = {
  WAIT_PAY: "待付款",
  WAIT_SELLER_SEND_GOODS: "待发货",
  WAIT_BUYER_CONFIRM_GOODS: "待收货",
  TRADE_PAID: "已支付",
  TRADE_SUCCESS: "交易成功",
  TRADE_CLOSED: "已关闭",
};
const DEFAULT_EXPECT_MINUTES = 30;
const RECENT_ORDER_LIMIT = 5;

const booting = ref(true);
const principal = ref<StaffPrincipal | null>(null);

const loginPhone = ref("");
const loginPin = ref("");
const loginLoading = ref(false);
const loginError = ref("");

const memberPhone = ref("");
const memberLoading = ref(false);
const memberError = ref("");
const member = ref<StaffMember | null>(null);

const productKeyword = ref("");
const productLoading = ref(false);
const productError = ref("");
const products = ref<StaffProduct[]>([]);

const cart = ref<CartLine[]>([]);
const mode = ref<QuickOrderMode>("stored_value_direct");
const expectTime = ref(defaultExpectTime());
const remark = ref("");

const submitting = ref(false);
const submitError = ref("");
const result = ref<QuickOrderResult | null>(null);
/** 开单成功时的金额快照：购物车清空后仍可在回执区展示订单金额。 */
const resultTotalFen = ref(0);

/** 未收到服务端明确结论时保留 requestId，重试可被后端幂等回放，避免重复扣款。 */
let pendingRequestId = "";

const cartCount = computed(() =>
  cart.value.reduce((total, line) => total + line.quantity, 0),
);
const totalFen = computed(() =>
  cart.value.reduce(
    (total, line) => total + line.product.priceFen * line.quantity,
    0,
  ),
);
const remainingBalanceFen = computed(() =>
  member.value ? member.value.storedValueFen - totalFen.value : 0,
);
const balanceInsufficient = computed(
  () =>
    mode.value === "stored_value_direct" &&
    !!member.value &&
    remainingBalanceFen.value < 0,
);
const hasCakeLine = computed(() =>
  cart.value.some((line) => line.isCakeOrder),
);
const recentOrders = computed(() =>
  (member.value?.historyOrders || []).slice(0, RECENT_ORDER_LIMIT),
);

function fenToYuan(fen: number): string {
  return (Math.round(fen) / 100).toFixed(2);
}

/** 生成北京时间 now + 分钟数的 YYYY-MM-DD HH:mm。 */
function beijingDateTimePlus(minutes: number): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(Date.now() + minutes * 60_000));
  const valueOf = (type: string) =>
    parts.find((part) => part.type === type)?.value || "";
  return `${valueOf("year")}-${valueOf("month")}-${valueOf("day")} ${valueOf("hour")}:${valueOf("minute")}`;
}

function defaultExpectTime(): string {
  return beijingDateTimePlus(DEFAULT_EXPECT_MINUTES);
}

/** 后端错误为 { detail }，登录限流等场景可能返回 { message }。 */
function readErrorMessage(error: unknown, fallback: string): string {
  if (typeof error === "object" && error !== null && "response" in error) {
    const response = (
      error as { response?: { data?: { detail?: unknown; message?: unknown } } }
    ).response;
    const detail = response?.data?.detail ?? response?.data?.message;
    if (typeof detail === "string" && detail) {
      return detail;
    }
  }
  return fallback;
}

function httpStatusOf(error: unknown): number | undefined {
  if (typeof error === "object" && error !== null && "response" in error) {
    return (error as { response?: { status?: number } }).response?.status;
  }
  return undefined;
}

function roleLabel(role: string): string {
  return ROLE_LABELS[role] || role || "店员";
}

function historyStatusText(status: string): string {
  return HISTORY_STATUS_LABELS[status] || status || "未知";
}

/** 标题命中蛋糕/定制/生日只用于提示店员“疑似蛋糕”，不自动按定制蛋糕处理。 */
function looksLikeCake(title: string): boolean {
  return CAKE_TITLE_KEYWORDS.some((keyword) => title.includes(keyword));
}

function growableMax(line: CartLine): number {
  return line.product.stock > 0 ? line.product.stock : 99;
}

function canAdd(product: StaffProduct): boolean {
  return product.isPurchasable && product.stock > 0;
}

function resetSession(): void {
  principal.value = null;
  member.value = null;
  memberPhone.value = "";
  memberError.value = "";
  products.value = [];
  productError.value = "";
  cart.value = [];
  result.value = null;
  resultTotalFen.value = 0;
  submitError.value = "";
  pendingRequestId = "";
}

/** 登录态过期时回到登录卡，避免继续用失效会话查询。 */
function expireSession(): void {
  resetSession();
  loginError.value = "登录已过期，请重新登录";
}

async function bootstrap(): Promise<void> {
  try {
    principal.value = await staffQuickOrderService.me();
    await searchProducts();
  } catch (error) {
    if (httpStatusOf(error) === 401) {
      principal.value = null;
    } else {
      loginError.value = readErrorMessage(error, "无法确认登录状态，请重新登录");
    }
  } finally {
    booting.value = false;
  }
}

async function submitLogin(): Promise<void> {
  if (loginLoading.value) {
    return;
  }
  loginError.value = "";
  const phone = loginPhone.value.trim();
  const pin = loginPin.value.trim();
  if (!/^1\d{10}$/.test(phone)) {
    loginError.value = "请输入有效的11位手机号";
    return;
  }
  if (!pin) {
    loginError.value = "请输入 PIN 码";
    return;
  }
  loginLoading.value = true;
  try {
    await staffQuickOrderService.login(phone, pin);
    principal.value = await staffQuickOrderService.me();
    loginPin.value = "";
    ElMessage.success(`欢迎，${principal.value.name}`);
    await searchProducts();
  } catch (error) {
    loginError.value = readErrorMessage(error, "登录失败，请检查手机号与 PIN");
  } finally {
    loginLoading.value = false;
  }
}

async function logout(): Promise<void> {
  try {
    await staffQuickOrderService.logout();
  } catch (error) {
    // 退出接口失败也要清理本地状态，但需告知店员当前登录态已不可信。
    ElMessage.warning(readErrorMessage(error, "退出登录请求失败，已清理本地状态"));
  }
  resetSession();
  loginError.value = "";
}

async function lookupMember(): Promise<void> {
  if (memberLoading.value) {
    return;
  }
  memberError.value = "";
  const phone = memberPhone.value.trim();
  if (!/^1\d{10}$/.test(phone)) {
    memberError.value = "请输入有效的11位手机号";
    return;
  }
  memberLoading.value = true;
  try {
    const found = await staffQuickOrderService.lookupMember(phone);
    const sameMember = member.value?.customerId === found.customerId;
    member.value = found;
    memberPhone.value = found.mobile;
    // 只有换成另一位会员才清空购物车与上一单回执，避免把商品开到别人名下。
    if (!sameMember) {
      cart.value = [];
      result.value = null;
      resultTotalFen.value = 0;
      submitError.value = "";
      pendingRequestId = "";
    }
  } catch (error) {
    member.value = null;
    if (httpStatusOf(error) === 401) {
      expireSession();
      return;
    }
    memberError.value = readErrorMessage(error, "会员查询失败");
  } finally {
    memberLoading.value = false;
  }
}

async function searchProducts(): Promise<void> {
  if (!principal.value || productLoading.value) {
    return;
  }
  productError.value = "";
  productLoading.value = true;
  try {
    products.value = await staffQuickOrderService.listProducts(
      productKeyword.value.trim(),
    );
  } catch (error) {
    products.value = [];
    if (httpStatusOf(error) === 401) {
      expireSession();
      return;
    }
    productError.value = readErrorMessage(error, "商品搜索失败");
  } finally {
    productLoading.value = false;
  }
}

function addToCart(product: StaffProduct): void {
  if (!canAdd(product)) {
    ElMessage.warning("该商品当前不可售");
    return;
  }
  const existing = cart.value.find(
    (line) => line.product.productId === product.productId,
  );
  if (existing) {
    increaseQuantity(existing);
    return;
  }
  cart.value.push({
    product,
    quantity: 1,
    // 默认按现货开单，是否定制由店员在购物车行内显式勾选。
    isCakeOrder: false,
    customization: { size: "", filling: "", greeting: "", accessories: "" },
  });
}

function increaseQuantity(line: CartLine): void {
  const max = growableMax(line);
  if (line.quantity >= max) {
    ElMessage.warning(`库存仅剩 ${line.product.stock} 件`);
    return;
  }
  line.quantity += 1;
}

function decreaseQuantity(line: CartLine): void {
  if (line.quantity > 1) {
    line.quantity -= 1;
  }
}

function removeLine(index: number): void {
  cart.value.splice(index, 1);
}

/** 收集定制信息缺项，提交前提示；缺项仍由后端强校验兜底。 */
function missingCustomizationHints(): string[] {
  const hints: string[] = [];
  for (const line of cart.value) {
    if (!line.isCakeOrder) {
      continue;
    }
    const missing: string[] = [];
    if (!line.customization.size.trim()) missing.push("尺寸");
    if (!line.customization.filling.trim()) missing.push("夹心");
    if (!line.customization.greeting.trim()) missing.push("祝福语");
    if (!line.customization.accessories.trim()) missing.push("配件");
    if (missing.length > 0) {
      hints.push(`${line.product.title}：${missing.join("/")}`);
    }
  }
  return hints;
}

async function confirmCustomization(): Promise<boolean> {
  const hints = missingCustomizationHints();
  if (hints.length === 0) {
    return true;
  }
  try {
    await ElMessageBox.confirm(
      `以下定制信息未填写：${hints.join("；")}。后台会强制校验定制蛋糕信息，缺项将被拒绝开单。是否仍然提交？`,
      "定制信息未填写完整",
      {
        confirmButtonText: "仍然提交",
        cancelButtonText: "返回补充",
        type: "warning",
      },
    );
    return true;
  } catch {
    return false;
  }
}

/** 优先生成 8-64 位字母数字 requestId，供后端做幂等占位。 */
function generateRequestId(): string {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && typeof cryptoApi.randomUUID === "function") {
    return `req-${cryptoApi.randomUUID()}`;
  }
  return `req-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function ensureRequestId(): string {
  if (!pendingRequestId) {
    pendingRequestId = generateRequestId();
  }
  return pendingRequestId;
}

function buildItems(): QuickOrderItem[] {
  return cart.value.map((line) => {
    if (!line.isCakeOrder) {
      // 未勾选定制：现货开单，不带定制字段，避免被后端判为预订蛋糕。
      return {
        productId: line.product.productId,
        quantity: line.quantity,
        fulfillmentType: "DAILY_READY",
        customization: {},
      };
    }
    return {
      productId: line.product.productId,
      quantity: line.quantity,
      fulfillmentType: "PREORDER_CAKE",
      customization: {
        size: line.customization.size.trim(),
        filling: line.customization.filling.trim(),
        greeting: line.customization.greeting.trim(),
        accessories: line.customization.accessories.trim(),
      },
    };
  });
}

async function refreshMemberBalance(): Promise<void> {
  if (!member.value) {
    return;
  }
  try {
    member.value = await staffQuickOrderService.lookupMember(member.value.mobile);
  } catch (error) {
    if (httpStatusOf(error) === 401) {
      // 开单已成功，先保住回执；不立即清空页面，等下一次操作再要求重新登录。
      ElMessage.warning("登录已过期，请重新登录；本次回执仍可复制");
      return;
    }
    ElMessage.warning(
      readErrorMessage(error, "开单成功，但会员余额刷新失败，请重新查询会员"),
    );
  }
}

async function submitOrder(): Promise<void> {
  if (submitting.value) {
    return;
  }
  submitError.value = "";
  if (!member.value) {
    submitError.value = "请先查询会员";
    ElMessage.warning(submitError.value);
    return;
  }
  if (cart.value.length === 0) {
    submitError.value = "请先添加商品";
    ElMessage.warning(submitError.value);
    return;
  }
  if (!expectTime.value) {
    submitError.value = "请选择预约/自提时间";
    ElMessage.warning(submitError.value);
    return;
  }

  submitting.value = true;
  try {
    if (!(await confirmCustomization())) {
      return;
    }
    result.value = null;
    const payload: QuickOrderPayload = {
      requestId: ensureRequestId(),
      mode: mode.value,
      phone: member.value.mobile,
      items: buildItems(),
      fulfillmentMethod: "pickup",
      expectTime: expectTime.value,
      remark: remark.value.trim(),
    };
    const created = await staffQuickOrderService.create(payload);
    result.value = created;
    resultTotalFen.value = totalFen.value;
    cart.value = [];
    pendingRequestId = "";
    ElMessage.success(
      mode.value === "stored_value_direct" ? "开单并扣款成功" : "订单已创建，请分享给客户支付",
    );
    await refreshMemberBalance();
  } catch (error) {
    if (httpStatusOf(error) === 401) {
      expireSession();
      return;
    }
    // 仅 400 明确代表后端未建单，可换新 requestId 重新发起；其余状态保留以便幂等回放。
    if (httpStatusOf(error) === 400) {
      pendingRequestId = "";
    }
    submitError.value = readErrorMessage(error, "开单失败");
  } finally {
    submitting.value = false;
  }
}

function fallbackCopy(text: string): boolean {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "readonly");
  textarea.style.position = "fixed";
  textarea.style.top = "-1000px";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch {
    // 旧浏览器不支持复制命令时按失败处理，由界面提示手动复制。
    copied = false;
  }
  document.body.removeChild(textarea);
  return copied;
}

async function copyText(text: string, label: string): Promise<void> {
  if (!text) {
    return;
  }
  try {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      await navigator.clipboard.writeText(text);
    } else if (!fallbackCopy(text)) {
      ElMessage.error("复制失败，请长按手动复制");
      return;
    }
    ElMessage.success(`${label}已复制`);
  } catch {
    ElMessage.error("复制失败，请长按手动复制");
  }
}

onMounted(() => {
  void bootstrap();
});
</script>

<template>
  <section class="quick-order-page" data-testid="quick-order-page">
    <div v-if="booting" class="quick-order-page__boot" v-loading="true" />

    <!-- 未登录：店员独立登录卡，不依赖 admin 会话 -->
    <el-card v-else-if="!principal" shadow="never" class="quick-order-page__login">
      <div class="quick-order-page__login-header">
        <h1>店员快捷开单</h1>
        <p>使用店员手机号与 PIN 登录，登录后可代客查询会员、开单并扣储值。</p>
      </div>

      <el-form label-position="top" class="quick-order-page__login-form" @submit.prevent="submitLogin">
        <el-form-item label="手机号">
          <el-input
            v-model="loginPhone"
            type="tel"
            inputmode="tel"
            maxlength="11"
            clearable
            autocomplete="username"
            placeholder="请输入11位手机号"
            size="large"
            data-testid="staff-login-phone"
            @keyup.enter="submitLogin"
          />
        </el-form-item>
        <el-form-item label="PIN 码">
          <el-input
            v-model="loginPin"
            type="password"
            show-password
            autocomplete="current-password"
            placeholder="请输入 PIN 码"
            size="large"
            data-testid="staff-login-pin"
            @keyup.enter="submitLogin"
          />
        </el-form-item>

        <el-alert
          v-if="loginError"
          :title="loginError"
          type="error"
          show-icon
          :closable="false"
          class="quick-order-page__alert"
          data-testid="staff-login-error"
        />

        <el-button
          type="primary"
          size="large"
          class="quick-order-page__login-submit"
          :loading="loginLoading"
          data-testid="staff-login-submit"
          @click="submitLogin"
        >
          登录
        </el-button>
      </el-form>
    </el-card>

    <!-- 已登录 -->
    <template v-else>
      <el-card shadow="never" class="quick-order-page__card">
        <div class="quick-order-page__staff">
          <div class="quick-order-page__staff-info">
            <strong>{{ principal.name }}</strong>
            <el-tag size="small" effect="plain" type="warning">{{ roleLabel(principal.role) }}</el-tag>
          </div>
          <el-button text type="danger" size="small" data-testid="staff-logout" @click="logout">
            退出登录
          </el-button>
        </div>
      </el-card>

      <!-- 会员查询 -->
      <el-card shadow="never" class="quick-order-page__card">
        <template #header>
          <div class="quick-order-page__card-title">
            <span>会员</span>
            <span v-if="member" class="quick-order-page__muted">已查询</span>
          </div>
        </template>

        <div class="quick-order-page__search-row">
          <el-input
            v-model="memberPhone"
            type="tel"
            inputmode="tel"
            maxlength="11"
            clearable
            placeholder="会员手机号"
            size="large"
            data-testid="quick-order-member-phone"
            @keyup.enter="lookupMember"
          />
          <el-button
            type="primary"
            size="large"
            :loading="memberLoading"
            data-testid="quick-order-member-lookup"
            @click="lookupMember"
          >
            查询
          </el-button>
        </div>

        <el-alert
          v-if="memberError"
          :title="memberError"
          type="error"
          show-icon
          :closable="false"
          class="quick-order-page__alert"
          data-testid="quick-order-member-error"
        />

        <div v-if="member" class="quick-order-page__member" data-testid="quick-order-member-info">
          <div class="quick-order-page__member-head">
            <div>
              <strong>{{ member.displayName || "未命名会员" }}</strong>
              <span class="quick-order-page__muted">{{ member.mobile }}</span>
            </div>
            <el-tag v-if="member.isMember" type="success" size="small" effect="light">储值会员</el-tag>
            <el-tag v-else type="info" size="small" effect="light">非储值会员</el-tag>
          </div>

          <div class="quick-order-page__metrics">
            <div class="quick-order-page__metric">
              <span>储值总额</span>
              <b>¥{{ fenToYuan(member.storedValueFen) }}</b>
            </div>
            <div class="quick-order-page__metric">
              <span>本金</span>
              <b>¥{{ fenToYuan(member.principalFen) }}</b>
            </div>
            <div class="quick-order-page__metric">
              <span>赠送金</span>
              <b>¥{{ fenToYuan(member.bonusFen) }}</b>
            </div>
            <div class="quick-order-page__metric">
              <span>积分</span>
              <b>{{ member.points }}</b>
            </div>
          </div>

          <p v-if="member.cardAlias" class="quick-order-page__muted">卡号：{{ member.cardAlias }}</p>
          <p v-if="!member.isMember" class="quick-order-page__hint">
            该客户尚未开通储值卡，储值直扣可能失败，建议改用微信分享待付。
          </p>

          <div class="quick-order-page__history">
            <div class="quick-order-page__history-title">最近订单</div>
            <ul v-if="recentOrders.length > 0" class="quick-order-page__history-list">
              <li v-for="order in recentOrders" :key="order.orderNo">
                <div class="quick-order-page__history-row">
                  <span class="quick-order-page__history-no">{{ order.orderNo || "-" }}</span>
                  <el-tag size="small" effect="plain">{{ historyStatusText(order.status) }}</el-tag>
                </div>
                <div class="quick-order-page__history-meta">
                  {{ order.productTitles || "-" }} · x{{ order.totalQuantity }} ·
                  ¥{{ fenToYuan(order.amountFen) }}
                </div>
                <div class="quick-order-page__history-meta">
                  {{ order.payTime || order.createdAt || "-" }}
                </div>
              </li>
            </ul>
            <p v-else class="quick-order-page__muted">暂无历史订单</p>
          </div>
        </div>
      </el-card>

      <!-- 商品搜索 -->
      <el-card shadow="never" class="quick-order-page__card">
        <template #header>
          <div class="quick-order-page__card-title">
            <span>商品</span>
            <span class="quick-order-page__muted">当前 {{ products.length }} 款</span>
          </div>
        </template>

        <div class="quick-order-page__search-row">
          <el-input
            v-model="productKeyword"
            clearable
            placeholder="商品名称关键词"
            size="large"
            data-testid="quick-order-product-search"
            @keyup.enter="searchProducts"
          />
          <el-button
            type="primary"
            size="large"
            :loading="productLoading"
            data-testid="quick-order-product-search-submit"
            @click="searchProducts"
          >
            搜索
          </el-button>
        </div>

        <el-alert
          v-if="productError"
          :title="productError"
          type="error"
          show-icon
          :closable="false"
          class="quick-order-page__alert"
          data-testid="quick-order-product-error"
        />

        <ul v-loading="productLoading" class="quick-order-page__products">
          <li v-for="product in products" :key="product.productId" class="quick-order-page__product">
            <img
              v-if="product.imageUrl"
              :src="product.imageUrl"
              :alt="product.title"
              class="quick-order-page__product-image"
            />
            <div class="quick-order-page__product-main">
              <div class="quick-order-page__product-title">{{ product.title }}</div>
              <div class="quick-order-page__product-meta">
                <span class="quick-order-page__price">¥{{ fenToYuan(product.priceFen) }}</span>
                <span class="quick-order-page__muted">库存 {{ product.stock }}</span>
                <el-tag v-if="!product.isPurchasable || product.stock <= 0" type="info" size="small">
                  不可售
                </el-tag>
              </div>
            </div>
            <el-button
              type="primary"
              plain
              size="small"
              class="quick-order-page__product-add"
              :disabled="!canAdd(product)"
              :data-testid="`quick-order-add-${product.productId}`"
              @click="addToCart(product)"
            >
              加入
            </el-button>
          </li>
          <li v-if="!productLoading && products.length === 0" class="quick-order-page__muted">
            没有匹配的商品
          </li>
        </ul>
      </el-card>

      <!-- 购物车 -->
      <el-card shadow="never" class="quick-order-page__card">
        <template #header>
          <div class="quick-order-page__card-title">
            <span>购物车</span>
            <span class="quick-order-page__muted">{{ cartCount }} 件</span>
          </div>
        </template>

        <p v-if="cart.length === 0" class="quick-order-page__muted">请从上方商品列表加入商品</p>

        <ul v-else class="quick-order-page__cart">
          <li v-for="(line, index) in cart" :key="line.product.productId" class="quick-order-page__cart-line">
            <div class="quick-order-page__cart-head">
              <div class="quick-order-page__cart-title">{{ line.product.title }}</div>
              <el-button text type="danger" size="small" @click="removeLine(index)">删除</el-button>
            </div>
            <div class="quick-order-page__cart-meta">
              <span>¥{{ fenToYuan(line.product.priceFen) }} / 件</span>
              <span class="quick-order-page__muted">库存 {{ line.product.stock }}</span>
            </div>
            <div class="quick-order-page__cart-actions">
              <el-button
                size="small"
                class="quick-order-page__qty-button"
                :disabled="line.quantity <= 1"
                @click="decreaseQuantity(line)"
              >
                −
              </el-button>
              <span class="quick-order-page__qty">{{ line.quantity }}</span>
              <el-button
                size="small"
                class="quick-order-page__qty-button"
                :disabled="line.quantity >= growableMax(line)"
                @click="increaseQuantity(line)"
              >
                +
              </el-button>
              <span class="quick-order-page__line-total">
                ¥{{ fenToYuan(line.product.priceFen * line.quantity) }}
              </span>
            </div>

            <div class="quick-order-page__cake-row">
              <el-checkbox
                v-model="line.isCakeOrder"
                class="quick-order-page__cake-toggle"
                :data-testid="`quick-order-cake-toggle-${line.product.productId}`"
              >
                按定制蛋糕处理（需提前 4 小时）
              </el-checkbox>
              <p
                v-if="looksLikeCake(line.product.title) && !line.isCakeOrder"
                class="quick-order-page__cake-hint"
              >
                疑似蛋糕，如为定制请勾选
              </p>
            </div>

            <div v-if="line.isCakeOrder" class="quick-order-page__custom">
              <label class="quick-order-page__field">
                <span>尺寸</span>
                <el-input
                  v-model="line.customization.size"
                  placeholder="如 6寸 / 8寸"
                  :data-testid="`quick-order-custom-size-${line.product.productId}`"
                />
              </label>
              <label class="quick-order-page__field">
                <span>夹心</span>
                <el-input
                  v-model="line.customization.filling"
                  placeholder="如 草莓 / 芒果"
                  :data-testid="`quick-order-custom-filling-${line.product.productId}`"
                />
              </label>
              <label class="quick-order-page__field">
                <span>祝福语</span>
                <el-input
                  v-model="line.customization.greeting"
                  placeholder="若无请填“无”"
                  :data-testid="`quick-order-custom-greeting-${line.product.productId}`"
                />
              </label>
              <label class="quick-order-page__field">
                <span>配件</span>
                <el-input
                  v-model="line.customization.accessories"
                  placeholder="如 餐具 6 份、蜡烛 1 包"
                  :data-testid="`quick-order-custom-accessories-${line.product.productId}`"
                />
              </label>
              <p class="quick-order-page__hint">定制信息可留空，但提交前会提示；后台会强制校验缺项。</p>
            </div>
          </li>
        </ul>
      </el-card>

      <!-- 开单设置 -->
      <el-card shadow="never" class="quick-order-page__card">
        <template #header>
          <div class="quick-order-page__card-title">
            <span>开单设置</span>
            <span class="quick-order-page__muted">到店自提</span>
          </div>
        </template>

        <div class="quick-order-page__field">
          <span>收款方式</span>
          <el-radio-group v-model="mode" class="quick-order-page__modes" data-testid="quick-order-mode">
            <el-radio value="stored_value_direct">储值直扣</el-radio>
            <el-radio value="wechat_share_card">微信分享待付</el-radio>
          </el-radio-group>
          <p class="quick-order-page__hint">
            <template v-if="mode === 'stored_value_direct'">
              从会员储值余额直接扣款，开单即完成收款。
            </template>
            <template v-else>
              只创建待支付订单，把分享路径/文案发给客户本人，由客户在小程序自行支付（不做代付）。
            </template>
          </p>
        </div>

        <div class="quick-order-page__field">
          <span>预约/自提时间</span>
          <div class="quick-order-page__datetime" data-testid="quick-order-expect-time">
            <el-date-picker
              v-model="expectTime"
              type="datetime"
              value-format="YYYY-MM-DD HH:mm"
              format="YYYY-MM-DD HH:mm"
              placeholder="选择预约/自提时间"
              :clearable="false"
            />
          </div>
          <p v-if="hasCakeLine" class="quick-order-page__hint">
            含定制蛋糕，预约时间需满足门店最小提前量（当前后端默认至少 4 小时）。
          </p>
        </div>

        <div class="quick-order-page__field">
          <span>备注</span>
          <el-input
            v-model="remark"
            type="textarea"
            :rows="2"
            maxlength="120"
            show-word-limit
            placeholder="选填，如门店开单、顾客自提说明"
            data-testid="quick-order-remark"
          />
        </div>

        <div v-if="cart.length > 0" class="quick-order-page__summary">
          <div>
            <div class="quick-order-page__muted">合计</div>
            <div class="quick-order-page__total">¥{{ fenToYuan(totalFen) }}</div>
          </div>
          <div v-if="member" class="quick-order-page__balance">
            <template v-if="mode === 'stored_value_direct'">
              <div class="quick-order-page__muted">扣款后剩余余额</div>
              <div
                class="quick-order-page__balance-value"
                :class="{ 'quick-order-page__balance-value--danger': balanceInsufficient }"
              >
                ¥{{ fenToYuan(remainingBalanceFen) }}
              </div>
            </template>
            <template v-else>
              <div class="quick-order-page__muted">待客户支付</div>
              <div class="quick-order-page__balance-value">¥{{ fenToYuan(totalFen) }}</div>
            </template>
          </div>
        </div>

        <el-alert
          v-if="balanceInsufficient"
          title="储值余额不足，提交后会被后端拒绝；请改用微信分享待付或先充值。"
          type="warning"
          show-icon
          :closable="false"
          class="quick-order-page__alert"
          data-testid="quick-order-balance-warning"
        />

        <el-alert
          v-if="submitError"
          :title="submitError"
          type="error"
          show-icon
          :closable="false"
          class="quick-order-page__alert"
          data-testid="quick-order-error"
        />

        <el-button
          type="primary"
          size="large"
          class="quick-order-page__submit"
          :loading="submitting"
          :disabled="submitting || cart.length === 0"
          data-testid="quick-order-submit"
          @click="submitOrder"
        >
          {{ mode === "stored_value_direct" ? "开单并扣款" : "创建待支付订单" }}
        </el-button>
      </el-card>

      <!-- 开单回执 -->
      <el-card v-if="result" shadow="never" class="quick-order-page__card" data-testid="quick-order-result">
        <template #header>
          <div class="quick-order-page__card-title">
            <span>开单成功</span>
            <el-tag size="small" type="success" effect="light">{{ result.orderId }}</el-tag>
          </div>
        </template>

        <div class="quick-order-page__result-meta">
          <span>订单状态：{{ result.status || "-" }}</span>
          <span>支付状态：{{ result.paymentStatus || "-" }}</span>
          <span v-if="resultTotalFen > 0">订单金额：¥{{ fenToYuan(resultTotalFen) }}</span>
          <span v-if="typeof result.balanceFen === 'number'">
            扣款后余额：¥{{ fenToYuan(result.balanceFen) }}
          </span>
        </div>

        <div class="quick-order-page__receipt-head">
          <span>回执</span>
          <el-button size="small" text type="primary" @click="copyText(result.receiptText, '回执')">
            复制回执
          </el-button>
        </div>
        <pre class="quick-order-page__receipt" data-testid="quick-order-receipt">{{ result.receiptText }}</pre>

        <template v-if="result.sharePath">
          <p class="quick-order-page__hint">
            分享给客户本人支付：请把下方路径/文案发给客户，由客户在小程序内完成支付，门店不代付。
          </p>
          <div class="quick-order-page__share-block">
            <div class="quick-order-page__receipt-head">
              <span>分享路径</span>
              <el-button size="small" text type="primary" @click="copyText(result.sharePath || '', '分享路径')">
                复制
              </el-button>
            </div>
            <code class="quick-order-page__share-path" data-testid="quick-order-share-path">
              {{ result.sharePath }}
            </code>
          </div>
          <div v-if="result.shareText" class="quick-order-page__share-block">
            <div class="quick-order-page__receipt-head">
              <span>分享文案</span>
              <el-button size="small" text type="primary" @click="copyText(result.shareText || '', '分享文案')">
                复制
              </el-button>
            </div>
            <p class="quick-order-page__share-text">{{ result.shareText }}</p>
          </div>
        </template>
      </el-card>
    </template>
  </section>
</template>

<style scoped>
.quick-order-page {
  height: 100vh;
  height: 100dvh;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  width: 100%;
  max-width: 680px;
  margin: 0 auto;
}

/* 固定高度的滚动容器里禁止卡片收缩，否则内容会被后一张卡片覆盖。 */
.quick-order-page > * {
  flex: none;
}

.quick-order-page__boot {
  min-height: 240px;
}

.quick-order-page__login {
  margin: auto 0;
  border-radius: 16px;
}

.quick-order-page__login-header h1 {
  margin: 0;
  font-size: 22px;
}

.quick-order-page__login-header p {
  margin: 8px 0 0;
  color: var(--yx-text-muted);
  font-size: 13px;
  line-height: 1.6;
}

.quick-order-page__login-form {
  margin-top: 16px;
}

.quick-order-page__login-submit {
  width: 100%;
  min-height: 46px;
}

.quick-order-page__card {
  border-radius: 14px;
}

.quick-order-page__card :deep(.el-card__header) {
  padding: 12px 16px;
}

.quick-order-page__card :deep(.el-card__body) {
  padding: 12px 16px;
}

.quick-order-page__staff {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.quick-order-page__staff-info {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.quick-order-page__card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-weight: 600;
}

.quick-order-page__muted {
  color: var(--yx-text-muted);
  font-size: 12px;
  font-weight: 400;
}

.quick-order-page__hint {
  margin: 6px 0 0;
  color: var(--yx-text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.quick-order-page__alert {
  margin-top: 10px;
}

.quick-order-page__search-row {
  display: flex;
  gap: 8px;
  align-items: stretch;
}

.quick-order-page__search-row :deep(.el-input) {
  flex: 1;
  min-width: 0;
}

.quick-order-page__search-row :deep(.el-button) {
  flex-shrink: 0;
  min-height: 40px;
}

.quick-order-page__member {
  margin-top: 14px;
  display: grid;
  gap: 10px;
}

.quick-order-page__member-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.quick-order-page__member-head strong {
  margin-right: 8px;
}

.quick-order-page__metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.quick-order-page__metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  border-radius: 10px;
  background: var(--yx-bg);
}

.quick-order-page__metric span {
  color: var(--yx-text-muted);
  font-size: 12px;
}

.quick-order-page__metric b {
  font-size: 16px;
  font-variant-numeric: tabular-nums;
}

.quick-order-page__history {
  border-top: 1px solid var(--yx-border);
  padding-top: 10px;
}

.quick-order-page__history-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
}

.quick-order-page__history-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 8px;
}

.quick-order-page__history-list li {
  padding: 8px 10px;
  border-radius: 10px;
  background: var(--yx-bg);
}

.quick-order-page__history-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.quick-order-page__history-no {
  font-size: 12px;
  font-family: var(--yx-font-mono);
  word-break: break-all;
}

.quick-order-page__history-meta {
  margin-top: 2px;
  color: var(--yx-text-muted);
  font-size: 12px;
  line-height: 1.5;
  word-break: break-word;
}

.quick-order-page__products {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: grid;
  gap: 8px;
  min-height: 48px;
}

.quick-order-page__product {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border-radius: 12px;
  background: var(--yx-bg);
}

.quick-order-page__product-image {
  width: 48px;
  height: 48px;
  border-radius: 8px;
  object-fit: cover;
  flex-shrink: 0;
}

.quick-order-page__product-main {
  flex: 1;
  min-width: 0;
}

.quick-order-page__product-title {
  font-size: 14px;
  line-height: 1.4;
  word-break: break-word;
}

.quick-order-page__product-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 4px;
}

.quick-order-page__price {
  color: var(--yx-brand);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.quick-order-page__product-add {
  flex-shrink: 0;
  min-height: 32px;
}

.quick-order-page__cart {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 10px;
}

.quick-order-page__cart-line {
  padding: 10px;
  border-radius: 12px;
  background: var(--yx-bg);
}

.quick-order-page__cart-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.quick-order-page__cart-title {
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  word-break: break-word;
}

.quick-order-page__cart-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 2px;
  font-size: 12px;
  color: var(--yx-text-muted);
}

.quick-order-page__cart-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.quick-order-page__qty-button {
  min-width: 40px;
  min-height: 36px;
  font-size: 18px;
}

.quick-order-page__qty {
  min-width: 28px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.quick-order-page__line-total {
  margin-left: auto;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.quick-order-page__cake-row {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--yx-border);
}

.quick-order-page__cake-toggle {
  height: auto;
  min-height: 32px;
}

.quick-order-page__cake-toggle :deep(.el-checkbox__label) {
  font-size: 13px;
  line-height: 1.5;
  white-space: normal;
}

.quick-order-page__cake-hint {
  margin: 2px 0 0 24px;
  color: var(--el-color-warning);
  font-size: 12px;
  line-height: 1.5;
}

.quick-order-page__custom {
  display: grid;
  gap: 8px;
  margin-top: 6px;
  padding-top: 8px;
  border-top: 1px dashed var(--yx-border);
}

.quick-order-page__field {
  display: grid;
  gap: 6px;
  margin-bottom: 12px;
}

.quick-order-page__field:last-child {
  margin-bottom: 0;
}

.quick-order-page__field > span {
  font-size: 13px;
  font-weight: 600;
}

.quick-order-page__modes {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.quick-order-page .quick-order-page__datetime {
  width: 100%;
}

.quick-order-page__datetime :deep(.el-date-editor) {
  width: 100%;
}

.quick-order-page__summary {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin: 4px 0 12px;
  padding: 12px;
  border-radius: 12px;
  background: var(--yx-bg);
}

.quick-order-page__total {
  font-size: 22px;
  font-weight: 700;
  color: var(--yx-brand);
  font-variant-numeric: tabular-nums;
}

.quick-order-page__balance {
  text-align: right;
}

.quick-order-page__balance-value {
  font-size: 16px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.quick-order-page__balance-value--danger {
  color: var(--el-color-danger);
}

.quick-order-page__submit {
  width: 100%;
  min-height: 48px;
  font-size: 16px;
}

.quick-order-page__result-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  font-size: 12px;
  color: var(--yx-text-muted);
  margin-bottom: 12px;
}

.quick-order-page__receipt-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
}

.quick-order-page__receipt {
  margin: 6px 0 12px;
  padding: 12px;
  border-radius: 10px;
  background: var(--yx-bg);
  font-family: var(--yx-font-mono);
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.quick-order-page__share-block {
  margin-top: 10px;
}

.quick-order-page__share-path {
  display: block;
  margin-top: 6px;
  padding: 10px;
  border-radius: 10px;
  background: var(--yx-bg);
  font-family: var(--yx-font-mono);
  font-size: 12px;
  word-break: break-all;
}

.quick-order-page__share-text {
  margin: 6px 0 0;
  padding: 10px;
  border-radius: 10px;
  background: var(--yx-bg);
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
}

@media (min-width: 768px) {
  .quick-order-page {
    padding: 24px 16px;
  }

  .quick-order-page__metrics {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
</style>
