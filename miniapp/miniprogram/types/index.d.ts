interface CartItem {
  productId: string;
  title: string;
  imageUrl: string;
  priceFen: number;
  quantity: number;
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
