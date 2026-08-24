export type ObservabilityTab = "current" | "history" | "webhooks";

export interface ObservabilityDetailField {
  label: string;
  value: string;
  highlight?: boolean;
}

export interface ObservabilityCurrentItem {
  entityType: string;
  entityKey: string;
  title: string;
  subtitle: string;
  category: string;
  statusText: string;
  isActive: boolean;
  updatedAt: string;
  lastSyncSource: string;
  lastSyncRef: string;
  summary: string[];
  details: ObservabilityDetailField[];
}

export interface ObservabilityHistoryItem {
  id: number;
  entityType: string;
  entityKey: string;
  category: string;
  title: string;
  source: string;
  sourceRef: string;
  sessionId: string;
  webhookMsgId: string;
  webhookEventType?: string;
  action: string;
  status: string;
  errorType: string;
  errorMessage: string;
  occurredAt: string;
  summaryLines: string[];
  detailFields: ObservabilityDetailField[];
  details: any;
}

export interface ObservabilityWebhookItem {
  id: number;
  msgId: string;
  eventType: string;
  businessType: string;
  businessKey: string;
  status: string;
  processStage: string;
  errorType: string;
  errorMessage: string;
  receivedAt: string;
  durationMs: number;
  summaryLines: string[];
  detailFields: ObservabilityDetailField[];
}

export interface ObservabilityCurrentPayload {
  items: ObservabilityCurrentItem[];
  total: number;
}

export interface ObservabilityHistoryPayload {
  items: ObservabilityHistoryItem[];
  total: number;
}

export interface ObservabilityWebhookPayload {
  items: ObservabilityWebhookItem[];
  total: number;
}

export interface ObservabilitySummaryCounts {
  contentChangeFailures: number;
  webhookFailures: number;
  webhookProcessing: number;
  slowWebhooks: number;
}

export interface ObservabilitySummary {
  status: "ok" | "attention" | string;
  counts: ObservabilitySummaryCounts;
  thresholds: {
    slowWebhookMs: number;
    webhookScanLimit: number;
  };
}
