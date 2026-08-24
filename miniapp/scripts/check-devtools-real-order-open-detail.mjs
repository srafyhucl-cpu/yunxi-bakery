import fs from "node:fs";
import path from "node:path";
import automator from "miniprogram-automator";

const root = process.cwd();
const reportsRoot = path.join(root, "reports", "button-runtime");
const wsEndpoint = process.env.MINIAPP_AUTOMATOR_WS || "ws://127.0.0.1:9420";
const targetUserId = process.env.MINIAPP_ORDER_USER_ID || "miniapp-demo-user-999deb52ebeb";
const targetOrderId = process.env.MINIAPP_ORDER_ID || "mp_20260621103755_722c0d60";

function nowStamp() {
  return new Date()
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\..+$/, "")
    .replace("T", "-");
}

async function main() {
  fs.mkdirSync(reportsRoot, { recursive: true });
  const miniProgram = await automator.connect({ wsEndpoint });
  let runtimeResult;
  try {
    runtimeResult = await miniProgram.evaluate(
      async function (options) {
        const session = {
          userId: options.targetUserId,
          openid: options.targetUserId.replace(/^wx_/, ""),
          sessionReady: true,
          isDemo: false,
        };
        const originalMiniappSession = wx.getStorageSync("miniappSession");
        const originalMiniappUserId = wx.getStorageSync("miniappUserId");
        const originalUseLocalApi = wx.getStorageSync("yunxiUseLocalApi");

        function sleep(ms) {
          return new Promise(function (resolve) {
            setTimeout(resolve, ms);
          });
        }

        async function waitForPage(route, timeoutMs) {
          const startedAt = Date.now();
          while (Date.now() - startedAt < timeoutMs) {
            const pages = getCurrentPages();
            const page = pages[pages.length - 1];
            if (page && page.route === route) {
              return page;
            }
            await sleep(200);
          }
          throw new Error("Timed out waiting for " + route);
        }

        async function waitFor(predicate, timeoutMs, message) {
          const startedAt = Date.now();
          while (Date.now() - startedAt < timeoutMs) {
            if (predicate()) {
              return;
            }
            await sleep(200);
          }
          throw new Error(message);
        }

        wx.setStorageSync("miniappSession", session);
        wx.setStorageSync("miniappUserId", session.userId);
        wx.removeStorageSync("yunxiUseLocalApi");

        try {
          await new Promise(function (resolve) {
            wx.reLaunch({
              url: "/pages/orders/index",
              complete: resolve,
            });
          });
          const ordersPage = await waitForPage("pages/orders/index", 10000);
          if (typeof ordersPage.onShow === "function") {
            ordersPage.onShow();
          }
          await waitFor(
            function () {
              return !ordersPage.data.loading && Array.isArray(ordersPage.data.allOrders);
            },
            12000,
            "Timed out waiting for orders list loading=false"
          );
          const orders = ordersPage.data.allOrders || [];
          const order =
            orders.find(function (item) {
              return item.id === options.targetOrderId;
            }) || orders[0];
          if (!order) {
            throw new Error("No orders loaded for " + session.userId);
          }

          ordersPage.openOrder({
            currentTarget: {
              dataset: {
                id: order.id,
              },
            },
          });
          const detailPage = await waitForPage("pages/order-detail/index", 10000);
          await waitFor(
            function () {
              return !detailPage.data.loading && Boolean(detailPage.data.order);
            },
            12000,
            "Timed out waiting for order detail loading=false"
          );
          const detailOrder = detailPage.data.order;

          return {
            storageDuringCheck: {
              miniappSession: wx.getStorageSync("miniappSession"),
              miniappUserId: wx.getStorageSync("miniappUserId"),
              yunxiUseLocalApi: wx.getStorageSync("yunxiUseLocalApi"),
            },
            ordersPage: {
              route: ordersPage.route,
              loading: Boolean(ordersPage.data.loading),
              allOrderCount: orders.length,
              filteredOrderCount: Array.isArray(ordersPage.data.filteredOrders)
                ? ordersPage.data.filteredOrders.length
                : 0,
              activeFilter: ordersPage.data.activeFilter,
              containsTargetOrder: orders.some(function (item) {
                return item.id === options.targetOrderId;
              }),
              selectedOrder: {
                id: order.id,
                status: order.status,
                statusText: order.statusText,
                paymentStatus: order.paymentStatus,
                paymentStatusText: order.paymentStatusText,
                totalFen: order.totalFen,
                totalText: order.totalText,
                itemTitle: order.itemTitle,
                itemCount: order.itemCount,
                canPay: Boolean(order.canPay),
                canCancel: Boolean(order.canCancel),
              },
            },
            detailPage: {
              route: detailPage.route,
              loading: Boolean(detailPage.data.loading),
              orderId: detailPage.data.orderId,
              hasOrder: Boolean(detailOrder),
              order: detailOrder
                ? {
                    id: detailOrder.id,
                    status: detailOrder.status,
                    statusText: detailOrder.statusText,
                    paymentStatus: detailOrder.paymentStatus,
                    paymentStatusText: detailOrder.paymentStatusText,
                    paymentMethod: detailOrder.paymentMethod,
                    paymentMethodText: detailOrder.paymentMethodText,
                    totalFen: detailOrder.totalFen,
                    totalText: detailOrder.totalText,
                    itemTitle: detailOrder.itemTitle,
                    itemCount: detailOrder.itemCount,
                    itemsViewCount: Array.isArray(detailOrder.itemsView)
                      ? detailOrder.itemsView.length
                      : 0,
                    progressStepCount: Array.isArray(detailOrder.progressSteps)
                      ? detailOrder.progressSteps.length
                      : 0,
                    timelineCount: Array.isArray(detailOrder.timeline)
                      ? detailOrder.timeline.length
                      : 0,
                    canPay: Boolean(detailOrder.canPay),
                    canCancel: Boolean(detailOrder.canCancel),
                  }
                : null,
            },
          };
        } finally {
          if (originalMiniappSession) {
            wx.setStorageSync("miniappSession", originalMiniappSession);
          } else {
            wx.removeStorageSync("miniappSession");
          }
          if (originalMiniappUserId) {
            wx.setStorageSync("miniappUserId", originalMiniappUserId);
          } else {
            wx.removeStorageSync("miniappUserId");
          }
          if (originalUseLocalApi) {
            wx.setStorageSync("yunxiUseLocalApi", originalUseLocalApi);
          } else {
            wx.removeStorageSync("yunxiUseLocalApi");
          }
        }
      },
      {
        targetUserId,
        targetOrderId,
      }
    );
  } finally {
    await miniProgram.disconnect();
  }

  const selectedOrder = runtimeResult.ordersPage.selectedOrder;
  const detailOrder = runtimeResult.detailPage.order;
  const checks = [
    {
      name: "orders page loaded real user orders",
      ok:
        runtimeResult.ordersPage.route === "pages/orders/index" &&
        !runtimeResult.ordersPage.loading &&
        runtimeResult.ordersPage.allOrderCount > 0,
    },
    {
      name: "orders list contains target order",
      ok: runtimeResult.ordersPage.containsTargetOrder && selectedOrder.id === targetOrderId,
    },
    {
      name: "order card opens detail page",
      ok:
        runtimeResult.detailPage.route === "pages/order-detail/index" &&
        runtimeResult.detailPage.orderId === selectedOrder.id,
    },
    {
      name: "detail page loaded matching order",
      ok:
        runtimeResult.detailPage.hasOrder &&
        detailOrder?.id === selectedOrder.id &&
        detailOrder?.totalFen === selectedOrder.totalFen &&
        detailOrder?.itemTitle === selectedOrder.itemTitle,
    },
    {
      name: "detail shows items and timeline",
      ok: detailOrder?.itemsViewCount > 0 && detailOrder?.timelineCount > 0,
    },
  ];

  const report = {
    traceId: "20260621-real-order-open-detail-runtime",
    generatedAt: new Date().toISOString(),
    wsEndpoint,
    targetUserId,
    targetOrderId,
    status: checks.every((check) => check.ok) ? "pass" : "fail",
    checks,
    result: runtimeResult,
    notes: [
      "This runtime check uses an existing production miniapp order and does not create, cancel, or pay any order.",
      "It temporarily switches DevTools storage to the order owner demo session, opens the orders tab, calls the page openOrder handler, verifies order detail, then restores previous storage.",
      "It proves the orders list card-to-detail navigation and read path for this known order in DevTools runtime.",
    ],
  };

  const stamp = nowStamp();
  const reportPath = path.join(reportsRoot, `real-order-open-detail-${stamp}.json`);
  const payload = `${JSON.stringify(report, null, 2)}\n`;
  fs.writeFileSync(reportPath, payload, "utf8");
  fs.writeFileSync(path.join(reportsRoot, "real-order-open-detail-latest.json"), payload, "utf8");
  console.log(`Real order open-detail runtime ${report.status}: ${selectedOrder.id}`);
  console.log(`Report: ${reportPath}`);
  if (report.status !== "pass") {
    process.exit(1);
  }
}

main();
