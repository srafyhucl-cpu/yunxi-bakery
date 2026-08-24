import http from "@/services/http";

interface WrappedAssetResponse {
  code: number;
  data: {
    imageUrl: string;
  };
}

export const assetsService = {
  async uploadDecorationImage(file: File): Promise<string> {
    const form = new FormData();
    form.append("file", file);
    const response = await http.post<WrappedAssetResponse>("/shop-config/assets", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return response.data.data.imageUrl;
  },
};
