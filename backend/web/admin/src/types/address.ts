export interface AddressListItem {
  id: string;
  userId: string;
  receiverName: string;
  receiverPhone: string;
  address: string;
  isDefault: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface AddressAuditLog {
  id: number;
  addressId: string;
  userId: string;
  operator: string;
  action: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  note: string;
  createdAt: string;
}

export interface AddressDetail extends AddressListItem {
  auditLogs: AddressAuditLog[];
}

export interface AddressDraft {
  id?: string;
  userId: string;
  receiverName: string;
  receiverPhone: string;
  address: string;
  isDefault: boolean;
}

export interface AddressListPayload {
  items: AddressListItem[];
  total: number;
  page: number;
  pageSize: number;
}
