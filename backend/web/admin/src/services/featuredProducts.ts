import http from "./http";
import { productsService } from "./products";

import type { ProductListItem } from "@/types/product";

interface FeaturedProductsResponse {
  code: number;
  data: string[];
}

interface SaveFeaturedProductsResponse {
  code: number;
  message: string;
  data: string[];
}

export const featuredProductsService = {
  async getFeaturedProducts(): Promise<string[]> {
    const response = await http.get<FeaturedProductsResponse>("/shop-config/featured-products");
    return response.data.data;
  },

  async saveFeaturedProducts(products: string[]): Promise<SaveFeaturedProductsResponse> {
    const response = await http.post<SaveFeaturedProductsResponse>("/shop-config/featured-products", {
      products,
    });
    return response.data;
  },

  async searchCandidates(keyword: string): Promise<ProductListItem[]> {
    const payload = await productsService.listProducts(1, keyword);
    return payload.items;
  },
};
