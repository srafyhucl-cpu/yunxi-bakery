<script setup lang="ts">
import { Plus, RefreshRight } from "@element-plus/icons-vue";

import { useFeaturedProductsPage } from "./useFeaturedProductsPage";

const {
  loading,
  saving,
  searching,
  keyword,
  featuredItems,
  searchResults,
  hasUnsavedChanges,
  searchProducts,
  addFeaturedProduct,
  removeFeaturedProduct,
  moveProduct,
  saveFeaturedProducts,
} = useFeaturedProductsPage();
</script>

<template>
  <section class="featured-products-page" v-loading="loading">
    <el-card shadow="never">
      <template #header>
        <div class="featured-products-page__header">
          <div>
            <strong>主推款配置</strong>
            <p>维护前台推荐顺序，保存后会直接影响 RAG 推荐优先级。</p>
          </div>
          <el-button :icon="RefreshRight" @click="searchProducts">刷新候选商品</el-button>
        </div>
      </template>

      <div class="featured-products-page__layout">
        <section class="featured-products-page__panel">
          <div class="featured-products-page__panel-head">
            <strong>候选商品</strong>
            <span>从商品知识里搜索并加入主推款</span>
          </div>

          <el-form class="featured-products-page__search" @submit.prevent="searchProducts">
            <el-input
              v-model="keyword"
              placeholder="搜索商品标题"
              clearable
              @keyup.enter="searchProducts"
            />
            <el-button type="primary" :loading="searching" @click="searchProducts">搜索</el-button>
          </el-form>

          <div class="featured-products-page__candidate-list">
            <el-empty v-if="searchResults.length === 0" description="暂时没有匹配商品" />
            <article
              v-for="product in searchResults"
              :key="product.id"
              class="featured-products-page__candidate"
            >
              <div class="featured-products-page__candidate-body">
                <strong>{{ product.title }}</strong>
                <span>
                  {{ product.isActive ? "在售" : "下架" }}
                  <template v-if="product.youzanItemId"> / 有赞 {{ product.youzanItemId }}</template>
                </span>
              </div>
              <el-button :icon="Plus" circle @click="addFeaturedProduct(product)" />
            </article>
          </div>
        </section>

        <section class="featured-products-page__panel">
          <div class="featured-products-page__panel-head">
            <strong>当前主推款</strong>
            <span>保存顺序就是推荐时的优先顺序</span>
          </div>

          <div class="featured-products-page__featured-list">
            <el-empty v-if="featuredItems.length === 0" description="还没有设置主推款" />
            <article
              v-for="(item, index) in featuredItems"
              :key="item.title"
              class="featured-products-page__featured-item"
            >
              <div class="featured-products-page__featured-main">
                <strong>{{ index + 1 }}. {{ item.title }}</strong>
                <span v-if="item.product">
                  {{ item.product.isActive ? "在售" : "下架" }}
                  <template v-if="item.product.lastSyncSource"> / {{ item.product.lastSyncSource }}</template>
                </span>
                <span v-else>当前候选列表里暂无这款商品的详情</span>
              </div>

              <div class="featured-products-page__featured-actions">
                <el-button
                  text
                  :disabled="index === 0"
                  @click="moveProduct(item.title, -1)"
                >
                  上移
                </el-button>
                <el-button
                  text
                  :disabled="index === featuredItems.length - 1"
                  @click="moveProduct(item.title, 1)"
                >
                  下移
                </el-button>
                <el-button text type="danger" @click="removeFeaturedProduct(item.title)">
                  移除
                </el-button>
              </div>
            </article>
          </div>

          <div class="featured-products-page__save-bar">
            <span>{{ hasUnsavedChanges ? "有未保存变更" : "当前配置已保存" }}</span>
            <el-button
              type="primary"
              :loading="saving"
              :disabled="!hasUnsavedChanges"
              @click="saveFeaturedProducts"
            >
              保存主推款
            </el-button>
          </div>
        </section>
      </div>
    </el-card>
  </section>
</template>

<style scoped>
.featured-products-page {
  display: grid;
  gap: 16px;
}

.featured-products-page__header,
.featured-products-page__panel-head,
.featured-products-page__candidate,
.featured-products-page__featured-item,
.featured-products-page__save-bar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.featured-products-page__header p,
.featured-products-page__panel-head span,
.featured-products-page__candidate-body span,
.featured-products-page__featured-main span,
.featured-products-page__save-bar span {
  color: var(--yx-text-muted);
  font-size: 13px;
}

.featured-products-page__header p {
  margin: 6px 0 0;
}

.featured-products-page__layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px;
}

.featured-products-page__panel {
  display: grid;
  gap: 16px;
  min-width: 0;
}

.featured-products-page__search {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
}

.featured-products-page__candidate-list,
.featured-products-page__featured-list {
  display: grid;
  gap: 12px;
}

.featured-products-page__candidate,
.featured-products-page__featured-item {
  padding: 14px 16px;
  border: 1px solid var(--yx-border);
  border-radius: 12px;
  background: #fff;
}

.featured-products-page__candidate-body,
.featured-products-page__featured-main {
  display: grid;
  gap: 4px;
}

.featured-products-page__featured-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.featured-products-page__save-bar {
  padding-top: 8px;
  border-top: 1px solid var(--yx-border);
  align-items: center;
}

@media (max-width: 1199px) {
  .featured-products-page__layout {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 767px) {
  .featured-products-page__header,
  .featured-products-page__candidate,
  .featured-products-page__featured-item,
  .featured-products-page__save-bar,
  .featured-products-page__search {
    display: grid;
  }

  .featured-products-page__save-bar {
    position: sticky;
    bottom: 0;
    padding: 12px 0 calc(12px + env(safe-area-inset-bottom));
    background: #fff;
  }
}
</style>
