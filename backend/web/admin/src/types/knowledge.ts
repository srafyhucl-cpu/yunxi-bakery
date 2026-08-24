export interface KnowledgeEntry {
  id: number;
  category: string;
  contentType: string;
  title: string;
  content: string;
  keywords: string;
  priority: number;
  isActive: boolean;
  contentOrigin: string;
  createdBy: string;
  updatedBy: string;
  suggestedCategory: string;
  suggestReason: string;
  lastSyncSource: string;
  lastSyncRef: string;
  vectorSyncStatus: string;
  vectorSyncedAt: string;
  vectorSyncError: string;
  vectorSyncRetryCount: number;
  audience: string;
  reviewStatus: string;
  validFrom: string;
  validUntil: string;
  reviewedBy: string;
  reviewedAt: string;
  createdAt: string;
  updatedAt: string;
}

export interface KnowledgeDraft {
  title: string;
  content: string;
  contentType: string;
  keywords: string;
  priority: number;
  isActive: boolean;
  audience: string;
  reviewStatus: string;
  validFrom: string;
  validUntil: string;
}

export interface KnowledgeListPayload {
  items: KnowledgeEntry[];
  total: number;
  totalActive: number;
  totalFailed: number;
  page: number;
  pageSize: number;
}

export interface KnowledgeDetailPayload {
  entry: KnowledgeEntry;
  history: Array<Record<string, unknown>>;
}
