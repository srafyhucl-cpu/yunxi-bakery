import { expect, request, test, type Page } from "@playwright/test";

const adminToken = process.env.ADMIN_E2E_TOKEN || "";
const apiOrigin = process.env.ADMIN_E2E_API_ORIGIN || "http://127.0.0.1:7001";
const expectedReadyStatus = Number(process.env.ADMIN_E2E_EXPECT_READY_STATUS || "503");

async function login(page: Page): Promise<void> {
  await page.goto("login?redirect=/orders");
  await page.getByLabel("管理员 Token").fill(adminToken);
  await page.getByRole("button", { name: "登录" }).click();
  await page.waitForURL(/\/admin\/orders/);
}

test.describe("后台管理最小门禁", () => {
  test.beforeEach(() => {
    test.skip(!adminToken, "设置 ADMIN_E2E_TOKEN 后执行真实后台 E2E");
  });

  test("登录后可以进入订单页并加载真实订单接口", async ({ page }) => {
    await login(page);
    await expect(page.getByTestId("orders-page")).toBeVisible();
    await expect(page.getByTestId("orders-table")).toBeVisible();
    await expect(page.getByTestId("orders-page").getByText("订单管理")).toBeVisible();
  });

  test("向量重建接口拒绝未登录请求并接受 Cookie 会话", async ({ page }) => {
    const anonymousApi = await request.newContext({ baseURL: apiOrigin });
    const anonymousResponse = await anonymousApi.get("/api/admin/vector-build-status");
    expect(anonymousResponse.status()).toBe(401);
    await anonymousApi.dispose();

    await login(page);
    const authenticatedResponse = await page.request.get("/api/admin/vector-build-status");
    expect(authenticatedResponse.status()).toBe(200);
    expect((await authenticatedResponse.json()).code).toBe(200);
  });

  test("ready 状态遵守运行时门禁语义", async () => {
    const api = await request.newContext({ baseURL: apiOrigin });
    const response = await api.get("/ready");
    expect(response.status()).toBe(expectedReadyStatus);
    const payload = await response.json();
    if (expectedReadyStatus === 503) {
      expect(payload.status).toBe("degraded");
    } else {
      expect(expectedReadyStatus).toBe(200);
      expect(payload.status).toBe("ready");
    }
    await api.dispose();
  });
});
