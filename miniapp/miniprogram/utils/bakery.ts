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
