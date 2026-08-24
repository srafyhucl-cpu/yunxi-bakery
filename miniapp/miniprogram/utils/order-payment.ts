import {
  getOrder,
  mockPayOrder,
  prepareOrderPayment,
  type OrderSummary,
  type PreparedPayment,
  type WechatPaymentParams,
} from "../services/orders";

function isWechatPaymentParams(params: Partial<WechatPaymentParams>): params is WechatPaymentParams {
  return Boolean(
    params.timeStamp &&
      params.nonceStr &&
      params.package &&
      params.signType &&
      params.paySign,
  );
}

function requestWechatPayment(params: WechatPaymentParams): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    wx.requestPayment({
      timeStamp: params.timeStamp,
      nonceStr: params.nonceStr,
      package: params.package,
      signType: params.signType,
      paySign: params.paySign,
      success: () => resolve(),
      fail: (error) => reject(error),
    });
  });
}

export async function executePreparedPayment(
  payment: PreparedPayment
): Promise<OrderSummary> {
  if (payment.mode === "wechat") {
    if (!isWechatPaymentParams(payment.paymentParams)) {
      throw new Error("微信支付参数不完整");
    }
    await requestWechatPayment(payment.paymentParams);
    return getOrder(payment.orderId);
  }
  if (payment.mode !== "mock") {
    throw new Error(`未知支付模式: ${payment.mode}`);
  }
  return mockPayOrder(payment.orderId);
}

export async function payOrderById(orderId: string, reloadOrder: () => Promise<OrderSummary>): Promise<OrderSummary> {
  const payment = await prepareOrderPayment(orderId);
  const paidOrder = await executePreparedPayment(payment);
  return reloadOrder ? reloadOrder() : paidOrder;
}
