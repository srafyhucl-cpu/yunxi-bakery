import { ROUTES } from "../../constants/routes";
import { SHOP_CONFIG } from "../../config/shop";
import { getMiniappLayoutMetrics } from "../../utils/layout";
import { addCartItem, getCartItems } from "../../utils/cart";
import { formatFen } from "../../utils/money";
import { syncCustomTabBar } from "../../utils/tab-bar";
import {
  listProductCategories,
  fetchProductListing,
  type ProductCategory
} from "../../services/products";
import {
  getProductActionLabel,
  getProductAddToastLabel,
  getProductAvailabilityLabel,
  getProductImageClass,
  getProductPriceText,
  getProductPurchaseHint,
  isProductPurchasable
} from "../../utils/bakery";
import type { CatalogProduct } from "../../types/catalog";

interface CategorySectionView {
  id: string;
  title: string;
  subtitle: string;
  countLabel: string;
  loaded: boolean;
  hasMatches: boolean;
}

interface ProductView extends CatalogProduct {
  priceText: string;
  imageClass: string;
  badgeText: string;
  badgeClass: string;
  imageFailed: boolean;
  isUnavailable: boolean;
  isDisplayOnly: boolean;
  stockText: string;
  purchaseHint: string;
  actionText: string;
}

interface ProductsPageData {
  layoutStyle: string;
  searchText: string;
  branchName: string;
  businessHours: string;
  loaded: boolean;
  loading: boolean;
  loadFailed: boolean;
  categoriesDegraded: boolean;
  categorySections: CategorySectionView[];
  isSingleCategoryLayout: boolean;
  globalSearchResults: ProductView[];
  searchMatchCount: number;
  searchRenderedCount: number;
  searchHasMore: boolean;
  searchOffset: number;
  searchLoading: boolean;
  searchLoadingMore: boolean;
  searchFailed: boolean;
  searchScrollAnchor: string;
  catalogScrollAnchor: string;
  activeCategoryId: string;
  activeCategoryTitle: string;
  activeCategoryCountLabel: string;
  activeProducts: ProductView[];
  catalogTotal: number;
  catalogOffset: number;
  hasMoreProducts: boolean;
  loadingMore: boolean;
  catalogLoading: boolean;
  // 仅用于请求竞态判定，不参与渲染；直接写 data 避免无谓的 setData 重排。
  searchDebounceTimer: number;
  searchRequestId: number;
  catalogRequestId: number;
  cartItemCount: number;
  cartTotalText: string;
  cartSummaryText: string;
  cartBarVisible: boolean;
}

interface ProductBadge {
  text: string;
  className: string;
}

const CATALOG_PAGE_SIZE = 12;
const SEARCH_PAGE_SIZE = 30;
const SEARCH_DEBOUNCE_MS = 300;
const ALL_PRODUCTS_CATEGORY_ID = "all";
const FALLBACK_CATEGORY_TITLE = "其他商品";
// 滚动锚点：新关键词或新分类后回到列表顶部，避免缩窄结果后停在旧偏移。
const CATALOG_SCROLL_ANCHOR = "products-catalog-top";
const SEARCH_SCROLL_ANCHOR = "products-search-top";

function getCategoryDisplayTitle(title: string): string {
  if (title === "芸熙周边惊喜连连") return "品牌周边";
  if (title === "招牌千层蛋糕") return "招牌千层";
  if (title === "甜品台茶歇") return "手作茶歇";
  if (title === "春节茶礼盒") return "新春礼盒";
  if (title === "糕点&礼盒") return "伴手礼盒";
  return title || FALLBACK_CATEGORY_TITLE;
}

function getCategoryWeight(title: string): number {
  if (title === "全部商品") return 100;
  if (title === "生日蛋糕") return 95;
  if (title === "招牌千层") return 90;
  if (title === "甜品和面包") return 85;
  if (title === "伴手礼盒") return 80;
  if (title === "手作茶歇") return 75;
  if (title.includes("礼盒")) return 70;
  if (title === "品牌周边") return 20;
  if (title === FALLBACK_CATEGORY_TITLE) return 10;
  return 50;
}

function refineCategorySections(sections: CategorySectionView[]): CategorySectionView[] {
  return sections
    .map((section) => ({
      ...section,
      title: getCategoryDisplayTitle(section.title)
    }))
    .sort((left, right) => getCategoryWeight(right.title) - getCategoryWeight(left.title));
}

function buildCategorySections(
  categories: ProductCategory[],
  totalProducts: number
): CategorySectionView[] {
  const allSection: CategorySectionView = {
    id: ALL_PRODUCTS_CATEGORY_ID,
    title: "全部商品",
    subtitle: `${totalProducts} 款`,
    countLabel: String(totalProducts),
    loaded: true,
    hasMatches: totalProducts > 0
  };
  const remoteSections = categories.map((category) => ({
    id: category.id,
    title: category.title,
    subtitle: `${category.productCount || 0} 款`,
    countLabel: String(category.productCount || 0),
    loaded: false,
    hasMatches: category.productCount > 0
  }));
  return refineCategorySections([allSection, ...remoteSections]);
}

function withCategoryTotal(
  sections: CategorySectionView[],
  categoryId: string,
  totalProducts: number
): CategorySectionView[] {
  return sections.map((section) =>
    section.id === categoryId
      ? {
          ...section,
          subtitle: `${totalProducts} 款`,
          countLabel: String(totalProducts),
          loaded: true,
          hasMatches: totalProducts > 0
        }
      : section
  );
}

function getTruthfulBadge(product: CatalogProduct): ProductBadge {
  // 图片角标只承担异常状态，库存/现货事实交给卡片内的可用性标签，避免同一事实重复展示。
  // 招牌/热卖/新品/限量没有数据来源，不在本地推断展示。
  if (product.isPurchasable === false) {
    return { text: "仅供展示", className: "is-display-only" };
  }
  if (!product.isActive) {
    return { text: "已下架", className: "is-inactive" };
  }
  if (product.stock <= 0) {
    return { text: "暂时售罄", className: "is-sold-out" };
  }
  return { text: "", className: "" };
}

function getPurchaseHint(product: CatalogProduct): string {
  if (product.isPurchasable === false) {
    return getProductPurchaseHint(product);
  }
  if (!product.isActive || product.stock <= 0) {
    return "可咨询客服或先看其他商品";
  }
  return getProductPurchaseHint(product);
}

function toProductView(product: CatalogProduct): ProductView {
  const badge = getTruthfulBadge(product);
  const isUnavailable = product.isPurchasable === false || !product.isActive || product.stock <= 0;
  return {
    ...product,
    priceText: getProductPriceText(product, formatFen(product.priceFen)),
    imageClass: getProductImageClass(product),
    badgeText: badge.text,
    badgeClass: badge.className,
    imageFailed: false,
    isUnavailable,
    isDisplayOnly: !isProductPurchasable(product),
    stockText: getProductAvailabilityLabel(product),
    purchaseHint: getPurchaseHint(product),
    actionText: getProductActionLabel(product)
  };
}

function mergeProductViews(existing: ProductView[], incoming: ProductView[]): ProductView[] {
  const seen = new Set(existing.map((product) => product.id));
  return [
    ...existing,
    ...incoming.filter((product) => {
      if (seen.has(product.id)) {
        return false;
      }
      seen.add(product.id);
      return true;
    })
  ];
}

// 搜索态统一复位入口：清空关键词、切分类和重试时不能只清列表而漏掉计数。
function getEmptySearchState() {
  return {
    globalSearchResults: [] as ProductView[],
    searchMatchCount: 0,
    searchRenderedCount: 0,
    searchHasMore: false,
    searchOffset: 0,
    searchLoading: false,
    searchLoadingMore: false,
    searchFailed: false,
    searchScrollAnchor: ""
  };
}

function prefetchProductImages(products: ProductView[]): void {
  const imageUrls = products
    .map((product) => product.imageUrl)
    .filter((imageUrl): imageUrl is string => Boolean(imageUrl))
    .slice(0, 4);

  imageUrls.forEach((src) => {
    wx.getImageInfo({
      src,
      fail: () => undefined
    });
  });
}

function getCartQuantity(productId: string): number {
  return getCartItems()
    .filter((item) => item.productId === productId)
    .reduce((sum, item) => sum + item.quantity, 0);
}

function getProductFromViews(products: ProductView[], productId: string): ProductView | undefined {
  return products.find((product) => product.id === productId);
}

Page<ProductsPageData, WechatMiniprogram.IAnyObject>({
  data: {
    layoutStyle: getMiniappLayoutMetrics().pageShellStyle,
    searchText: "",
    branchName: SHOP_CONFIG.branchName,
    businessHours: SHOP_CONFIG.businessHours,
    loaded: false,
    loading: false,
    loadFailed: false,
    categoriesDegraded: false,
    categorySections: [] as CategorySectionView[],
    isSingleCategoryLayout: false,
    globalSearchResults: [] as ProductView[],
    searchMatchCount: 0,
    searchRenderedCount: 0,
    searchHasMore: false,
    searchOffset: 0,
    searchLoading: false,
    searchLoadingMore: false,
    searchFailed: false,
    searchScrollAnchor: "",
    catalogScrollAnchor: "",
    activeCategoryId: ALL_PRODUCTS_CATEGORY_ID,
    activeCategoryTitle: "全部商品",
    activeCategoryCountLabel: "0",
    activeProducts: [] as ProductView[],
    catalogTotal: 0,
    catalogOffset: 0,
    hasMoreProducts: false,
    loadingMore: false,
    catalogLoading: false,
    searchDebounceTimer: 0,
    searchRequestId: 0,
    catalogRequestId: 0,
    cartItemCount: 0,
    cartTotalText: "¥0.00",
    cartSummaryText: "还没有选择商品",
    cartBarVisible: false
  },
  onLoad() {
    void this.loadProducts();
  },
  onShow() {
    syncCustomTabBar(ROUTES.products);
    this.refreshCartSummary();
  },
  onUnload() {
    this.clearSearchDebounce();
  },
  clearSearchDebounce() {
    if (this.data.searchDebounceTimer) {
      clearTimeout(this.data.searchDebounceTimer);
      this.data.searchDebounceTimer = 0;
    }
  },
  resetSearchState() {
    // 复位必须同时作废在途请求，否则旧关键词响应会覆盖清空后的状态。
    this.clearSearchDebounce();
    this.data.searchRequestId += 1;
    this.setData(getEmptySearchState());
  },
  async loadProducts() {
    if (this.data.loaded || this.data.loading) {
      return;
    }
    const requestId = this.data.catalogRequestId + 1;
    this.data.catalogRequestId = requestId;
    this.setData({ loading: true, loadFailed: false });
    try {
      // 商品与分类独立结算：主列表失败整页可重试，分类失败降级为单分类浏览。
      const [productsResult, categoriesResult] = await Promise.allSettled([
        fetchProductListing({ limit: CATALOG_PAGE_SIZE, offset: 0, sort: "popular" }),
        listProductCategories()
      ]);
      if (requestId !== this.data.catalogRequestId) {
        return;
      }
      if (productsResult.status === "rejected") {
        this.setData({ loadFailed: true });
        return;
      }
      const page = productsResult.value;
      const categories = categoriesResult.status === "fulfilled" ? categoriesResult.value : [];
      const categorySections = buildCategorySections(categories, page.meta.total);
      const activeProducts = page.items.map((product) => toProductView(product));
      this.setData({
        categorySections,
        isSingleCategoryLayout: categorySections.length <= 1,
        categoriesDegraded: categoriesResult.status === "rejected",
        loaded: true,
        loadFailed: false,
        activeCategoryId: ALL_PRODUCTS_CATEGORY_ID,
        activeCategoryTitle: "全部商品",
        activeCategoryCountLabel: String(page.meta.total),
        activeProducts,
        catalogTotal: page.meta.total,
        catalogOffset: page.meta.offset + page.meta.limit,
        hasMoreProducts: page.meta.hasMore,
        loadingMore: false,
        catalogLoading: false
      });
      prefetchProductImages(activeProducts);
    } finally {
      if (requestId === this.data.catalogRequestId) {
        this.setData({ loading: false });
      }
    }
  },
  retryLoad() {
    // 失败重试：复位加载态后重新走完整加载链路
    if (this.data.loading) {
      return;
    }
    this.setData({
      loaded: false,
      loadFailed: false,
      categoriesDegraded: false,
      categorySections: []
    });
    this.resetSearchState();
    void this.loadProducts();
  },
  async selectCategory(section: CategorySectionView) {
    // 失败时要能回到切换前的真实列表，不能让用户看到空目录。
    const previousCatalog = {
      activeCategoryId: this.data.activeCategoryId,
      activeCategoryTitle: this.data.activeCategoryTitle,
      activeCategoryCountLabel: this.data.activeCategoryCountLabel,
      activeProducts: this.data.activeProducts,
      catalogTotal: this.data.catalogTotal,
      catalogOffset: this.data.catalogOffset,
      hasMoreProducts: this.data.hasMoreProducts
    };
    const requestId = this.data.catalogRequestId + 1;
    this.data.catalogRequestId = requestId;
    this.setData({
      activeCategoryId: section.id,
      activeCategoryTitle: section.title,
      activeCategoryCountLabel: section.countLabel,
      catalogLoading: true,
      loadingMore: false,
      catalogOffset: 0,
      hasMoreProducts: false
    });
    try {
      const page = await fetchProductListing({
        categoryId: section.id === ALL_PRODUCTS_CATEGORY_ID ? undefined : section.id,
        limit: CATALOG_PAGE_SIZE,
        offset: 0,
        sort: "popular"
      });
      if (requestId !== this.data.catalogRequestId) {
        return;
      }
      const activeProducts = page.items.map((product) => toProductView(product));
      this.setData({
        activeProducts,
        catalogTotal: page.meta.total,
        catalogOffset: page.meta.offset + page.meta.limit,
        hasMoreProducts: page.meta.hasMore,
        activeCategoryCountLabel: String(page.meta.total),
        catalogLoading: false,
        categorySections: withCategoryTotal(
          this.data.categorySections,
          section.id,
          page.meta.total
        )
      });
      prefetchProductImages(activeProducts);
      this.resetCatalogScrollPosition();
    } catch {
      if (requestId !== this.data.catalogRequestId) {
        return;
      }
      // 分类加载失败：回滚到切换前分类，既不展示别的分类商品，也不把列表清空。
      this.setData({
        ...previousCatalog,
        catalogLoading: false
      });
      wx.showToast({ title: "分类加载失败，请稍后重试", icon: "none" });
    }
  },
  async switchCategory(event: WechatMiniprogram.TouchEvent) {
    const categoryId = String(event.currentTarget.dataset.categoryId || "");
    if (!categoryId || categoryId === this.data.activeCategoryId) {
      return;
    }
    const section = this.data.categorySections.find((item) => item.id === categoryId);
    if (!section) {
      return;
    }
    this.setData({ searchText: "" });
    this.resetSearchState();
    await this.selectCategory(section);
  },
  switchToAll() {
    // 分类空态兜底：一键切回全部商品
    this.setData({ searchText: "" });
    this.resetSearchState();
    const allSection = this.data.categorySections.find(
      (section) => section.id === ALL_PRODUCTS_CATEGORY_ID
    );
    if (allSection && allSection.id !== this.data.activeCategoryId) {
      void this.selectCategory(allSection);
    }
  },
  async loadMoreProducts() {
    if (this.data.loadingMore || this.data.catalogLoading || !this.data.hasMoreProducts) {
      return;
    }
    const requestId = this.data.catalogRequestId;
    const categoryId =
      this.data.activeCategoryId === ALL_PRODUCTS_CATEGORY_ID
        ? undefined
        : this.data.activeCategoryId;
    this.setData({ loadingMore: true });
    try {
      const page = await fetchProductListing({
        categoryId,
        limit: CATALOG_PAGE_SIZE,
        offset: this.data.catalogOffset,
        sort: "popular"
      });
      if (requestId !== this.data.catalogRequestId) {
        return;
      }
      const incoming = page.items.map((product) => toProductView(product));
      const activeProducts = mergeProductViews(this.data.activeProducts, incoming);
      this.setData({
        activeProducts,
        catalogTotal: page.meta.total,
        catalogOffset: page.meta.offset + page.meta.limit,
        hasMoreProducts: page.meta.hasMore,
        categorySections: withCategoryTotal(
          this.data.categorySections,
          this.data.activeCategoryId,
          page.meta.total
        )
      });
      prefetchProductImages(incoming);
    } catch {
      if (requestId === this.data.catalogRequestId) {
        wx.showToast({ title: "加载更多失败，请重试", icon: "none" });
      }
    } finally {
      if (requestId === this.data.catalogRequestId) {
        this.setData({ loadingMore: false });
      }
    }
  },
  isCurrentSearch(requestId: number, keyword: string): boolean {
    return requestId === this.data.searchRequestId && this.data.searchText.trim() === keyword;
  },
  scheduleSearch(keyword: string) {
    this.clearSearchDebounce();
    const nextKeyword = keyword.trim();
    if (!nextKeyword) {
      this.resetSearchState();
      return;
    }
    this.data.searchDebounceTimer = setTimeout(() => {
      this.data.searchDebounceTimer = 0;
      void this.runSearch(nextKeyword);
    }, SEARCH_DEBOUNCE_MS);
  },
  async runSearch(keyword: string) {
    const activeKeyword = keyword.trim();
    if (!activeKeyword) {
      return;
    }
    const requestId = this.data.searchRequestId + 1;
    this.data.searchRequestId = requestId;
    this.setData({
      searchLoading: true,
      searchLoadingMore: false,
      searchFailed: false
    });
    try {
      const page = await fetchProductListing({
        keyword: activeKeyword,
        limit: SEARCH_PAGE_SIZE,
        offset: 0,
        sort: "popular"
      });
      if (!this.isCurrentSearch(requestId, activeKeyword)) {
        return;
      }
      const globalSearchResults = page.items.map((product) => toProductView(product));
      this.setData({
        globalSearchResults,
        searchMatchCount: page.meta.total,
        searchRenderedCount: globalSearchResults.length,
        searchHasMore: page.meta.hasMore,
        searchOffset: page.meta.offset + page.meta.limit,
        searchLoading: false,
        searchFailed: false
      });
      prefetchProductImages(globalSearchResults);
      this.resetSearchScrollPosition();
    } catch {
      if (!this.isCurrentSearch(requestId, activeKeyword)) {
        return;
      }
      this.setData({
        ...getEmptySearchState(),
        searchFailed: true
      });
    }
  },
  retrySearch() {
    const keyword = this.data.searchText.trim();
    if (!keyword) {
      return;
    }
    void this.runSearch(keyword);
  },
  async loadMoreSearchResults() {
    const keyword = this.data.searchText.trim();
    if (
      !keyword ||
      this.data.searchLoading ||
      this.data.searchLoadingMore ||
      !this.data.searchHasMore
    ) {
      return;
    }
    const requestId = this.data.searchRequestId;
    this.setData({ searchLoadingMore: true });
    try {
      const page = await fetchProductListing({
        keyword,
        limit: SEARCH_PAGE_SIZE,
        offset: this.data.searchOffset,
        sort: "popular"
      });
      if (!this.isCurrentSearch(requestId, keyword)) {
        return;
      }
      const incoming = page.items.map((product) => toProductView(product));
      const globalSearchResults = mergeProductViews(this.data.globalSearchResults, incoming);
      this.setData({
        globalSearchResults,
        searchMatchCount: page.meta.total,
        searchRenderedCount: globalSearchResults.length,
        searchHasMore: page.meta.hasMore,
        searchOffset: page.meta.offset + page.meta.limit
      });
      prefetchProductImages(incoming);
    } catch {
      if (this.isCurrentSearch(requestId, keyword)) {
        wx.showToast({ title: "加载更多失败，请重试", icon: "none" });
      }
    } finally {
      if (this.isCurrentSearch(requestId, keyword)) {
        this.setData({ searchLoadingMore: false });
      }
    }
  },
  resetSearchScrollPosition() {
    // scroll-into-view 只有值变化才会生效：先清空再指向顶部锚点。
    this.setData({ searchScrollAnchor: "" }, () => {
      this.setData({ searchScrollAnchor: SEARCH_SCROLL_ANCHOR });
    });
  },
  resetCatalogScrollPosition() {
    this.setData({ catalogScrollAnchor: "" }, () => {
      this.setData({ catalogScrollAnchor: CATALOG_SCROLL_ANCHOR });
    });
  },
  onSearchInput(event: WechatMiniprogram.Input) {
    const value = String(event.detail.value || "");
    this.setData({ searchText: value });
    this.scheduleSearch(value);
  },
  clearSearch() {
    this.setData({ searchText: "" });
    this.resetSearchState();
  },
  refreshCartSummary() {
    const cartItems = getCartItems();
    const cartItemCount = cartItems.reduce((sum, item) => sum + item.quantity, 0);
    const cartTotalFen = cartItems.reduce((sum, item) => sum + item.priceFen * item.quantity, 0);
    this.setData({
      cartItemCount,
      cartTotalText: formatFen(cartTotalFen),
      cartSummaryText:
        cartItemCount > 0 ? cartItemCount + " 件已选 · 闪送费下单前确认" : "还没有选择商品",
      cartBarVisible: cartItemCount > 0
    });
  },
  quickAddProduct(event: WechatMiniprogram.TouchEvent) {
    const productId = String(event.currentTarget.dataset.id || "");
    if (!productId) {
      return;
    }
    const product =
      getProductFromViews(this.data.activeProducts, productId) ||
      getProductFromViews(this.data.globalSearchResults, productId);
    if (!product || product.isPurchasable === false || !product.isActive || product.stock <= 0) {
      wx.navigateTo({ url: `${ROUTES.productDetail}?id=${productId}` });
      return;
    }
    const currentQuantity = getCartQuantity(productId);
    if (currentQuantity >= product.stock) {
      wx.showToast({ title: "库存仅余 " + product.stock + " 件", icon: "none" });
      return;
    }
    addCartItem({
      productId: product.id,
      title: product.title,
      imageUrl: product.imageUrl,
      priceFen: product.priceFen,
      quantity: 1,
      stock: product.stock
    });
    this.refreshCartSummary();
    wx.showToast({ title: getProductAddToastLabel(product), icon: "success" });
  },
  onProductImageError(event: WechatMiniprogram.TouchEvent) {
    // 图片运行时加载失败：按商品定位当前渲染项并切换占位，保持固定宽高。
    const productId = String(event.currentTarget.dataset.id || "");
    if (!productId) {
      return;
    }
    const updates: Record<string, boolean> = {};
    this.data.activeProducts.forEach((product, productIndex) => {
      if (product.id === productId && !product.imageFailed) {
        updates[`activeProducts[${productIndex}].imageFailed`] = true;
      }
    });
    this.data.globalSearchResults.forEach((product, resultIndex) => {
      if (product.id === productId && !product.imageFailed) {
        updates[`globalSearchResults[${resultIndex}].imageFailed`] = true;
      }
    });
    if (Object.keys(updates).length > 0) {
      this.setData(updates);
    }
  },
  openProduct(event: WechatMiniprogram.TouchEvent) {
    const productId = String(event.currentTarget.dataset.id || "");
    if (!productId) {
      return;
    }
    wx.navigateTo({
      url: `${ROUTES.productDetail}?id=${productId}`
    });
  },
  goToCart() {
    wx.switchTab({ url: ROUTES.cart });
  },
  goCheckout() {
    if (!getCartItems().length) {
      wx.showToast({ title: "请先选择商品", icon: "none" });
      return;
    }
    wx.navigateTo({ url: ROUTES.checkout });
  },
  goToChat() {
    wx.switchTab({ url: ROUTES.chat });
  }
});
