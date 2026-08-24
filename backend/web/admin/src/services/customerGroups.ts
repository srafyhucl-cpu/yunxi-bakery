import http from "./http";

import type {
  CampaignSummary,
  CustomerGroup,
  CustomerGroupDraft,
  GroupCampaign,
  GroupCampaignDraft,
  GroupRegistration,
} from "@/types/customerGroup";

interface WrappedApiResponse<TData> {
  code: number;
  data: TData;
}

export const customerGroupsService = {
  async listGroups(keyword: string = ""): Promise<CustomerGroup[]> {
    const response = await http.get<WrappedApiResponse<CustomerGroup[]>>("/customer-groups", {
      params: {
        keyword: keyword || undefined,
      },
    });
    return response.data.data;
  },

  async bindGroup(payload: CustomerGroupDraft): Promise<CustomerGroup> {
    const response = await http.post<WrappedApiResponse<CustomerGroup>>(
      "/customer-groups",
      payload,
    );
    return response.data.data;
  },

  async listCampaigns(groupId: string = "", status: string = ""): Promise<GroupCampaign[]> {
    const response = await http.get<WrappedApiResponse<GroupCampaign[]>>(
      "/customer-groups/campaigns",
      {
        params: {
          groupId: groupId || undefined,
          status: status || undefined,
        },
      },
    );
    return response.data.data;
  },

  async createCampaign(payload: GroupCampaignDraft): Promise<GroupCampaign> {
    const response = await http.post<WrappedApiResponse<GroupCampaign>>(
      "/customer-groups/campaigns",
      payload,
    );
    return response.data.data;
  },

  async getCampaignSummary(campaignId: string): Promise<CampaignSummary> {
    const response = await http.get<WrappedApiResponse<CampaignSummary>>(
      `/customer-groups/campaigns/${campaignId}/summary`,
    );
    return response.data.data;
  },

  async updateRegistrationStatus(
    registrationId: string,
    status: GroupRegistration["status"],
  ): Promise<GroupRegistration> {
    const response = await http.post<WrappedApiResponse<GroupRegistration>>(
      `/customer-groups/registrations/${registrationId}/status`,
      { status },
    );
    return response.data.data;
  },
};
