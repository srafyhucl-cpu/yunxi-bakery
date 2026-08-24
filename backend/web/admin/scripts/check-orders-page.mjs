import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const ordersPage = readFileSync(resolve("src/pages/orders/OrdersPage.vue"), "utf8");

const requiredSnippets = [
  "data-testid=\"orders-page\"",
  "data-testid=\"orders-board\"",
  ":data-testid=\"`orders-board-filter-${card.key}`\"",
  "ORDER_BOARD_FILTERS",
  "activeBoardFilter",
  "getSummary",
  "ordersService.listOrders",
  "summaryTotalCount",
  "activeBoardFilter.value",
  "data-testid=\"orders-search-input\"",
  "data-testid=\"orders-search-submit\"",
  "data-testid=\"orders-reset-filters\"",
  "data-testid=\"orders-refresh\"",
  "data-testid=\"orders-expire-timeout-unpaid\"",
  "expireTimeoutUnpaid",
  "data-testid=\"orders-table\"",
  ":data-testid=\"`orders-row-status-${row.id}`\"",
  "paymentStatusTagType(row.paymentStatus)",
  "paymentStatusLabel(row.paymentStatus)",
  ":data-testid=\"`orders-row-title-${row.id}`\"",
  ":data-testid=\"`orders-open-detail-${row.id}`\"",
  ":data-testid=\"`orders-update-status-${row.id}-${action.status}`\"",
  ":data-testid=\"`orders-expire-unpaid-${row.id}`\"",
  "data-testid=\"orders-detail-drawer\"",
  ":data-testid=\"`orders-detail-status-${selectedOrder.id}`\"",
  "selectedOrder.paymentStatus",
  "selectedOrder.paymentMethod",
  "selectedOrder.paymentPaidAt",
  "selectedOrder.paymentExpiredAt",
  "selectedOrder.paymentExpiredReason",
  "selectedOrder.timeline",
  "timelineLabel(event.status)",
  ":data-testid=\"`orders-detail-update-status-${selectedOrder.id}-${action.status}`\"",
  ":data-testid=\"`orders-detail-expire-unpaid-${selectedOrder.id}`\"",
];

const missing = requiredSnippets.filter((snippet) => !ordersPage.includes(snippet));

if (missing.length > 0) {
  console.error("Orders page structural check failed. Missing snippets:");
  for (const snippet of missing) {
    console.error(`- ${snippet}`);
  }
  process.exit(1);
}

console.log("Orders page structural checks passed.");
