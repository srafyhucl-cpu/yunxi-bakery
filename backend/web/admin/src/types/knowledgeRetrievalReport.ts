export interface KnowledgeRetrievalSummary {
  total: number;
  hitCount: number;
  noMatchCount: number;
  noMatchRate: number;
}

export interface KnowledgeRetrievalBreakdown {
  byBotType: Record<string, number>;
  byAudience: Record<string, number>;
  byRetrievalMode: Record<string, number>;
  byFallbackReason: Record<string, number>;
}

export interface KnowledgeRetrievalDailyTrend {
  date: string;
  total: number;
  hitCount: number;
  noMatchCount: number;
  noMatchRate: number;
}

export interface KnowledgeNoMatchQuery {
  query: string;
  count: number;
}

export interface KnowledgeRetrievalLog {
  id: number;
  createdAt: string;
  botType: string;
  audience: string;
  query: string;
  retrievalMode: string;
  resultCount: number;
  fallbackReason: string;
  matchedEntryIds: unknown[];
  matchedTitles: unknown[];
}

export interface KnowledgeRetrievalReportMetadata {
  generatedAt: string;
  projectRoot: string;
  db: string;
  limit: number;
  loaded: number;
}

export interface KnowledgeRetrievalReport {
  status: string;
  metadata: KnowledgeRetrievalReportMetadata;
  summary: KnowledgeRetrievalSummary;
  breakdown: KnowledgeRetrievalBreakdown;
  trend: {
    byDate: KnowledgeRetrievalDailyTrend[];
  };
  topNoMatchQueries: KnowledgeNoMatchQuery[];
  recentLogs: KnowledgeRetrievalLog[];
}
