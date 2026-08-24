export function formatFen(priceFen: number): string {
  return `¥${(priceFen / 100).toFixed(2)}`;
}

