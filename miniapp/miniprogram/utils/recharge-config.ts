/** 充值档位配置：档位与赠送金额确定后只改本文件。bonusFen 仅展示占位，实际到账以服务端 amountFen 为准。 */
export interface RechargeTier {
  amountFen: number;
  bonusFen: number;
}

export const RECHARGE_TIERS: RechargeTier[] = [
  { amountFen: 10000, bonusFen: 0 },
  { amountFen: 20000, bonusFen: 0 },
  { amountFen: 30000, bonusFen: 0 },
  { amountFen: 50000, bonusFen: 0 }
];
// 档位任何一项不得超出 MAX_RECHARGE_FEN（50000 分 = 500 元）；档位/赠送确定后只改本文件。

export function hasRechargeBonus(): boolean {
  return RECHARGE_TIERS.some((tier) => tier.bonusFen > 0);
}
