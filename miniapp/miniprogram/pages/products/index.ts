import { ROUTES } from "../../constants/routes";
import { SHOP_CONFIG } from "../../config/shop";
import { getMiniappLayoutMetrics } from "../../utils/layout";
import { getCategoryById } from "../../utils/catalog";
import { calculateDistanceKm, formatDistanceKm } from "../../utils/location";
import { formatFen } from "../../utils/money";
import { syncCustomTabBar } from "../../utils/tab-bar";
import { listProductCategories, listProducts, type ProductCategory } from "../../services/products";
import { getProductImageClass } from "../../utils/bakery";
import type { CatalogProduct } from "../../types/catalog";

interface CategorySection {
  id: string;
  title: string;
  subtitle: string;
  products: CatalogProduct[];
}

interface ProductView extends CatalogProduct {
  priceText: string;
  imageClass: string;
  badgeText: string;
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
  storeDistance: string;
  deliveryMode: "delivery" | "pickup";
  loaded: boolean;
  loading: boolean;
  allProducts: CatalogProduct[];
  categorySections: CategorySectionView[];
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
}

const INITIAL_PRODUCTS_PER_SECTION = 12;
const PRODUCTS_PAGE_SIZE = 12;
const ALL_PRODUCTS_CATEGORY_ID = "all";
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
    subtitle: "当前接口返回的真实商品",
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
      subtitle = "新鲜现做";
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



function toProductView(product: CatalogProduct): ProductView {
  return {
    ...product,
    priceText: formatFen(product.priceFen),
    imageClass: getProductImageClass(product),
    badgeText: product.tags[0] ?? "现做"
  };
}

function buildSectionView(section: CategorySection): CategorySectionView {
  return {
    ...section,
    countLabel: String(section.products.length),
    products: section.products.map(toProductView),
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

function getUserLocation(): Promise<WechatMiniprogram.GetLocationSuccessCallbackResult> {
  return new Promise((resolve, reject) => {
    wx.getLocation({
      type: "gcj02",
      success: resolve,
      fail: reject
    });
  });
}

function productMatchesSearch(product: CatalogProduct, keyword: string): boolean {
  const normalizedKeyword = keyword.trim().toLocaleLowerCase();
  if (!normalizedKeyword) {
    return true;
  }
  return getSearchText(product).toLocaleLowerCase().includes(normalizedKeyword);
}

function refineCategorySections(sections: CategorySectionView[]): CategorySectionView[] {
  // 1. Rename category titles for aesthetic purity
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
    else if (title === "生日蛋糕") subtitle = "新鲜现做";
    else if (title === "甜品和面包") subtitle = "麦香现烤";

    return {
      ...section,
      title,
      subtitle
    };
  });

  // 2. Sort by category priority weight
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
    return 50; // fallback weight
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
    storeDistance: "距离待定位",
    deliveryMode: "delivery",
    loaded: false,
    loading: false,
    allProducts: [] as CatalogProduct[],
    categorySections: [] as CategorySectionView[],
    globalSearchResults: [] as ProductView[],
    activeCategoryId: ALL_PRODUCTS_CATEGORY_ID,
    activeCategoryTitle: "全部商品",
    activeCategorySubtitle: "当前接口返回的真实商品",
    activeCategoryCountLabel: "0",
    activeSectionProducts: [] as ProductView[],
    activeProducts: [] as ProductView[],
    visibleProductCount: 0,
    hasMoreProducts: false,
    loadingMore: false
  },
  onLoad() {
    void this.refreshStoreDistance();
    void this.loadProducts();
  },
  onShow() {
    syncCustomTabBar(ROUTES.products);
  },
  goHome() {
    wx.switchTab({ url: ROUTES.home });
  },
  async loadProducts() {
    if (this.data.loaded || this.data.loading) {
      return;
    }
    this.setData({ loading: true });
    try {
      const [products, categories] = await Promise.all([
        listProducts(),
        listProductCategories()
      ]);
      
      const remoteSections = categories.map((category) => {
        let subtitle = "匠心推荐";
        const title = category.title;
        if (title.includes("蛋糕")) {
          subtitle = "新鲜现做";
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
          products: products.map(toProductView),
          loaded: true,
          countLabel: String(products.length),
          hasMatches: products.length > 0
        },
        ...remoteSections
      ];
      
      const sortedSections = refineCategorySections(categorySections);
      this.setData({ allProducts: products, categorySections: sortedSections, loaded: true });
      if (sortedSections.length) {
        this.applyActiveCategory(sortedSections[0]);
      }
    } finally {
      this.setData({ loading: false });
    }
  },
  async refreshStoreDistance() {
    try {
      const location = await getUserLocation();
      const distanceKm = calculateDistanceKm(
        { latitude: location.latitude, longitude: location.longitude },
        SHOP_CONFIG.storeLocation
      );
      this.setData({ storeDistance: formatDistanceKm(distanceKm) });
    } catch {
      this.setData({ storeDistance: "距离待定位" });
    }
  },
  applyActiveCategory(section: CategorySectionView) {
    this.setData({
      activeCategoryId: section.id,
      activeCategoryTitle: section.title,
      activeCategorySubtitle: section.subtitle,
      activeCategoryCountLabel: section.countLabel
    });
    prefetchProductImages(section.products);
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
      globalSearchResults: matchedProducts.map(toProductView)
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
        const productViews = products.map(toProductView);

        // Merge new products into allProducts and the "All" section
        const { allProducts, categorySections } = this.data;
        const existingIds = new Set(allProducts.map((p) => p.id));
        const newProducts = products.filter((p) => !existingIds.has(p.id));

        if (newProducts.length > 0) {
          const updatedAllProducts = [...allProducts, ...newProducts];
          const allSectionIndex = categorySections.findIndex((s) => s.id === ALL_PRODUCTS_CATEGORY_ID);
          
          if (allSectionIndex !== -1) {
            const allSection = categorySections[allSectionIndex];
            const updatedAllSectionProducts = [...allSection.products, ...newProducts.map(toProductView)];
            
            this.setData({
              allProducts: updatedAllProducts,
              [`categorySections[${allSectionIndex}].products`]: updatedAllSectionProducts,
              [`categorySections[${allSectionIndex}].countLabel`]: String(updatedAllSectionProducts.length)
            });
          }
        }

        const key = `categorySections[${sectionIndex}]`;
        this.setData({
          [key]: {
            ...section,
            products: productViews,
            loaded: true,
            countLabel: String(productViews.length),
            hasMatches: productViews.length > 0
          }
        });
      } finally {
        this.setData({ loading: false });
      }
    }

    this.setData({ activeCategoryId: categoryId });
  },
  setDeliveryMode(event: WechatMiniprogram.TouchEvent) {
    const mode = event.currentTarget.dataset.mode as "delivery" | "pickup";
    this.setData({ deliveryMode: mode });
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
  openProduct(event: WechatMiniprogram.TouchEvent) {
    const productId = event.currentTarget.dataset.id as string;
    wx.navigateTo({
      url: `${ROUTES.productDetail}?id=${productId}`
    });
  },
  goToCart() {
    wx.switchTab({ url: ROUTES.cart });
  },
  goToChat() {
    wx.switchTab({ url: ROUTES.chat });
  }
});
