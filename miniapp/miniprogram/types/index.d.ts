interface CartItem {
  productId: string;
  title: string;
  imageUrl: string;
  priceFen: number;
  quantity: number;
  stock?: number;
  /** 规格与定制：同一商品不同规格必须分行，lineKey 为唯一标识 */
  lineKey?: string;
  skuId?: string;
  skuName?: string;
  optionChoiceIds?: string[];
  optionText?: string;
  greeting?: string;
  accessories?: string;
  /** 下单方式：预订商品需要提前量，结算页据此抬高可选时间 */
  orderMode?: "direct" | "preorder";
}

interface AddressBookItem {
  id: string;
  receiverName: string;
  receiverPhone: string;
  address: string;
  isDefault: boolean;
  updatedAt: string;
}

interface IAppOption {
  globalData: {
    addressBookItems: AddressBookItem[];
    cartItems: CartItem[];
    miniappSession?: MiniappSession;
  };
}

interface MiniappSession {
  userId: string;
  openid: string;
  sessionReady: boolean;
  isDemo: boolean;
  accessToken: string;
  tokenType: string;
  expiresIn: number;
  expiresAt: number;
}
