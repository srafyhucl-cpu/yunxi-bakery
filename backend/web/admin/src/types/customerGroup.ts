export interface CustomerGroup {
  id: string;
  chatId: string;
  opengid: string;
  name: string;
  ownerUserid: string;
  source: string;
  status: string;
  createdAt: string;
  updatedAt: string;
}

export interface CustomerGroupDraft {
  chatId: string;
  opengid: string;
  name: string;
  ownerUserid: string;
  source: string;
}

export interface GroupCampaign {
  id: string;
  groupId: string;
  title: string;
  status: string;
  startsAt: string;
  endsAt: string;
  summaryNote: string;
  createdAt: string;
  updatedAt: string;
}

export interface GroupCampaignDraft {
  groupId: string;
  title: string;
  startsAt: string;
  endsAt: string;
  summaryNote: string;
}

export interface GroupRegistration {
  id: string;
  campaignId: string;
  groupId: string;
  userId: string;
  customerName: string;
  customerPhone: string;
  productName: string;
  quantity: number;
  fulfillmentMethod: "pickup" | "delivery";
  desiredTime: string;
  address: string;
  remark: string;
  status: "pending" | "confirmed" | "cancelled";
  createdAt: string;
  updatedAt: string;
}

export interface ProductTotal {
  productName: string;
  quantity: number;
}

export interface CampaignSummary {
  campaign: GroupCampaign;
  group: CustomerGroup | null;
  totalRegistrations: number;
  totalQuantity: number;
  statusCounts: Record<string, number>;
  fulfillmentCounts: Record<string, number>;
  productTotals: ProductTotal[];
  pendingFollowups: GroupRegistration[];
  registrations: GroupRegistration[];
  summaryText: string;
}
