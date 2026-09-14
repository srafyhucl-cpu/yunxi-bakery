import type { CatalogProduct } from "../types/catalog";

const BAKERY_PATTERNS = ["cake-pink", "cake-cream", "cake-choco", "cake-yellow"] as const;

export function getBakeryPattern(indexOrSeed: number | string): typeof BAKERY_PATTERNS[number] {
  const seed = typeof indexOrSeed === "number"
    ? indexOrSeed
    : indexOrSeed.split("").reduce((sum, char) => sum + char.charCodeAt(0), 0);
  return BAKERY_PATTERNS[Math.abs(seed) % BAKERY_PATTERNS.length];
}

export function getProductImageClass(product: CatalogProduct, index = 0): string {
  if (product.imageUrl) {
    return "";
  }
  const token = `${product.id}-${index}-${product.categoryId}`;
  return getBakeryPattern(token);
}

type PurchaseHintProduct = Pick<CatalogProduct, "title"> &
  Partial<Pick<CatalogProduct, "categoryName" | "tags" | "stock" | "isActive" | "isPurchasable">>;

export function isProductPurchasable(product: PurchaseHintProduct): boolean {
  return product.isPurchasable !== false;
}

const LOW_STOCK_THRESHOLD = 5;

const ACCESSORY_TITLE_PATTERN =
  /(蜡烛|餐具|刀叉|餐盘|纸盘|生日帽|贺卡|打包盒|包装盒|摆件|插件|玩具|装饰物)/;
const MADE_TO_ORDER_PATTERN =
  /(蛋糕|千层|慕斯|芝士|奶油|面包|吐司|贝果|饼干|曲奇|糕点|酥|甜品|下午茶|礼盒)/;

export function isAccessoryProduct(product: PurchaseHintProduct): boolean {
  if (!isProductPurchasable(product)) {
    return false;
  }
  const title = product.title.trim();
  return ACCESSORY_TITLE_PATTERN.test(title) && !MADE_TO_ORDER_PATTERN.test(title);
}

export function getProductPurchaseHint(product: PurchaseHintProduct): string {
  if (!isProductPurchasable(product)) {
    return "仅用于原料或产品展示，不参与下单";
  }
  if (isAccessoryProduct(product)) {
    return typeof product.stock === "number" && product.stock > 0
      ? "现货可直接下单，闪送费下单前确认"
      : "配件库存以下单前确认为准";
  }
  if ((product.tags || []).some((tag) => tag.includes("现货") || tag.includes("当日"))) {
    return "有现货时可当天取，建议先确认";
  }
  const categoryName = product.categoryName || "";
  if (MADE_TO_ORDER_PATTERN.test(product.title) || MADE_TO_ORDER_PATTERN.test(categoryName)) {
    return "建议提前1天预订";
  }
  return "自提价展示，闪送费下单前确认";
}

// 卡片标签只表达可核对事实；没有额外事实时返回空串，不把“可预订”这类默认能力当卖点重复展示。
export function getProductAvailabilityLabel(product: PurchaseHintProduct): string {
  if (!isProductPurchasable(product)) {
    return "仅供展示";
  }
  if (product.isActive === false) {
    return "已下架";
  }
  const stock = product.stock;
  if (typeof stock === "number" && stock <= 0) {
    return "暂时售罄";
  }
  if ((product.tags || []).some((tag) => tag.trim() === "现货")) {
    return "现货";
  }
  if (isAccessoryProduct(product)) {
    return typeof stock === "number" && stock > 0 ? "现货" : "";
  }
  if (typeof stock === "number" && stock <= LOW_STOCK_THRESHOLD) {
    return "仅余 " + stock + " 件";
  }
  return "";
}

// 非卖品没有真实售价：同步数据里的虚拟占位价与库存数会把展示条目伪装成可售商品。
export function getProductPriceText(product: PurchaseHintProduct, priceText: string): string {
  return isProductPurchasable(product) ? priceText : "非卖品";
}

// 按钮动作必须与履约口径一致：现货配件当场加购，现做商品走预订。
export function getProductActionLabel(product: PurchaseHintProduct): string {
  if (!isProductPurchasable(product)) {
    return "查看";
  }
  if (product.isActive === false) {
    return "查看";
  }
  if (typeof product.stock === "number" && product.stock <= 0) {
    return "查看";
  }
  return isAccessoryProduct(product) ? "加入购物车" : "预订";
}

// 加购提示跟随动作文案，避免“加入购物车”后提示“已加入预订单”。
export function getProductAddToastLabel(product: PurchaseHintProduct): string {
  if (!isProductPurchasable(product)) {
    return "仅供展示，不可加入购物车";
  }
  return isAccessoryProduct(product) ? "已加入购物车" : "已加入预订单";
}

// 首页卡片宽度有限，只保留一句短口径供扫读。
export function getProductCardTip(product: PurchaseHintProduct): string {
  if (!isProductPurchasable(product)) {
    return "仅供展示 · 如有需要请联系客服";
  }
  if (product.isActive === false || (typeof product.stock === "number" && product.stock <= 0)) {
    return "可咨询客服或先看其他商品";
  }
  if (isAccessoryProduct(product)) {
    return typeof product.stock === "number" && product.stock > 0 ? "现货 · 闪送费另计" : "库存以下单前确认为准";
  }
  if ((product.tags || []).some((tag) => tag.includes("现货") || tag.includes("当日"))) {
    return "当天可取 · 建议先确认";
  }
  return "提前1天预订 · 闪送/自取";
}

// 详情页展示过滤：规格与标签共用后端词表时去通用词与标题重复，尺寸等真实选项保留
const DETAIL_GENERIC_TOKENS = new Set([
  "商品",
  "价格",
  "推荐",
  "蛋糕",
  "在售",
  "现做"
]);

function isDisplayToken(token: string, product: CatalogProduct): boolean {
  const text = token.trim();
  if (!text || DETAIL_GENERIC_TOKENS.has(text)) {
    return false;
  }
  return text !== product.title.trim() && text !== product.subtitle.trim();
}

export function getDisplaySpecs(product: CatalogProduct): string[] {
  return product.specs.map((spec) => spec.trim()).filter((spec) => isDisplayToken(spec, product));
}

export function getDisplayTags(product: CatalogProduct): string[] {
  const specSet = new Set(product.specs.map((spec) => spec.trim()));
  return product.tags
    .map((tag) => tag.trim())
    .filter((tag) => isDisplayToken(tag, product) && !specSet.has(tag));
}

export interface DescriptionBlock {
  text: string;
  isHeading: boolean;
}

function isJunkDescriptionLine(line: string): boolean {
  // 有赞同步原文中的非展示信息：直购链接、营销串、头部已展示字段、标签重复、无信息占位
  if (line.startsWith("http://") || line.startsWith("https://") || line.includes("h5.youzan.com")) {
    return true;
  }
  if (line.includes("[UMP")) {
    return true;
  }
  if (/下单链接/.test(line)) {
    return true;
  }
  if (/^商品名称：/.test(line) || /^在售状态：/.test(line)) {
    return true;
  }
  if (/^商品特征/.test(line)) {
    return true;
  }
  if (/暂无特殊定制属性/.test(line)) {
    return true;
  }
  if (/SPU 自定义属性/.test(line)) {
    return true;
  }
  return false;
}

export function getDescriptionBlocks(description: string): DescriptionBlock[] {
  return description
    .split(/\r?\n/)
    .map((line) => line.trim().replace(/^[-\u2022]\s*/, ""))
    .filter((line) => line.length > 0 && !isJunkDescriptionLine(line))
    .map((line) => ({ text: line, isHeading: /：$/.test(line) }));
}
