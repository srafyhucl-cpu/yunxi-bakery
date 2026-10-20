/** 店员身份：登录成功时后端只返回精简字段，完整资料由 /auth/me 补齐。 */
export interface StaffPrincipal {
  staffId: string;
  name: string;
  role: string;
  phone: string;
  tenantId: string;
}

/** 登录接口返回的精简身份（不含手机号与租户）。 */
export type StaffLoginResult = Pick<StaffPrincipal, "staffId" | "name" | "role">;

/** 会员最近一笔有赞历史订单摘要。 */
export interface StaffMemberHistoryOrder {
  orderNo: string;
  status: string;
  amountFen: number;
  productTitles: string;
  totalQuantity: number;
  payTime: string;
  createdAt: string;
}

/** 会员查询结果，金额单位统一为分。 */
export interface StaffMember {
  customerId: string;
  mobile: string;
  userId: string;
  displayName: string;
  isMember: boolean;
  storedValueFen: number;
  principalFen: number;
  bonusFen: number;
  points: number;
  cardAlias: string;
  historyOrders: StaffMemberHistoryOrder[];
}

/** 快捷开单商品最小字段。 */
export interface StaffProduct {
  productId: string;
  title: string;
  priceFen: number;
  stock: number;
  isPurchasable: boolean;
  imageUrl: string;
}

/** 开单收款方式：储值直扣 / 微信分享待付。 */
export type QuickOrderMode = "stored_value_direct" | "wechat_share_card";

/** 履约类型：日常现烤现货 / 定制蛋糕预订。 */
export type QuickOrderFulfillmentType = "DAILY_READY" | "PREORDER_CAKE";

/** 定制蛋糕结构化信息，后端按字段强校验。 */
export interface QuickOrderCustomization {
  size: string;
  filling: string;
  greeting: string;
  accessories: string;
}

/** 开单商品行。 */
export interface QuickOrderItem {
  productId: string;
  quantity: number;
  fulfillmentType: QuickOrderFulfillmentType;
  customization?: QuickOrderCustomization | Record<string, never>;
}

/** 建单请求体，requestId 用于后端幂等占位。 */
export interface QuickOrderPayload {
  requestId: string;
  mode: QuickOrderMode;
  phone: string;
  items: QuickOrderItem[];
  fulfillmentMethod: "pickup";
  expectTime: string;
  remark: string;
}

/** 建单成功回执；分享字段仅微信分享待付返回，balanceFen 仅储值直扣返回。 */
export interface QuickOrderResult {
  orderId: string;
  status: string;
  paymentStatus: string;
  receiptText: string;
  balanceFen?: number;
  sharePath?: string;
  shareText?: string;
}
