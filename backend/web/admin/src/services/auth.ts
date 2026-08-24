import http from "./http";

import type { AdminProfile } from "@/stores/auth";

interface AuthMeResponse {
  ok: boolean;
  data: AdminProfile;
}

interface AuthActionResponse {
  ok: boolean;
  message: string;
  data?: AdminProfile;
}

export const authService = {
  async getProfile(): Promise<AdminProfile> {
    const response = await http.get<AuthMeResponse>("/me");
    return response.data.data;
  },

  async login(token: string): Promise<AdminProfile> {
    const response = await http.post<AuthActionResponse>("/auth/login", { token });
    return response.data.data || { name: "管理员", role: "admin" };
  },

  async logout(): Promise<void> {
    await http.post<AuthActionResponse>("/auth/logout");
  },
};
