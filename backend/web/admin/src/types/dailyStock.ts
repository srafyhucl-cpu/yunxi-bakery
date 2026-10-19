export interface DailyStockItem {
  product_id: string;
  item_id: number;
  title: string;
  price_fen: number;
  is_active: number;
  youzan_stock: number;
  total_qty: number;
  reserved_qty: number;
  available_qty: number;
  configured: boolean;
  updated_by: string;
  updated_at: string | null;
}

export interface DailyStockListPayload {
  date: string;
  items: DailyStockItem[];
}
