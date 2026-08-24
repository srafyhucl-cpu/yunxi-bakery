export interface CatalogCategory {
  id: string;
  title: string;
  iconText: string;
}

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
  tags: string[];
  description: string;
  specs: string[];
  notices: string[];
}
