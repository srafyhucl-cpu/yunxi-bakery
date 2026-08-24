export interface ProductListItem {
  id: number;
  category: string;
  contentType: string;
  title: string;
  content: string;
  keywords: string;
  priority: number;
  isActive: boolean;
  youzanItemId: string;
  itemNo: string;
  priceFen: number | null;
  stock: number | null;
  soldNum: number;
  lastSyncSource: string;
  lastSyncRef: string;
  vectorSyncStatus: string;
  updatedAt: string;
}

export interface ProductListPayload {
  items: ProductListItem[];
  total: number;
  totalActive: number;
  totalInactive: number;
  page: number;
  pageSize: number;
}
