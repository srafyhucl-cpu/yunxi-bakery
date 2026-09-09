import { IS_USING_LOCAL_API } from "./config";

/** 充值 mock 确认依赖本地后端。 */
export const RECHARGE_READY = IS_USING_LOCAL_API;
/** 在线支付路径（prepare-payment / 组合差额会话，需 mock 或微信）依赖本地后端。 */
export const ONLINE_PAYMENT_READY = IS_USING_LOCAL_API;
