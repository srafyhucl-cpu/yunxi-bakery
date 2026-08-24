export type SettingsPanel = "shop" | "channel" | "api";

export interface ShopSettingsSummary {
  serverHost: string;
  serverPort: number;
  databasePath: string;
  embeddingPath: string;
  featuredProductCount: number;
  productTotal: number;
}

export interface ChannelSettingsSummary {
  youzan: {
    clientIdConfigured: boolean;
    clientSecretConfigured: boolean;
    kdtIdConfigured: boolean;
    mockMode: boolean;
  };
  wecom: {
    corpIdConfigured: boolean;
    agentIdConfigured: boolean;
    secretConfigured: boolean;
    tokenConfigured: boolean;
    encodingAesKeyConfigured: boolean;
    staffIdConfigured: boolean;
    robotWebhookConfigured: boolean;
  };
}

export interface ApiSettingsSummary {
  adminTokenConfigured: boolean;
  mimoApiKeyConfigured: boolean;
  mimoBaseUrl: string;
  mimoChatModel: string;
  mimoVisionModel: string;
  mimoAsrModel: string;
}

export interface SettingsSummary {
  shop: ShopSettingsSummary;
  channels: ChannelSettingsSummary;
  api: ApiSettingsSummary;
}
