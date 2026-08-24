import http from "./http";

import type {
  KnowledgeDetailPayload,
  KnowledgeDraft,
  KnowledgeEntry,
  KnowledgeListPayload,
} from "@/types/knowledge";

interface KnowledgeEntryResponse {
  id: number;
  category: string;
  content_type: string;
  title: string;
  content: string;
  keywords: string;
  priority: number;
  is_active: boolean;
  content_origin: string;
  created_by: string;
  updated_by: string;
  suggested_category: string;
  suggest_reason: string;
  last_sync_source: string;
  last_sync_ref: string;
  vector_sync_status: string;
  vector_synced_at: string;
  vector_sync_error: string;
  vector_sync_retry_count: number;
  audience: string;
  review_status: string;
  valid_from: string;
  valid_until: string;
  reviewed_by: string;
  reviewed_at: string;
  created_at: string;
  updated_at: string;
}

interface KnowledgeListResponse {
  code: number;
  data: KnowledgeEntryResponse[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_active?: number;
    total_failed?: number;
  };
}

interface KnowledgeDetailResponse {
  code: number;
  data: {
    entry: KnowledgeEntryResponse;
    history: Array<Record<string, unknown>>;
  };
}

interface KnowledgeMutationResponse {
  code: number;
  data: KnowledgeEntryResponse;
}

interface SuggestCategoryResponse {
  code: number;
  data: {
    content_type: string;
    label: string;
    reason: string;
  };
}

function normalizeEntry(item: KnowledgeEntryResponse): KnowledgeEntry {
  return {
    id: item.id,
    category: item.category || "",
    contentType: item.content_type || "",
    title: item.title || "",
    content: item.content || "",
    keywords: item.keywords || "",
    priority: item.priority || 50,
    isActive: item.is_active,
    contentOrigin: item.content_origin || "",
    createdBy: item.created_by || "",
    updatedBy: item.updated_by || "",
    suggestedCategory: item.suggested_category || "",
    suggestReason: item.suggest_reason || "",
    lastSyncSource: item.last_sync_source || "",
    lastSyncRef: item.last_sync_ref || "",
    vectorSyncStatus: item.vector_sync_status || "",
    vectorSyncedAt: item.vector_synced_at || "",
    vectorSyncError: item.vector_sync_error || "",
    vectorSyncRetryCount: item.vector_sync_retry_count || 0,
    audience: item.audience || "all",
    reviewStatus: item.review_status || "published",
    validFrom: item.valid_from || "",
    validUntil: item.valid_until || "",
    reviewedBy: item.reviewed_by || "",
    reviewedAt: item.reviewed_at || "",
    createdAt: item.created_at || "",
    updatedAt: item.updated_at || "",
  };
}

function toRequestBody(draft: KnowledgeDraft) {
  return {
    title: draft.title,
    content: draft.content,
    content_type: draft.contentType,
    keywords: draft.keywords,
    priority: draft.priority,
    is_active: draft.isActive,
    audience: draft.audience,
    review_status: draft.reviewStatus,
    valid_from: draft.validFrom,
    valid_until: draft.validUntil,
  };
}

export const knowledgeService = {
  async listEntries(params: {
    page: number;
    contentType: string;
    isActive: string;
    vectorStatus: string;
    keyword: string;
  }): Promise<KnowledgeListPayload> {
    const response = await http.get<KnowledgeListResponse>("/knowledge-config/entries", {
      params: {
        page: params.page,
        content_type: params.contentType,
        is_active: params.isActive,
        vector_status: params.vectorStatus,
        keyword: params.keyword,
      },
    });
    return {
      items: response.data.data.map(normalizeEntry),
      total: response.data.pagination.total,
      totalActive: response.data.pagination.total_active || 0,
      totalFailed: response.data.pagination.total_failed || 0,
      page: response.data.pagination.page,
      pageSize: response.data.pagination.page_size,
    };
  },

  async getEntry(entryId: number): Promise<KnowledgeDetailPayload> {
    const response = await http.get<KnowledgeDetailResponse>(`/knowledge-config/entries/${entryId}`);
    return {
      entry: normalizeEntry(response.data.data.entry),
      history: response.data.data.history,
    };
  },

  async createEntry(draft: KnowledgeDraft): Promise<KnowledgeEntry> {
    const response = await http.post<KnowledgeMutationResponse>(
      "/knowledge-config/entries",
      toRequestBody(draft),
    );
    return normalizeEntry(response.data.data);
  },

  async updateEntry(entryId: number, draft: KnowledgeDraft): Promise<KnowledgeEntry> {
    const response = await http.put<KnowledgeMutationResponse>(
      `/knowledge-config/entries/${entryId}`,
      toRequestBody(draft),
    );
    return normalizeEntry(response.data.data);
  },

  async toggleActive(entryId: number): Promise<KnowledgeEntry> {
    const response = await http.post<KnowledgeMutationResponse>(
      `/knowledge-config/entries/${entryId}/toggle-active`,
    );
    return normalizeEntry(response.data.data);
  },

  async retrySync(entryId: number): Promise<KnowledgeEntry> {
    const response = await http.post<KnowledgeMutationResponse>(
      `/knowledge-config/entries/${entryId}/retry-sync`,
    );
    return normalizeEntry(response.data.data);
  },

  async suggestCategory(title: string, content: string): Promise<SuggestCategoryResponse["data"]> {
    const response = await http.post<SuggestCategoryResponse>("/knowledge-config/suggest-category", {
      title,
      content,
    });
    return response.data.data;
  },
};
