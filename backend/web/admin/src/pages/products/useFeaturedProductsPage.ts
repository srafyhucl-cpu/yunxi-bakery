import { computed, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { featuredProductsService } from "@/services/featuredProducts";
import type { ProductListItem } from "@/types/product";

interface FeaturedProductItem {
  title: string;
  product: ProductListItem | null;
}

function buildFeaturedItems(titles: string[], products: ProductListItem[]): FeaturedProductItem[] {
  return titles.map((title) => ({
    title,
    product: products.find((item) => item.title === title) || null,
  }));
}

export function useFeaturedProductsPage() {
  const loading = ref(false);
  const saving = ref(false);
  const searching = ref(false);
  const keyword = ref("");
  const featuredTitles = ref<string[]>([]);
  const searchResults = ref<ProductListItem[]>([]);

  const featuredItems = computed(() => buildFeaturedItems(featuredTitles.value, searchResults.value));
  const hasUnsavedChanges = ref(false);

  async function loadPage() {
    loading.value = true;
    try {
      const [titles, products] = await Promise.all([
        featuredProductsService.getFeaturedProducts(),
        featuredProductsService.searchCandidates(""),
      ]);
      featuredTitles.value = titles;
      searchResults.value = products;
      hasUnsavedChanges.value = false;
    } finally {
      loading.value = false;
    }
  }

  async function searchProducts() {
    searching.value = true;
    try {
      searchResults.value = await featuredProductsService.searchCandidates(keyword.value.trim());
    } finally {
      searching.value = false;
    }
  }

  function addFeaturedProduct(product: ProductListItem) {
    if (featuredTitles.value.includes(product.title)) {
      ElMessage.warning("该商品已经在主推款列表里了");
      return;
    }
    featuredTitles.value = [...featuredTitles.value, product.title];
    hasUnsavedChanges.value = true;
  }

  function removeFeaturedProduct(title: string) {
    featuredTitles.value = featuredTitles.value.filter((item) => item !== title);
    hasUnsavedChanges.value = true;
  }

  function moveProduct(title: string, direction: -1 | 1) {
    const currentIndex = featuredTitles.value.findIndex((item) => item === title);
    const nextIndex = currentIndex + direction;
    if (currentIndex < 0 || nextIndex < 0 || nextIndex >= featuredTitles.value.length) {
      return;
    }
    const nextTitles = [...featuredTitles.value];
    [nextTitles[currentIndex], nextTitles[nextIndex]] = [nextTitles[nextIndex], nextTitles[currentIndex]];
    featuredTitles.value = nextTitles;
    hasUnsavedChanges.value = true;
  }

  async function saveFeaturedProducts() {
    saving.value = true;
    try {
      const payload = await featuredProductsService.saveFeaturedProducts(featuredTitles.value);
      featuredTitles.value = payload.data;
      hasUnsavedChanges.value = false;
      ElMessage.success(payload.message || "主推款已保存");
    } finally {
      saving.value = false;
    }
  }

  onMounted(async () => {
    await loadPage();
  });

  return {
    loading,
    saving,
    searching,
    keyword,
    featuredTitles,
    featuredItems,
    searchResults,
    hasUnsavedChanges,
    loadPage,
    searchProducts,
    addFeaturedProduct,
    removeFeaturedProduct,
    moveProduct,
    saveFeaturedProducts,
  };
}
