export interface CatalogCategory {
  id: string;
  title: string;
  iconText: string;
}

/** 商品规格：来自有赞 SKU，尺寸决定价格，其余规格只选具体型号。 */
export interface CatalogVariant {
  id: string;
  property: string;
  name: string;
  priceFen: number;
  stock: number;
}

/** 定制选项：蛋糕胚/夹心/甜度等，选项自带加价。 */
export interface CatalogOptionChoice {
  id: string;
  name: string;
  priceDeltaFen: number;
}

export interface CatalogOptionGroup {
  name: string;
  required: boolean;
  multiple: boolean;
  choices: CatalogOptionChoice[];
}

export type CatalogOrderMode = "direct" | "preorder";

export interface CatalogProduct {
  id: string;
  title: string;
  subtitle: string;
  imageUrl: string;
  priceFen: number;
  soldText: string;
  categoryId: string;
  categoryName?: string;
  stock: number;
  isActive: boolean;
  isPurchasable?: boolean;
  tags: string[];
  description: string;
  specs: string[];
  notices: string[];
  orderMode?: CatalogOrderMode;
  variants?: CatalogVariant[];
  options?: CatalogOptionGroup[];
}
