export function formatFen(priceFen: number): string {
  return `¥${(priceFen / 100).toFixed(2)}`;
}

// 没有实际抵扣时统一显示占位符，避免结算页出现“-¥0.00”这种既不是零元、也不代表未使用的中间态。
export function formatDeductionFen(deductionFen: number): string {
  return deductionFen > 0 ? `-${formatFen(deductionFen)}` : "-";
}
