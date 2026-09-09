import { ROUTES } from "../../constants/routes";
import { SHOP_CONFIG } from "../../config/shop";
import { getMiniappLayoutMetrics } from "../../utils/layout";
import { addCartItem, getCartItems } from "../../utils/cart";
import { getCategoryById } from "../../utils/catalog";
import { formatFen } from "../../utils/money";
import { syncCustomTabBar } from "../../utils/tab-bar";
import { listProductCategories, listProducts } from "../../services/products";
import { getProductImageClass } from "../../utils/bakery";
import type { CatalogProduct } from "../../types/catalog";

interface CategorySection {
  id: string;
  title: string;
  subtitle: string;
  products: CatalogProduct[];
}

type BadgeKind = "" | "flagship" | "new" | "hot" | "limited";

interface ProductView extends CatalogProduct {
  priceText: string;
  imageClass: string;
  badgeText: string;
  badgeClass: string;
  imageFailed: boolean;
  isUnavailable: boolean;
  stockText: string;
  purchaseHint: string;
  actionText: string;
  isSearchResult?: boolean;
}

interface CategorySectionView extends CategorySection {
  countLabel: string;
  products: ProductView[];
  hasMatches?: boolean;
  loaded: boolean;
}

interface ProductsPageData {
  layoutStyle: string;
  searchText: string;
  storeName: string;
  loaded: boolean;
  loading: boolean;
  loadFailed: boolean;
  categoriesDegraded: boolean;
  allProducts: CatalogProduct[];
  categorySections: CategorySectionView[];
  isSingleCategoryLayout: boolean;
  branchName: string;
  businessHours: string;
  globalSearchResults: ProductView[];
  activeCategoryId: string;
  activeCategoryTitle: string;
  activeCategorySubtitle: string;
  activeCategoryCountLabel: string;
  activeSectionProducts: ProductView[];
  activeProducts: ProductView[];
  visibleProductCount: number;
  hasMoreProducts: boolean;
  loadingMore: boolean;
  cartItemCount: number;
  cartTotalText: string;
  cartSummaryText: string;
  cartBarVisible: boolean;
}

const INITIAL_PRODUCTS_PER_SECTION = 12;
const PRODUCTS_PAGE_SIZE = 12;
const ALL_PRODUCTS_CATEGORY_ID = "all";
// 全量目录安全上限：后端默认 50 未覆盖全量，取 500（≥ 当前全量并与默认分页档位拉开量级）；
// 后续产品决策引入服务端分页后由 total/分页逻辑替换（API 现为纯数组无 total 字段）
const FULL_CATALOG_LIMIT = 500;
const FALLBACK_CATEGORY_TITLE = "特色推荐";
const RAW_CATEGORY_ID_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)+$/i;
const GENERIC_CATEGORY_TOKENS = new Set([
  "",
  "商品",
  "价格",
  "推荐",
  "蛋糕",
  "在售",
  "现做",
  "4寸",
  "6寸",
  "8寸",
  "10寸",
  "12寸",
  "14寸",
  "16寸"
]);

function getSearchText(product: CatalogProduct): string {
  return [
    product.title,
    product.subtitle,
    product.categoryId,
    product.description,
    ...product.tags,
    ...product.specs
  ].join(" ");
}

function normalizeCategoryId(title: string): string {
  return title
    .trim()
    .toLocaleLowerCase()
    .replace(/[^\w\u4e00-\u9fa5]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function isUsefulCategoryToken(value: string): boolean {
  const token = value.trim();
  if (!token || GENERIC_CATEGORY_TOKENS.has(token)) {
    return false;
  }
  if (RAW_CATEGORY_ID_PATTERN.test(token)) {
    return false;
  }
  return !/^\d+\s*寸$/.test(token);
}

function normalizeCategoryToken(value: string): string {
  return value.trim().replace(/\s+/g, "").toLocaleLowerCase();
}

function isProductTitleToken(value: string, product: CatalogProduct): boolean {
  const token = normalizeCategoryToken(value);
  return token === normalizeCategoryToken(product.title) || token === normalizeCategoryToken(product.subtitle);
}

function isUsefulProductCategoryToken(value: string, product: CatalogProduct): boolean {
  return isUsefulCategoryToken(value) && !isProductTitleToken(value, product);
}

function getProductCategoryTitle(product: CatalogProduct): string {
  if (product.categoryName && isUsefulProductCategoryToken(product.categoryName, product)) {
    return product.categoryName;
  }
  const localCategory = getCategoryById(product.categoryId);
  if (localCategory?.title && isUsefulProductCategoryToken(localCategory.title, product)) {
    return localCategory.title;
  }
  if (isUsefulProductCategoryToken(product.categoryId, product)) {
    return product.categoryId;
  }
  return FALLBACK_CATEGORY_TITLE;
}

function buildSectionsFromProducts(products: CatalogProduct[]): CategorySectionView[] {
  const buckets = new Map<string, CategorySection>();
  const allProductsSection: CategorySection = {
    id: ALL_PRODUCTS_CATEGORY_ID,
    title: "全部商品",
    subtitle: "门店在售商品",
    products
  };

  products.forEach((product) => {
    const title = getProductCategoryTitle(product);
    const id = normalizeCategoryId(title) || "youzan-synced";
    const existing = buckets.get(id);
    if (existing) {
      existing.products.push(product);
      return;
    }
    let subtitle = "匠心手作";
    if (title.includes("蛋糕")) {
      subtitle = "建议提前预订";
    } else if (title.includes("面包") || title.includes("甜品")) {
      subtitle = "麦香现烤";
    } else if (title.includes("礼盒") || title.includes("糕点")) {
      subtitle = "手作茶点";
    }
    buckets.set(id, {
      id,
      title,
      subtitle,
      products: [product]
    });
  });

  return [allProductsSection, ...Array.from(buckets.values())]
    .filter((section) => section.products.length)
    .map(buildSectionView);
}



function getBadgeKind(product: CatalogProduct, isFirst: boolean): BadgeKind {
  // 徽标四类本地映射：分区首位为招牌，标签含新品或限量关键字跟随标签，其余走热卖
  if (isFirst) {
    return "flagship";
  }
  if (product.tags.some((tag) => tag.includes("新品"))) {
    return "new";
  }
  if (product.tags.some((tag) => tag.includes("限量"))) {
    return "limited";
  }
  return "hot";
}

function getBadgeText(kind: BadgeKind): string {
  if (kind === "flagship") {
    return "招牌";
  }
  if (kind === "new") {
    return "新品";
  }
  if (kind === "limited") {
    return "限量";
  }
  return "热卖";
}

function getStockText(product: CatalogProduct): string {
  if (!product.isActive) {
    return "已下架";
  }
  if (product.stock <= 0) {
    return "暂时售罄";
  }
  if (product.stock <= 5) {
    return "仅余 " + product.stock + " 件";
  }
  return "可预订";
}

function getPurchaseHint(product: CatalogProduct): string {
  if (!product.isActive || product.stock <= 0) {
    return "可咨询客服或先看其他商品";
  }
  if (product.tags.some((tag) => tag.includes("现货") || tag.includes("当日"))) {
    return "有现货时可当天取，建议先确认";
  }
  if (product.categoryName?.includes("蛋糕") || product.categoryId.includes("cake")) {
    return "建议提前1天预订";
  }
  return "自提价展示，闪送费下单前确认";
}

function toProductView(product: CatalogProduct, isFirst = false): ProductView {
  const badgeKind = getBadgeKind(product, isFirst);
  const isUnavailable = !product.isActive || product.stock <= 0;
  return {
    ...product,
    priceText: formatFen(product.priceFen),
    imageClass: getProductImageClass(product),
    badgeText: getBadgeText(badgeKind),
    badgeClass: badgeKind ? `is-${badgeKind}` : "",
    imageFailed: false,
    isUnavailable,
    stockText: getStockText(product),
    purchaseHint: getPurchaseHint(product),
    actionText: isUnavailable ? "查看" : "预订"
  };
}

function buildSectionView(section: CategorySection): CategorySectionView {
  return {
    ...section,
    countLabel: String(section.products.length),
    products: section.products.map((product, index) => toProductView(product, index === 0)),
    loaded: true
  };
}

function getVisibleProducts(products: ProductView[], visibleProductCount: number): ProductView[] {
  return products.slice(0, visibleProductCount);
}

function getInitialVisibleCount(products: ProductView[]): number {
  return Math.min(INITIAL_PRODUCTS_PER_SECTION, products.length);
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

function getProductFromViews(products: ProductView[], productId: string): CatalogProduct | undefined {
  return products.find((product) => product.id === productId);
}

function refineCategorySections(sections: CategorySectionView[]): CategorySectionView[] {
  // 1. 精简分类标题，保持界面文案统一
  const renamed = sections.map((section) => {
    let title = section.title;
    if (title === "芸熙周边惊喜连连") title = "品牌周边";
    else if (title === "招牌千层蛋糕") title = "招牌千层";
    else if (title === "甜品台茶歇") title = "手作茶歇";
    else if (title === "春节茶礼盒") title = "新春礼盒";
    else if (title === "糕点&礼盒") title = "伴手礼盒";
    
    let subtitle = section.subtitle;
    if (title === "品牌周边") subtitle = "生活美学";
    else if (title === "新春礼盒") subtitle = "礼送心意";
    else if (title === "伴手礼盒") subtitle = "手作温情";
    else if (title === "手作茶歇") subtitle = "专享定制";
    else if (title === "招牌千层") subtitle = "层层甜蜜";
    else if (title === "全部商品") subtitle = "人气汇聚";
    else if (title === "生日蛋糕") subtitle = "建议提前预订";
    else if (title === "甜品和面包") subtitle = "麦香现烤";

    return {
      ...section,
      title,
      subtitle
    };
  });

  // 2. 按分类优先级权重排序
  const getWeight = (title: string): number => {
    if (title === "全部商品") return 100;
    if (title === "生日蛋糕") return 95;
    if (title === "招牌千层") return 90;
    if (title === "甜品和面包") return 85;
    if (title === "伴手礼盒") return 80;
    if (title === "手作茶歇") return 75;
    if (title.includes("礼盒")) return 70;
    if (title === "品牌周边") return 20;
    if (title === "其他") return 10;
    return 50; // 默认权重
  };

  return renamed.sort((a, b) => getWeight(b.title) - getWeight(a.title));
}

Page<ProductsPageData, WechatMiniprogram.IAnyObject>({
  data: {
    layoutStyle: getMiniappLayoutMetrics().pageShellStyle,
    searchText: "",
    storeName: SHOP_CONFIG.displayName,
    branchName: SHOP_CONFIG.branchName,
    businessHours: SHOP_CONFIG.businessHours,
    loaded: false,
    loading: false,
    loadFailed: false,
    categoriesDegraded: false,
    allProducts: [] as CatalogProduct[],
    categorySections: [] as CategorySectionView[],
    isSingleCategoryLayout: false,
    globalSearchResults: [] as ProductView[],
    activeCategoryId: ALL_PRODUCTS_CATEGORY_ID,
    activeCategoryTitle: "全部商品",
    activeCategorySubtitle: "门店在售商品",
    activeCategoryCountLabel: "0",
    activeSectionProducts: [] as ProductView[],
    activeProducts: [] as ProductView[],
    visibleProductCount: 0,
    hasMoreProducts: false,
    loadingMore: false,
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
  goHome() {
    wx.switchTab({ url: ROUTES.home });
  },
  async loadProducts() {
    if (this.data.loaded || this.data.loading) {
      return;
    }
    this.setData({ loading: true, loadFailed: false });
    try {
      // 商品与分类独立结算：主列表失败整页可重试，分类失败降级为本地分区分组
      const [productsResult, categoriesResult] = await Promise.allSettled([
        listProducts({ limit: FULL_CATALOG_LIMIT }),
        listProductCategories()
      ]);
      if (productsResult.status === "rejected") {
        this.setData({ loadFailed: true });
        return;
      }
      const products = productsResult.value;
      if (categoriesResult.status === "rejected") {
        const fallbackSections = refineCategorySections(buildSectionsFromProducts(products));
        this.setData({
          allProducts: products,
          categorySections: fallbackSections,
          isSingleCategoryLayout: fallbackSections.length <= 1,
          categoriesDegraded: true,
          loaded: true
        });
        if (fallbackSections.length) {
          this.applyActiveCategory(fallbackSections[0]);
        }
        return;
      }
      const categories = categoriesResult.value;
      
      const remoteSections = categories.map((category) => {
        let subtitle = "匠心推荐";
        const title = category.title;
        if (title.includes("蛋糕")) {
          subtitle = "建议提前预订";
        } else if (title.includes("面包") || title.includes("烘焙") || title.includes("甜品")) {
          subtitle = "麦香现烤";
        } else if (title.includes("礼盒") || title.includes("手作") || title.includes("糕点")) {
          subtitle = "手工茶点";
        } else if (title.includes("茶") || title.includes("饮")) {
          subtitle = "清爽特调";
        } else if (title.includes("周边")) {
          subtitle = "芸熙好物";
        } else if (title.includes("千层")) {
          subtitle = "层层甜蜜";
        }
        return {
          id: category.id,
          title: category.title,
          subtitle,
          products: [] as ProductView[],
          loaded: false,
          countLabel: String(category.productCount || 0),
          hasMatches: true
        };
      });

      const categorySections = [
        {
          id: ALL_PRODUCTS_CATEGORY_ID,
          title: "全部商品",
          subtitle: "人气汇聚",
          products: products.map((product, index) => toProductView(product, index === 0)),
          loaded: true,
          countLabel: String(products.length),
          hasMatches: products.length > 0
        },
        ...remoteSections
      ];
      
      const sortedSections = refineCategorySections(categorySections);
      this.setData({
        allProducts: products,
        categorySections: sortedSections,
        isSingleCategoryLayout: sortedSections.length <= 1,
        loaded: true
      });
      if (sortedSections.length) {
        this.applyActiveCategory(sortedSections[0]);
      }
    } finally {
      this.setData({ loading: false });
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
      categorySections: [],
      globalSearchResults: []
    });
    void this.loadProducts();
  },
  applyActiveCategory(section: CategorySectionView) {
    const visibleProductCount = getInitialVisibleCount(section.products);
    const activeProducts = getVisibleProducts(section.products, visibleProductCount);
    this.setData({
      activeCategoryId: section.id,
      activeCategoryTitle: section.title,
      activeCategorySubtitle: section.subtitle,
      activeCategoryCountLabel: section.countLabel,
      activeSectionProducts: section.products,
      visibleProductCount,
      activeProducts,
      hasMoreProducts: visibleProductCount < section.products.length,
      loadingMore: false
    });
    prefetchProductImages(activeProducts);
  },
  applySearch(keyword: string) {
    const searchText = keyword.trim().toLocaleLowerCase();
    if (!searchText) {
      this.setData({ globalSearchResults: [] });
      return;
    }

    const matchedProducts = this.data.allProducts.filter((product) =>
      getSearchText(product).toLocaleLowerCase().includes(searchText)
    );

    this.setData({
      globalSearchResults: matchedProducts.map((product, index) => toProductView(product, index === 0))
    });
  },
  onSearchInput(event: WechatMiniprogram.Input) {
    const value = String(event.detail.value || "");
    this.setData({ searchText: value });
    this.applySearch(value);
  },
  clearSearch() {
    this.setData({
      searchText: "",
      globalSearchResults: []
    });
  },
  async switchCategory(event: WechatMiniprogram.TouchEvent) {
    const categoryId = event.currentTarget.dataset.categoryId as string;
    const sectionIndex = this.data.categorySections.findIndex((item) => item.id === categoryId);
    if (sectionIndex === -1) {
      return;
    }

    const section = this.data.categorySections[sectionIndex];
    
    this.setData({
      searchText: "",
      globalSearchResults: []
    });

    if (!section.loaded && section.id !== ALL_PRODUCTS_CATEGORY_ID) {
      this.setData({ loading: true });
      try {
        const products = await listProducts({ categoryId: section.id });
        const productViews = products.map((product, index) => toProductView(product, index === 0));

        // 将新商品合并到 allProducts 和“全部商品”分区
        const { allProducts, categorySections } = this.data;
        const existingIds = new Set(allProducts.map((p) => p.id));
        const newProducts = products.filter((p) => !existingIds.has(p.id));

        if (newProducts.length > 0) {
          const updatedAllProducts = [...allProducts, ...newProducts];
          const allSectionIndex = categorySections.findIndex((s) => s.id === ALL_PRODUCTS_CATEGORY_ID);
          
          if (allSectionIndex !== -1) {
            const allSection = categorySections[allSectionIndex];
            const updatedAllSectionProducts = [...allSection.products, ...newProducts.map((product) => toProductView(product))];
            
            this.setData({
              allProducts: updatedAllProducts,
              [`categorySections[${allSectionIndex}].products`]: updatedAllSectionProducts,
              [`categorySections[${allSectionIndex}].countLabel`]: String(updatedAllSectionProducts.length)
            });
          }
        }

        const key = `categorySections[${sectionIndex}]`;
        const updatedSection = {
          ...section,
          products: productViews,
          loaded: true,
          countLabel: String(productViews.length),
          hasMatches: productViews.length > 0
        };
        this.setData({ [key]: updatedSection });
        this.applyActiveCategory(updatedSection);
      } catch {
        // 分类懒加载失败：保留全部商品并标记降级，不清空当前内容
        this.setData({ categoriesDegraded: true });
        wx.showToast({ title: "分类加载失败，已展示全部商品", icon: "none" });
        this.applyActiveCategory(section);
      } finally {
        this.setData({ loading: false });
      }
      return;
    }

    this.applyActiveCategory(section);
  },
  switchToAll() {
    // 分类空态兜底：一键切回全部商品
    this.setData({
      searchText: "",
      globalSearchResults: [],
      activeCategoryId: ALL_PRODUCTS_CATEGORY_ID
    });
    const allSection = this.data.categorySections.find((section) => section.id === ALL_PRODUCTS_CATEGORY_ID);
    if (allSection) {
      this.applyActiveCategory(allSection);
    }
  },
  loadMoreProducts() {
    if (this.data.loadingMore || !this.data.hasMoreProducts) {
      return;
    }
    const visibleProductCount = Math.min(
      this.data.visibleProductCount + PRODUCTS_PAGE_SIZE,
      this.data.activeSectionProducts.length
    );
    const activeProducts = getVisibleProducts(this.data.activeSectionProducts, visibleProductCount);
    this.setData({
      loadingMore: true,
      visibleProductCount,
      activeProducts,
      hasMoreProducts: visibleProductCount < this.data.activeSectionProducts.length
    });
    prefetchProductImages(activeProducts.slice(Math.max(0, visibleProductCount - PRODUCTS_PAGE_SIZE)));
    this.setData({ loadingMore: false });
  },
  refreshCartSummary() {
    const cartItems = getCartItems();
    const cartItemCount = cartItems.reduce((sum, item) => sum + item.quantity, 0);
    const cartTotalFen = cartItems.reduce((sum, item) => sum + item.priceFen * item.quantity, 0);
    this.setData({
      cartItemCount,
      cartTotalText: formatFen(cartTotalFen),
      cartSummaryText: cartItemCount > 0 ? cartItemCount + " 件已选 · 闪送费下单前确认" : "还没有选择商品",
      cartBarVisible: cartItemCount > 0
    });
  },
  quickAddProduct(event: WechatMiniprogram.TouchEvent) {
    const productId = event.currentTarget.dataset.id as string;
    if (!productId) {
      return;
    }
    const product =
      getProductFromViews(this.data.activeSectionProducts, productId) ||
      getProductFromViews(this.data.globalSearchResults, productId) ||
      this.data.allProducts.find((item) => item.id === productId);
    if (!product || !product.isActive || product.stock <= 0) {
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
      stock: product.stock,
    });
    this.refreshCartSummary();
    wx.showToast({ title: "已加入预订单", icon: "success" });
  },
  onProductImageError(event: WechatMiniprogram.TouchEvent) {
    // 图片运行时加载失败：按商品定位全部命中项并切换占位，保持固定宽高
    const productId = event.currentTarget.dataset.id as string;
    if (!productId) {
      return;
    }
    const updates: Record<string, boolean> = {};
    this.data.categorySections.forEach((section, sectionIndex) => {
      section.products.forEach((product, productIndex) => {
        if (product.id === productId && !product.imageFailed) {
          updates[`categorySections[${sectionIndex}].products[${productIndex}].imageFailed`] = true;
        }
      });
    });
    this.data.globalSearchResults.forEach((product, resultIndex) => {
      if (product.id === productId && !product.imageFailed) {
        updates[`globalSearchResults[${resultIndex}].imageFailed`] = true;
      }
    });
    this.data.activeProducts.forEach((product, productIndex) => {
      if (product.id === productId && !product.imageFailed) {
        updates[`activeProducts[${productIndex}].imageFailed`] = true;
      }
    });
    if (Object.keys(updates).length > 0) {
      this.setData(updates);
    }
  },
  openProduct(event: WechatMiniprogram.TouchEvent) {
    const productId = event.currentTarget.dataset.id as string;
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
