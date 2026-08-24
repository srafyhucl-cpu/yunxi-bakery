<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { Check, DocumentChecked, Plus, Refresh, Remove } from "@element-plus/icons-vue";

import { SHOP_PAGE_OPTIONS, type ShopPageId } from "@/constants/shopPages";
import { assetsService } from "@/services/assets";
import { productsService } from "@/services/products";
import { shopPagesService } from "@/services/shopPages";
import type { ProductListItem } from "@/types/product";
import type { EditableBlockSummary, ShopPageBlock, ShopPageConfig } from "@/types/shopPage";

const loading = ref(false);
const saving = ref(false);
const publishing = ref(false);
const selectedPageId = ref<ShopPageId>("home");
const selectedBlockId = ref("");
const draft = ref<ShopPageConfig | null>(null);
const published = ref<ShopPageConfig | null>(null);
const productPickerVisible = ref(false);
const productPickerLoading = ref(false);
const productPickerKeyword = ref("");
const productPickerItems = ref<ProductListItem[]>([]);
const productPickerPage = ref(1);
const productPickerTotal = ref(0);
const productPickerPageSize = ref(30);
const productTitleByIdentity = ref<Record<string, string>>({});
const heroUploading = ref(false);

const blockLabels: Record<string, string> = {
  searchBar: "搜索入口",
  heroCarousel: "首页轮播",
  noticeBar: "公告条",
  categoryGrid: "分类入口",
  quickLinks: "快捷入口",
  membershipBanner: "会员横幅",
  noticeList: "订购须知",
  productShelf: "商品货架",
  memberSummary: "会员摘要",
  serviceGrid: "服务入口",
  richText: "长说明",
};

const blockSummaries = computed<EditableBlockSummary[]>(() =>
  (draft.value?.blocks ?? []).map((block) => ({
    id: block.id,
    type: block.type,
    label: blockLabels[block.type] ?? block.type,
  })),
);

const selectedBlock = computed<ShopPageBlock | null>(() => {
  return draft.value?.blocks.find((block) => block.id === selectedBlockId.value) ?? null;
});

const selectedBlockPropsText = computed({
  get() {
    if (!selectedBlock.value) return "";
    return JSON.stringify(selectedBlock.value.props, null, 2);
  },
  set(value: string) {
    if (!selectedBlock.value) return;
    try {
      selectedBlock.value.props = JSON.parse(value) as Record<string, unknown>;
    } catch {
      // 输入中的临时非法 JSON 不立即打断编辑，保存前会校验。
    }
  },
});

const enabledBlocks = computed(() => draft.value?.blocks.filter((block) => block.enabled) ?? []);

const selectedProps = computed<Record<string, unknown>>(() => {
  if (!selectedBlock.value) return {};
  if (!selectedBlock.value.props) {
    selectedBlock.value.props = {};
  }
  return selectedBlock.value.props;
});

function clonePage(page: ShopPageConfig): ShopPageConfig {
  return JSON.parse(JSON.stringify(page)) as ShopPageConfig;
}

function selectFirstBlock() {
  selectedBlockId.value = draft.value?.blocks[0]?.id ?? "";
}

async function loadPage() {
  loading.value = true;
  try {
    const payload = await shopPagesService.getPage(selectedPageId.value);
    draft.value = clonePage(payload.draft);
    published.value = clonePage(payload.published);
    selectFirstBlock();
    await hydrateSelectedShelfProductTitles();
  } finally {
    loading.value = false;
  }
}

function moveBlock(index: number, direction: -1 | 1) {
  if (!draft.value) return;
  const targetIndex = index + direction;
  if (targetIndex < 0 || targetIndex >= draft.value.blocks.length) return;
  const nextBlocks = [...draft.value.blocks];
  const [current] = nextBlocks.splice(index, 1);
  nextBlocks.splice(targetIndex, 0, current);
  draft.value.blocks = nextBlocks;
}

function getStringProp(key: string): string {
  const value = selectedProps.value[key];
  return typeof value === "string" ? value : "";
}

function setStringProp(key: string, value: string) {
  selectedProps.value[key] = value;
}

function getNumberProp(key: string): number {
  const value = selectedProps.value[key];
  return typeof value === "number" ? value : 0;
}

function setNumberProp(key: string, value: number | undefined) {
  selectedProps.value[key] = Number(value ?? 0);
}

function getStringListProp(key: string): string {
  const value = selectedProps.value[key];
  if (!Array.isArray(value)) return "";
  return value.map((item) => String(item)).join("\n");
}

function setStringListProp(key: string, value: string) {
  selectedProps.value[key] = value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function getStringArrayProp(key: string): string[] {
  const value = selectedProps.value[key];
  if (!Array.isArray(value)) {
    selectedProps.value[key] = [];
    return selectedProps.value[key] as string[];
  }
  const normalized = value.map((item) => String(item)).filter(Boolean);
  selectedProps.value[key] = normalized;
  return normalized;
}

function getObjectArrayProp(key: string): Record<string, unknown>[] {
  const value = selectedProps.value[key];
  if (!Array.isArray(value)) {
    selectedProps.value[key] = [];
    return selectedProps.value[key] as Record<string, unknown>[];
  }
  return value.filter((item): item is Record<string, unknown> => {
    return Boolean(item && typeof item === "object" && !Array.isArray(item));
  });
}

function getItemStringListProp(item: Record<string, unknown>, key: string): string {
  const value = item[key];
  if (!Array.isArray(value)) return "";
  return value.map((entry) => String(entry)).join("\n");
}

function setItemStringListProp(item: Record<string, unknown>, key: string, value: string) {
  item[key] = value
    .split(/\r?\n|,/)
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function addHeroItem() {
  getObjectArrayProp("items").push({
    id: `hero-${Date.now()}`,
    title: "新轮播",
    imageUrl: "",
    subtitle: "",
    eyebrow: "",
    badges: ["当日现做", "精选奶油", "生日礼赠"],
    linkType: "none",
    linkTarget: "",
  });
}

function removeHeroItem(index: number) {
  getObjectArrayProp("items").splice(index, 1);
}

async function uploadHeroImages(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files ?? []);
  if (!files.length) return;
  heroUploading.value = true;
  try {
    for (const file of files) {
      const imageUrl = await assetsService.uploadDecorationImage(file);
      getObjectArrayProp("items").push({
        id: `hero-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        title: file.name.replace(/\.[^.]+$/, "") || "轮播图",
        imageUrl,
        subtitle: "",
        eyebrow: "",
        badges: ["主推", "新品", "礼赠"],
        linkType: "none",
        linkTarget: "",
      });
    }
    ElMessage.success(`已上传 ${files.length} 张轮播图`);
  } finally {
    heroUploading.value = false;
    input.value = "";
  }
}

function addNoticeListItem() {
  getObjectArrayProp("items").push({
    id: `notice-${Date.now()}`,
    title: "订购须知",
    actionText: "点击查看",
    linkType: "none",
    linkTarget: "",
  });
}

function removeNoticeListItem(index: number) {
  getObjectArrayProp("items").splice(index, 1);
}

function addLinkItem() {
  getObjectArrayProp("items").push({
    id: `link-${Date.now()}`,
    title: "新入口",
    iconText: "",
    linkType: "page",
    linkTarget: "",
  });
}

function removeLinkItem(index: number) {
  getObjectArrayProp("items").splice(index, 1);
}

function getLinkType(item: Record<string, unknown>): string {
  return typeof item.linkType === "string" ? item.linkType : "none";
}

function setItemStringProp(item: Record<string, unknown>, key: string, value: string) {
  item[key] = value;
}

function getProductIdentity(product: ProductListItem): string {
  return product.youzanItemId || String(product.id);
}

function rememberShelfProducts(products: ProductListItem[]) {
  const nextMap = { ...productTitleByIdentity.value };
  for (const product of products) {
    const productId = getProductIdentity(product);
    if (productId) {
      nextMap[productId] = product.title || productId;
    }
  }
  productTitleByIdentity.value = nextMap;
}

function getProductDisplayTitle(productId: string): string {
  return productTitleByIdentity.value[productId] || productId;
}

function getHeroPreviewItem(block: ShopPageBlock): Record<string, unknown> {
  const items = block.props.items;
  if (!Array.isArray(items)) return {};
  const firstItem = items.find((item): item is Record<string, unknown> => {
    return Boolean(item && typeof item === "object" && !Array.isArray(item));
  });
  return firstItem ?? {};
}

function getHeroPreviewBadges(block: ShopPageBlock): string[] {
  const badges = getHeroPreviewItem(block).badges;
  if (!Array.isArray(badges)) return [];
  return badges.map((badge) => String(badge)).filter(Boolean).slice(0, 3);
}

function getMissingSelectedProductIds(): string[] {
  return getStringArrayProp("productIds").filter((productId) => !productTitleByIdentity.value[productId]);
}

async function hydrateSelectedShelfProductTitles() {
  if (selectedBlock.value?.type !== "productShelf") return;
  const missingProductIds = getMissingSelectedProductIds().slice(0, 20);
  if (!missingProductIds.length) return;
  const productResults = await Promise.all(
    missingProductIds.map(async (productId) => {
      const payload = await productsService.listProducts(1, productId, "1");
      return payload.items.find((product) => getProductIdentity(product) === productId);
    }),
  );
  rememberShelfProducts(productResults.filter((product): product is ProductListItem => Boolean(product)));
}

function isProductSelected(product: ProductListItem): boolean {
  return getStringArrayProp("productIds").includes(getProductIdentity(product));
}

function addProductToShelf(product: ProductListItem) {
  rememberShelfProducts([product]);
  const productIds = getStringArrayProp("productIds");
  const productId = getProductIdentity(product);
  if (!productIds.includes(productId)) {
    productIds.push(productId);
  }
}

function removeProductFromShelf(productId: string) {
  selectedProps.value.productIds = getStringArrayProp("productIds").filter((item) => item !== productId);
}

async function openProductPicker() {
  productPickerVisible.value = true;
  if (!productPickerItems.value.length) {
    await searchShelfProducts();
  }
}

async function loadShelfProducts(page = productPickerPage.value) {
  productPickerLoading.value = true;
  try {
    const payload = await productsService.listProducts(page, productPickerKeyword.value.trim(), "1");
    productPickerItems.value = payload.items;
    rememberShelfProducts(payload.items);
    productPickerPage.value = payload.page;
    productPickerTotal.value = payload.total;
    productPickerPageSize.value = payload.pageSize;
  } finally {
    productPickerLoading.value = false;
  }
}

async function searchShelfProducts() {
  productPickerPage.value = 1;
  await loadShelfProducts(1);
}

async function changeProductPickerPage(page: number) {
  await loadShelfProducts(page);
}

async function saveDraft() {
  if (!draft.value) return;
  saving.value = true;
  try {
    draft.value.pageId = selectedPageId.value;
    draft.value = await shopPagesService.saveDraft(selectedPageId.value, draft.value);
    ElMessage.success("装修草稿已保存");
  } finally {
    saving.value = false;
  }
}

async function publishPage() {
  publishing.value = true;
  try {
    const currentBlockId = selectedBlockId.value;
    published.value = await shopPagesService.publish(selectedPageId.value);
    draft.value = clonePage(published.value);
    selectedBlockId.value = draft.value.blocks.some((block) => block.id === currentBlockId)
      ? currentBlockId
      : draft.value.blocks[0]?.id ?? "";
    ElMessage.success("已发布到小程序");
  } finally {
    publishing.value = false;
  }
}

function getBlockTitle(block: ShopPageBlock): string {
  const props = block.props as Record<string, unknown>;
  return String(props.title || props.text || blockLabels[block.type] || block.type);
}

async function changePage(pageId: ShopPageId) {
  selectedPageId.value = pageId;
  selectedBlockId.value = "";
  productPickerVisible.value = false;
  await loadPage();
}

onMounted(loadPage);

watch(selectedBlockId, () => {
  void hydrateSelectedShelfProductTitles();
});
</script>

<template>
  <section class="decoration-page" v-loading="loading">
    <el-card shadow="never" class="decoration-page__card">
      <template #header>
        <div class="decoration-page__header">
          <div>
            <strong>店铺装修</strong>
            <p>第一版采用表单编辑 + 手机预览，发布后小程序读取同一份 JSON。</p>
          </div>
          <div class="decoration-page__actions">
            <div class="decoration-page__page-tabs" data-testid="decoration-page-select">
              <button
                v-for="page in SHOP_PAGE_OPTIONS"
                :key="page.value"
                type="button"
                class="decoration-page__page-tab"
                :class="{ 'is-active': selectedPageId === page.value }"
                :data-testid="`decoration-page-tab-${page.value}`"
                @click="changePage(page.value)"
              >
                <strong>{{ page.label }}</strong>
                <span>{{ page.description }}</span>
              </button>
            </div>
            <!-- 保留 el-select 结构给窄屏和已有检查兼容，主操作使用上方分段页签。 -->
            <el-select
              class="decoration-page__page-select"
              :model-value="selectedPageId"
              @update:model-value="changePage($event as ShopPageId)"
            >
              <el-option
                v-for="page in SHOP_PAGE_OPTIONS"
                :key="page.value"
                :label="page.label"
                :value="page.value"
              >
                <div class="decoration-page__page-option">
                  <strong>{{ page.label }}</strong>
                  <span>{{ page.description }}</span>
                </div>
              </el-option>
            </el-select>
            <el-button :icon="Refresh" data-testid="decoration-refresh" @click="loadPage">刷新</el-button>
            <el-button
              :icon="DocumentChecked"
              :loading="saving"
              data-testid="decoration-save-draft"
              @click="saveDraft"
            >
              保存草稿
            </el-button>
            <el-button
              type="primary"
              :icon="Check"
              :loading="publishing"
              data-testid="decoration-publish"
              @click="publishPage"
            >
              发布
            </el-button>
          </div>
        </div>
      </template>

      <div v-if="draft" class="decoration-page__layout">
        <aside class="decoration-page__blocks">
          <div class="decoration-page__panel-title">页面模块</div>
          <article
            v-for="(block, index) in draft.blocks"
            :key="block.id"
            class="decoration-page__block"
            :class="{ 'is-active': selectedBlockId === block.id }"
            :data-testid="`decoration-block-${block.id}`"
            :data-block-id="block.id"
            :data-block-type="block.type"
            @click="selectedBlockId = block.id"
          >
            <div>
              <strong>{{ blockLabels[block.type] || block.type }}</strong>
              <span>{{ block.id }}</span>
            </div>
            <div class="decoration-page__block-actions">
              <el-switch v-model="block.enabled" size="small" />
              <el-button text :disabled="index === 0" @click.stop="moveBlock(index, -1)">
                上移
              </el-button>
              <el-button
                text
                :disabled="index === draft.blocks.length - 1"
                @click.stop="moveBlock(index, 1)"
              >
                下移
              </el-button>
            </div>
          </article>
        </aside>

        <main class="decoration-page__preview-wrap">
          <div class="decoration-page__phone">
            <div class="decoration-page__phone-title">芸熙烘焙</div>
            <div class="decoration-page__phone-body">
              <section
                v-for="block in enabledBlocks"
                :key="block.id"
                class="decoration-page__preview-block"
              >
                <template v-if="block.type === 'searchBar'">
                  <div class="decoration-page__search">
                    {{ String(block.props.placeholder || "搜索商品") }}
                  </div>
                </template>
                <template v-else-if="block.type === 'heroCarousel'">
                  <div class="decoration-page__hero">
                    <img
                      v-if="getHeroPreviewItem(block).imageUrl"
                      :src="String(getHeroPreviewItem(block).imageUrl)"
                      alt=""
                    />
                    <div class="decoration-page__hero-copy">
                      <small>{{ String(getHeroPreviewItem(block).eyebrow || "YUNXI BAKE") }}</small>
                      <strong>{{ String(getHeroPreviewItem(block).title || getBlockTitle(block)) }}</strong>
                      <span>{{ String(getHeroPreviewItem(block).subtitle || "每日现制 / 手作奶油 / 礼赠场景") }}</span>
                      <div v-if="getHeroPreviewBadges(block).length" class="decoration-page__hero-badges">
                        <em v-for="badge in getHeroPreviewBadges(block)" :key="badge">{{ badge }}</em>
                      </div>
                    </div>
                  </div>
                </template>
                <template v-else-if="block.type === 'noticeBar'">
                  <div class="decoration-page__notice">{{ getBlockTitle(block) }}</div>
                </template>
                <template v-else-if="block.type === 'categoryGrid'">
                  <div class="decoration-page__category-grid">
                    <span
                      v-for="categoryId in ((block.props.categoryIds as string[]) || []).slice(0, 4)"
                      :key="categoryId"
                    >
                      {{ categoryId }}
                    </span>
                  </div>
                </template>
                <template v-else-if="block.type === 'quickLinks' || block.type === 'serviceGrid'">
                  <div class="decoration-page__quick-grid">
                    <strong v-if="block.props.title">{{ String(block.props.title) }}</strong>
                    <span
                      v-for="item in ((block.props.items as Record<string, unknown>[]) || []).slice(0, 4)"
                      :key="String(item.id || item.title)"
                    >
                      {{ String(item.title || item.iconText || "入口") }}
                    </span>
                  </div>
                </template>
                <template v-else-if="block.type === 'membershipBanner'">
                  <div class="decoration-page__member-banner">
                    <strong>{{ String(block.props.title || "会员权益") }}</strong>
                    <small>{{ String(block.props.subtitle || "") }}</small>
                    <em>{{ String(block.props.actionText || "查看") }}</em>
                  </div>
                </template>
                <template v-else-if="block.type === 'noticeList'">
                  <div class="decoration-page__notice-list">
                    <div
                      v-for="item in ((block.props.items as Record<string, unknown>[]) || []).slice(0, 3)"
                      :key="String(item.id || item.title)"
                    >
                      <span>{{ String(item.title || "订购须知") }}</span>
                      <small>{{ String(item.actionText || "查看") }}</small>
                    </div>
                  </div>
                </template>
                <template v-else-if="block.type === 'productShelf'">
                  <div class="decoration-page__shelf">
                    <strong>{{ getBlockTitle(block) }}</strong>
                    <small v-if="block.props.subtitle">{{ String(block.props.subtitle) }}</small>
                    <div class="decoration-page__product-row">
                      <span />
                      <span />
                    </div>
                  </div>
                </template>
                <template v-else-if="block.type === 'richText'">
                  <div class="decoration-page__rich-text">
                    <strong>{{ String(block.props.title || "说明") }}</strong>
                    <p
                      v-for="paragraph in ((block.props.paragraphs as string[]) || []).slice(0, 2)"
                      :key="paragraph"
                    >
                      {{ paragraph }}
                    </p>
                  </div>
                </template>
                <template v-else>
                  <div class="decoration-page__simple-block">
                    {{ getBlockTitle(block) }}
                  </div>
                </template>
              </section>
            </div>
          </div>
        </main>

        <aside class="decoration-page__editor">
          <div class="decoration-page__panel-title">模块配置</div>
          <el-empty v-if="!selectedBlock" description="请选择一个模块" />
          <template v-else>
            <el-form label-position="top">
              <el-form-item label="模块 ID">
                <el-input :model-value="selectedBlock.id" disabled />
              </el-form-item>
              <el-form-item label="模块类型">
                <el-input :model-value="blockLabels[selectedBlock.type] || selectedBlock.type" disabled />
              </el-form-item>
              <el-form-item label="启用">
                <el-switch v-model="selectedBlock.enabled" />
              </el-form-item>
              <template v-if="selectedBlock.type === 'searchBar'">
                <el-form-item label="占位文案">
                  <el-input
                    :model-value="getStringProp('placeholder')"
                    @update:model-value="setStringProp('placeholder', String($event))"
                  />
                </el-form-item>
              </template>

              <template v-else-if="selectedBlock.type === 'noticeBar'">
                <el-form-item label="公告内容">
                  <el-input
                    :model-value="getStringProp('text')"
                    type="textarea"
                    :rows="3"
                    @update:model-value="setStringProp('text', String($event))"
                  />
                </el-form-item>
              </template>

              <template v-else-if="selectedBlock.type === 'categoryGrid'">
                <el-form-item label="分类 ID">
                  <el-input
                    :model-value="getStringListProp('categoryIds')"
                    type="textarea"
                    :rows="6"
                    placeholder="一行一个分类 ID，例如 birthday-cake"
                    @update:model-value="setStringListProp('categoryIds', String($event))"
                  />
                </el-form-item>
              </template>

              <template v-else-if="selectedBlock.type === 'quickLinks' || selectedBlock.type === 'serviceGrid'">
                <el-form-item label="模块标题">
                  <el-input
                    :model-value="getStringProp('title')"
                    @update:model-value="setStringProp('title', String($event))"
                  />
                </el-form-item>
                <div class="decoration-page__field-header">
                  <span>入口条目</span>
                  <el-button text :icon="Plus" @click="addLinkItem">新增</el-button>
                </div>
                <article
                  v-for="(item, index) in getObjectArrayProp('items')"
                  :key="index"
                  class="decoration-page__item-editor"
                >
                  <div class="decoration-page__item-title">
                    <strong>入口 {{ index + 1 }}</strong>
                    <el-button text :icon="Remove" @click="removeLinkItem(index)">删除</el-button>
                  </div>
                  <el-form-item label="标题">
                    <el-input
                      :model-value="String(item.title || '')"
                      @update:model-value="setItemStringProp(item, 'title', String($event))"
                    />
                  </el-form-item>
                  <el-form-item label="图标文字">
                    <el-input
                      :model-value="String(item.iconText || '')"
                      maxlength="4"
                      placeholder="如 订 / 问 / 礼"
                      @update:model-value="setItemStringProp(item, 'iconText', String($event))"
                    />
                  </el-form-item>
                  <el-form-item label="跳转类型">
                    <el-select
                      :model-value="getLinkType(item)"
                      @update:model-value="setItemStringProp(item, 'linkType', String($event))"
                    >
                      <el-option label="不跳转" value="none" />
                      <el-option label="页面" value="page" />
                      <el-option label="商品" value="product" />
                      <el-option label="分类" value="category" />
                      <el-option label="客服" value="contact" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="跳转目标">
                    <el-input
                      :model-value="String(item.linkTarget || '')"
                      placeholder="如 orders / chat / birthday-cake"
                      @update:model-value="setItemStringProp(item, 'linkTarget', String($event))"
                    />
                  </el-form-item>
                </article>
              </template>

              <template v-else-if="selectedBlock.type === 'heroCarousel'">
                <div class="decoration-page__field-header">
                  <span>轮播图</span>
                  <div class="decoration-page__hero-actions">
                    <label class="decoration-page__upload-button" data-testid="decoration-hero-upload">
                      <input
                        type="file"
                        accept="image/png,image/jpeg,image/webp"
                        multiple
                        :disabled="heroUploading"
                        @change="uploadHeroImages"
                      />
                      {{ heroUploading ? "上传中..." : "上传多张图片" }}
                    </label>
                    <el-button text :icon="Plus" @click="addHeroItem">手动新增</el-button>
                  </div>
                </div>
                <article
                  v-for="(item, index) in getObjectArrayProp('items')"
                  :key="index"
                  class="decoration-page__item-editor"
                >
                  <div class="decoration-page__item-title">
                    <strong>轮播 {{ index + 1 }}</strong>
                    <el-button text :icon="Remove" @click="removeHeroItem(index)">删除</el-button>
                  </div>
                  <div v-if="item.imageUrl" class="decoration-page__hero-thumb">
                    <img :src="String(item.imageUrl)" alt="" />
                    <span>{{ String(item.imageUrl) }}</span>
                  </div>
                  <el-form-item label="标题">
                    <el-input
                      :model-value="String(item.title || '')"
                      @update:model-value="setItemStringProp(item, 'title', String($event))"
                    />
                  </el-form-item>
                  <el-form-item label="副标题">
                    <el-input
                      :model-value="String(item.subtitle || '')"
                      @update:model-value="setItemStringProp(item, 'subtitle', String($event))"
                    />
                  </el-form-item>
                  <el-form-item label="角标">
                    <el-input
                      :model-value="String(item.eyebrow || '')"
                      placeholder="如 NEW / PROMOTION"
                      @update:model-value="setItemStringProp(item, 'eyebrow', String($event))"
                    />
                  </el-form-item>
                  <el-form-item label="卖点徽章">
                    <el-input
                      :model-value="getItemStringListProp(item, 'badges')"
                      type="textarea"
                      :rows="2"
                      placeholder="每行一个，如：当日现做 / 精选奶油 / 生日礼赠"
                      @update:model-value="setItemStringListProp(item, 'badges', String($event))"
                    />
                  </el-form-item>
                  <el-form-item label="图片地址">
                    <el-input
                      :model-value="String(item.imageUrl || '')"
                      placeholder="上传后自动填入，也可粘贴外部可访问图片地址"
                      @update:model-value="setItemStringProp(item, 'imageUrl', String($event))"
                    />
                  </el-form-item>
                  <el-form-item label="跳转类型">
                    <el-select
                      :model-value="getLinkType(item)"
                      @update:model-value="setItemStringProp(item, 'linkType', String($event))"
                    >
                      <el-option label="不跳转" value="none" />
                      <el-option label="商品" value="product" />
                      <el-option label="页面" value="page" />
                      <el-option label="分类" value="category" />
                      <el-option label="客服" value="contact" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="跳转目标">
                    <el-input
                      :model-value="String(item.linkTarget || '')"
                      @update:model-value="setItemStringProp(item, 'linkTarget', String($event))"
                    />
                  </el-form-item>
                </article>
              </template>

              <template v-else-if="selectedBlock.type === 'productShelf'">
                <el-form-item label="货架标题">
                  <el-input
                    :model-value="getStringProp('title')"
                    @update:model-value="setStringProp('title', String($event))"
                  />
                </el-form-item>
                <el-form-item label="副标题">
                  <el-input
                    :model-value="getStringProp('subtitle')"
                    @update:model-value="setStringProp('subtitle', String($event))"
                  />
                </el-form-item>
                <el-form-item label="商品来源">
                  <el-segmented
                    :model-value="getStringProp('source') || 'manual'"
                    :options="[
                      { label: '手动选择', value: 'manual' },
                      { label: '分类', value: 'category' },
                      { label: '主推', value: 'featured' },
                    ]"
                    @update:model-value="setStringProp('source', String($event))"
                  />
                </el-form-item>
                <el-form-item label="商品 ID">
                  <div
                    class="decoration-page__selected-products"
                    data-testid="decoration-selected-products"
                  >
                    <el-tag
                      v-for="productId in getStringArrayProp('productIds')"
                      :key="productId"
                      :data-testid="`decoration-selected-product-${productId}`"
                      closable
                      @close="removeProductFromShelf(productId)"
                    >
                      <span class="decoration-page__product-tag-title">
                        {{ getProductDisplayTitle(productId) }}
                      </span>
                      <small v-if="getProductDisplayTitle(productId) !== productId">
                        {{ productId }}
                      </small>
                    </el-tag>
                    <el-button
                      size="small"
                      :icon="Plus"
                      data-testid="decoration-open-product-picker"
                      @click="openProductPicker"
                    >
                      选择商品
                    </el-button>
                  </div>
                  <el-input
                    :model-value="getStringListProp('productIds')"
                    type="textarea"
                    :rows="5"
                    placeholder="一行一个商品 ID"
                    @update:model-value="setStringListProp('productIds', String($event))"
                  />
                </el-form-item>
                <el-form-item label="分类 ID">
                  <el-input
                    :model-value="getStringProp('categoryId')"
                    @update:model-value="setStringProp('categoryId', String($event))"
                  />
                </el-form-item>
              </template>

              <template v-else-if="selectedBlock.type === 'richText'">
                <el-form-item label="标题">
                  <el-input
                    :model-value="getStringProp('title')"
                    @update:model-value="setStringProp('title', String($event))"
                  />
                </el-form-item>
                <el-form-item label="段落">
                  <el-input
                    :model-value="getStringListProp('paragraphs')"
                    type="textarea"
                    :rows="8"
                    placeholder="一行一段"
                    @update:model-value="setStringListProp('paragraphs', String($event))"
                  />
                </el-form-item>
              </template>

              <template v-else-if="selectedBlock.type === 'membershipBanner'">
                <el-form-item label="标题">
                  <el-input
                    :model-value="getStringProp('title')"
                    @update:model-value="setStringProp('title', String($event))"
                  />
                </el-form-item>
                <el-form-item label="副标题">
                  <el-input
                    :model-value="getStringProp('subtitle')"
                    @update:model-value="setStringProp('subtitle', String($event))"
                  />
                </el-form-item>
                <el-form-item label="按钮文案">
                  <el-input
                    :model-value="getStringProp('actionText')"
                    @update:model-value="setStringProp('actionText', String($event))"
                  />
                </el-form-item>
              </template>

              <template v-else-if="selectedBlock.type === 'memberSummary'">
                <el-form-item label="问候语">
                  <el-input
                    :model-value="getStringProp('greeting')"
                    @update:model-value="setStringProp('greeting', String($event))"
                  />
                </el-form-item>
                <el-form-item label="昵称">
                  <el-input
                    :model-value="getStringProp('name')"
                    @update:model-value="setStringProp('name', String($event))"
                  />
                </el-form-item>
                <el-form-item label="会员等级">
                  <el-input
                    :model-value="getStringProp('levelText')"
                    @update:model-value="setStringProp('levelText', String($event))"
                  />
                </el-form-item>
                <el-form-item label="会员卡副标题">
                  <el-input
                    :model-value="getStringProp('cardSubtitle')"
                    @update:model-value="setStringProp('cardSubtitle', String($event))"
                  />
                </el-form-item>
                <el-form-item label="有效期文案">
                  <el-input
                    :model-value="getStringProp('cardValidity')"
                    @update:model-value="setStringProp('cardValidity', String($event))"
                  />
                </el-form-item>
                <div class="decoration-page__inline-fields">
                  <el-form-item label="余额(分)">
                    <el-input-number
                      :model-value="getNumberProp('balanceFen')"
                      :min="0"
                      @update:model-value="setNumberProp('balanceFen', $event ?? 0)"
                    />
                  </el-form-item>
                  <el-form-item label="积分">
                    <el-input-number
                      :model-value="getNumberProp('points')"
                      :min="0"
                      @update:model-value="setNumberProp('points', $event ?? 0)"
                    />
                  </el-form-item>
                  <el-form-item label="优惠券">
                    <el-input-number
                      :model-value="getNumberProp('coupons')"
                      :min="0"
                      @update:model-value="setNumberProp('coupons', $event ?? 0)"
                    />
                  </el-form-item>
                  <el-form-item label="权益卡">
                    <el-input-number
                      :model-value="getNumberProp('benefitCardCount')"
                      :min="0"
                      @update:model-value="setNumberProp('benefitCardCount', $event ?? 0)"
                    />
                  </el-form-item>
                </div>
              </template>

              <template v-else-if="selectedBlock.type === 'noticeList'">
                <div class="decoration-page__field-header">
                  <span>须知条目</span>
                  <el-button text :icon="Plus" @click="addNoticeListItem">新增</el-button>
                </div>
                <article
                  v-for="(item, index) in getObjectArrayProp('items')"
                  :key="index"
                  class="decoration-page__item-editor"
                >
                  <div class="decoration-page__item-title">
                    <strong>条目 {{ index + 1 }}</strong>
                    <el-button text :icon="Remove" @click="removeNoticeListItem(index)">删除</el-button>
                  </div>
                  <el-form-item label="标题">
                    <el-input
                      :model-value="String(item.title || '')"
                      @update:model-value="setItemStringProp(item, 'title', String($event))"
                    />
                  </el-form-item>
                  <el-form-item label="动作文案">
                    <el-input
                      :model-value="String(item.actionText || '')"
                      @update:model-value="setItemStringProp(item, 'actionText', String($event))"
                    />
                  </el-form-item>
                </article>
              </template>

              <el-collapse class="decoration-page__advanced">
                <el-collapse-item title="高级 JSON" name="json">
                  <el-input
                    v-model="selectedBlockPropsText"
                    type="textarea"
                    :rows="10"
                    spellcheck="false"
                  />
                </el-collapse-item>
              </el-collapse>
            </el-form>
          </template>
        </aside>
      </div>

      <el-empty v-else description="暂无装修配置" />
    </el-card>

    <el-dialog
      v-model="productPickerVisible"
      title="选择货架商品"
      width="760px"
      class="decoration-page__product-dialog"
      data-testid="decoration-product-picker-dialog"
    >
      <div class="decoration-page__picker-toolbar">
        <el-input
          v-model="productPickerKeyword"
          clearable
          placeholder="搜索商品名称"
          data-testid="decoration-product-picker-search"
          @keyup.enter="searchShelfProducts"
        />
        <el-button
          type="primary"
          :loading="productPickerLoading"
          data-testid="decoration-product-picker-search-button"
          @click="searchShelfProducts"
        >
          搜索
        </el-button>
      </div>

      <div class="decoration-page__picker-table-wrap" data-testid="decoration-product-picker-table">
        <div v-if="productPickerLoading" class="decoration-page__picker-loading">加载中</div>
        <table v-else class="decoration-page__picker-table">
          <thead>
            <tr>
              <th>商品</th>
              <th>编码</th>
              <th class="is-right">价格</th>
              <th class="is-center">库存</th>
              <th class="is-center">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!productPickerItems.length">
              <td colspan="5" class="decoration-page__picker-empty">暂无商品</td>
            </tr>
            <tr v-for="row in productPickerItems" :key="getProductIdentity(row)">
              <td>
                <div class="decoration-page__picker-product">
                  <strong>{{ row.title || "未命名商品" }}</strong>
                  <span>{{ getProductIdentity(row) }}</span>
                </div>
              </td>
              <td>{{ row.itemNo || "—" }}</td>
              <td class="is-right">
                <span v-if="row.priceFen != null">¥{{ (row.priceFen / 100).toFixed(2) }}</span>
                <span v-else>—</span>
              </td>
              <td class="is-center">{{ row.stock == null ? "—" : row.stock }}</td>
              <td class="is-center">
                <button
                  type="button"
                  class="decoration-page__picker-add-button"
                  :class="{ 'is-selected': isProductSelected(row) }"
                  :data-testid="`decoration-product-picker-add-${getProductIdentity(row)}`"
                  :data-product-id="getProductIdentity(row)"
                  @click="addProductToShelf(row)"
                >
                  {{ isProductSelected(row) ? "已选" : "加入" }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="decoration-page__picker-pagination">
        <span>共 {{ productPickerTotal }} 个在售商品</span>
        <el-pagination
          background
          layout="prev, pager, next"
          :current-page="productPickerPage"
          :page-size="productPickerPageSize"
          :total="productPickerTotal"
          @current-change="changeProductPickerPage"
        />
      </div>
    </el-dialog>
  </section>
</template>

<style scoped>
.decoration-page,
.decoration-page__card {
  height: 100%;
}

.decoration-page__card :deep(.el-card__body) {
  height: calc(100% - 73px);
}

.decoration-page__header,
.decoration-page__actions,
.decoration-page__block-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.decoration-page__header {
  justify-content: space-between;
}

.decoration-page__header p {
  margin: 6px 0 0;
  color: var(--yx-text-muted);
  font-size: 13px;
}

.decoration-page__page-select {
  width: 180px;
}

.decoration-page__page-tabs {
  display: flex;
  align-items: stretch;
  gap: 0;
  overflow: hidden;
  border: 1px solid var(--yx-border);
  border-radius: 8px;
  background: #fff;
}

.decoration-page__page-tab {
  display: grid;
  gap: 2px;
  width: 116px;
  padding: 7px 10px;
  border: 0;
  border-right: 1px solid var(--yx-border);
  background: transparent;
  color: var(--yx-text);
  text-align: left;
  cursor: pointer;
}

.decoration-page__page-tab:last-child {
  border-right: 0;
}

.decoration-page__page-tab strong,
.decoration-page__page-tab span {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.decoration-page__page-tab strong {
  font-size: 13px;
}

.decoration-page__page-tab span {
  color: var(--yx-text-muted);
  font-size: 11px;
}

.decoration-page__page-tab.is-active {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.decoration-page__page-option {
  display: grid;
  gap: 2px;
  line-height: 1.3;
}

.decoration-page__page-option span {
  color: var(--yx-text-muted);
  font-size: 12px;
}

.decoration-page__layout {
  display: grid;
  grid-template-columns: 280px minmax(320px, 1fr) 360px;
  gap: 16px;
  height: 100%;
  min-height: 0;
}

.decoration-page__blocks,
.decoration-page__editor,
.decoration-page__preview-wrap {
  min-height: 0;
  overflow: auto;
}

.decoration-page__panel-title {
  margin-bottom: 12px;
  color: var(--yx-text);
  font-weight: 700;
}

.decoration-page__block {
  display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--yx-border);
  border-radius: 8px;
  cursor: pointer;
}

.decoration-page__block + .decoration-page__block {
  margin-top: 10px;
}

.decoration-page__block.is-active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.decoration-page__block span {
  display: block;
  margin-top: 4px;
  color: var(--yx-text-muted);
  font-size: 12px;
}

.decoration-page__preview-wrap {
  display: flex;
  justify-content: center;
  padding: 4px 0;
}

.decoration-page__phone {
  width: 375px;
  height: 100%;
  min-height: 640px;
  overflow: hidden;
  border: 1px solid var(--yx-border);
  border-radius: 28px;
  background: #f7f7f7;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.12);
}

.decoration-page__phone-title {
  padding: 18px 16px;
  text-align: center;
  font-weight: 700;
  background: #fff;
}

.decoration-page__phone-body {
  display: grid;
  gap: 12px;
  height: calc(100% - 58px);
  padding: 14px;
  overflow: auto;
}

.decoration-page__search,
.decoration-page__notice,
.decoration-page__simple-block,
.decoration-page__shelf,
.decoration-page__category-grid,
.decoration-page__quick-grid,
.decoration-page__member-banner,
.decoration-page__notice-list,
.decoration-page__rich-text {
  padding: 14px;
  border-radius: 8px;
  background: #fff;
}

.decoration-page__search {
  color: #999;
}

.decoration-page__hero {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 220px;
  overflow: hidden;
  padding: 18px;
  border-radius: 16px;
  background:
    linear-gradient(90deg, rgba(246, 236, 226, 0.96) 0%, rgba(238, 218, 202, 0.9) 54%, rgba(220, 192, 165, 0.74) 100%),
    linear-gradient(135deg, #f9f5ef 0%, #ead7c5 100%);
  font-weight: 700;
  color: #6e4b2f;
}

.decoration-page__hero img {
  display: block;
  width: 100%;
  height: 220px;
  object-fit: cover;
}

.decoration-page__hero-copy {
  display: grid;
  gap: 8px;
  margin-top: auto;
}

.decoration-page__hero-copy small {
  font-size: 12px;
  letter-spacing: 0.16em;
  color: rgba(110, 75, 47, 0.72);
}

.decoration-page__hero-copy strong {
  font-size: 20px;
  line-height: 1.25;
}

.decoration-page__hero-copy span {
  color: rgba(110, 75, 47, 0.76);
  font-size: 13px;
  line-height: 1.4;
}

.decoration-page__hero-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 2px;
}

.decoration-page__hero-badges em {
  padding: 4px 8px;
  border: 1px solid rgba(185, 142, 92, 0.14);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  color: #8b5f39;
  font-size: 11px;
  font-style: normal;
}

.decoration-page__notice {
  color: #e94b4b;
  font-size: 13px;
}

.decoration-page__category-grid,
.decoration-page__quick-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.decoration-page__quick-grid strong {
  grid-column: 1 / -1;
}

.decoration-page__category-grid span,
.decoration-page__quick-grid span {
  min-height: 48px;
  padding: 8px 4px;
  border-radius: 8px;
  background: #f5f6f8;
  color: var(--yx-text-muted);
  font-size: 12px;
  text-align: center;
  word-break: break-all;
}

.decoration-page__member-banner {
  display: grid;
  gap: 6px;
  background: #1f2937;
  color: #fff;
}

.decoration-page__member-banner small {
  color: rgba(255, 255, 255, 0.7);
}

.decoration-page__member-banner em {
  justify-self: start;
  padding: 4px 10px;
  border-radius: 999px;
  background: #fff;
  color: #1f2937;
  font-size: 12px;
  font-style: normal;
}

.decoration-page__notice-list {
  display: grid;
  gap: 8px;
}

.decoration-page__notice-list div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
}

.decoration-page__notice-list span,
.decoration-page__rich-text p {
  min-width: 0;
  word-break: break-word;
}

.decoration-page__notice-list small {
  flex: none;
  color: var(--yx-text-muted);
}

.decoration-page__rich-text {
  display: grid;
  gap: 6px;
}

.decoration-page__rich-text p {
  margin: 0;
  color: var(--yx-text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.decoration-page__product-row {
  display: flex;
  gap: 10px;
  margin-top: 12px;
}

.decoration-page__shelf {
  display: grid;
  gap: 4px;
}

.decoration-page__shelf small {
  color: var(--yx-text-muted);
}

.decoration-page__product-row span {
  width: 96px;
  height: 118px;
  border-radius: 8px;
  background: #f6e4d8;
}

.decoration-page__field-header,
.decoration-page__item-title,
.decoration-page__inline-fields {
  display: flex;
  align-items: center;
  gap: 10px;
}

.decoration-page__hero-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.decoration-page__upload-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 30px;
  padding: 0 12px;
  border: 1px solid var(--el-color-primary);
  border-radius: 6px;
  color: var(--el-color-primary);
  background: #fff;
  font-size: 13px;
  cursor: pointer;
}

.decoration-page__upload-button input {
  display: none;
}

.decoration-page__hero-thumb {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  margin: 10px 0 14px;
  padding: 8px;
  border: 1px solid var(--yx-border);
  border-radius: 8px;
  background: #f8fafc;
}

.decoration-page__hero-thumb img {
  display: block;
  width: 112px;
  height: 64px;
  border-radius: 6px;
  object-fit: cover;
}

.decoration-page__hero-thumb span {
  min-width: 0;
  overflow: hidden;
  color: var(--yx-text-muted);
  font-size: 12px;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.decoration-page__field-header,
.decoration-page__item-title {
  justify-content: space-between;
}

.decoration-page__field-header {
  margin: 8px 0 12px;
  font-weight: 700;
}

.decoration-page__item-editor {
  padding: 12px;
  border: 1px solid var(--yx-border);
  border-radius: 8px;
  background: #fff;
}

.decoration-page__item-editor + .decoration-page__item-editor {
  margin-top: 12px;
}

.decoration-page__inline-fields {
  align-items: flex-start;
}

.decoration-page__inline-fields .el-form-item {
  flex: 1;
}

.decoration-page__advanced {
  margin-top: 16px;
}

.decoration-page__selected-products {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  width: 100%;
}

.decoration-page__selected-products :deep(.el-tag__content) {
  display: inline-grid;
  gap: 1px;
  max-width: 220px;
  line-height: 1.2;
}

.decoration-page__product-tag-title,
.decoration-page__selected-products small {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.decoration-page__selected-products small {
  color: var(--yx-text-muted);
  font-size: 11px;
}

.decoration-page__picker-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  margin-bottom: 14px;
}

.decoration-page__picker-table-wrap {
  min-height: 320px;
  max-height: 420px;
  overflow: auto;
  border: 1px solid var(--yx-border);
  border-radius: 8px;
}

.decoration-page__picker-loading,
.decoration-page__picker-empty {
  padding: 28px 12px;
  color: var(--yx-text-muted);
  text-align: center;
}

.decoration-page__picker-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  font-size: 13px;
}

.decoration-page__picker-table th,
.decoration-page__picker-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--yx-border);
  color: var(--yx-text);
  text-align: left;
  vertical-align: middle;
}

.decoration-page__picker-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #f8fafc;
  color: var(--yx-text-muted);
  font-weight: 600;
}

.decoration-page__picker-table th:nth-child(1),
.decoration-page__picker-table td:nth-child(1) {
  width: 36%;
}

.decoration-page__picker-table th:nth-child(2),
.decoration-page__picker-table td:nth-child(2) {
  width: 20%;
}

.decoration-page__picker-table th:nth-child(3),
.decoration-page__picker-table td:nth-child(3),
.decoration-page__picker-table th:nth-child(4),
.decoration-page__picker-table td:nth-child(4),
.decoration-page__picker-table th:nth-child(5),
.decoration-page__picker-table td:nth-child(5) {
  width: 14%;
}

.decoration-page__picker-table .is-right {
  text-align: right;
}

.decoration-page__picker-table .is-center {
  text-align: center;
}

.decoration-page__picker-product {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.decoration-page__picker-product strong,
.decoration-page__picker-product span {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.decoration-page__picker-product span {
  color: var(--yx-text-muted);
  font-size: 12px;
}

.decoration-page__picker-add-button {
  min-width: 54px;
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--el-color-primary);
  border-radius: 6px;
  background: var(--el-color-primary);
  color: #fff;
  font-size: 12px;
  cursor: pointer;
}

.decoration-page__picker-add-button.is-selected {
  background: #fff;
  color: var(--el-color-success);
  border-color: var(--el-color-success);
}

.decoration-page__picker-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 14px;
}

.decoration-page__picker-pagination span {
  color: var(--yx-text-muted);
  font-size: 13px;
}

@media (max-width: 1280px) {
  .decoration-page__layout {
    grid-template-columns: 260px minmax(300px, 1fr);
  }

  .decoration-page__editor {
    grid-column: 1 / -1;
  }
}
</style>
