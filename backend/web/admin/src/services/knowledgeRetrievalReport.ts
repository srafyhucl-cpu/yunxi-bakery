import http from "./http";

import type {
  KnowledgeNoMatchQuery,
  KnowledgeRetrievalDailyTrend,
  KnowledgeRetrievalLog,
  KnowledgeRetrievalReport,
} from "@/types/knowledgeRetrievalReport";

interface KnowledgeRetrievalReportResponse {
  code: number;
  data: {
    status: string;
    metadata: {
      generated_at: string;
      project_root: string;
      db: string;
      limit: number;
      loaded: number;
    };
    summary: {
      total: number;
      hit_count: number;
      no_match_count: number;
      no_match_rate: number;
    };
    breakdown: {
      by_bot_type: Record<string, number>;
      by_audience: Record<string, number>;
      by_retrieval_mode: Record<string, number>;
      by_fallback_reason: Record<string, number>;
    };
    trend: {
      by_date: Array<{
        date: string;
        total: number;
        hit_count: number;
        no_match_count: number;
        no_match_rate: number;
      }>;
    };
    top_no_match_queries: Array<{
      query: string;
      count: number;
    }>;
    recent_logs: Array<{
      id: number;
      created_at: string;
      bot_type: string;
      audience: string;
      query: string;
      retrieval_mode: string;
      result_count: number;
      fallback_reason: string;
      matched_entry_ids: unknown[];
      matched_titles: unknown[];
    }>;
  };
}

function normalizeTrendItem(
  item: KnowledgeRetrievalReportResponse["data"]["trend"]["by_date"][number],
): KnowledgeRetrievalDailyTrend {
  return {
    date: item.date || "",
    total: item.total || 0,
    hitCount: item.hit_count || 0,
    noMatchCount: item.no_match_count || 0,
    noMatchRate: item.no_match_rate || 0,
  };
}

function normalizeNoMatchQuery(
  item: KnowledgeRetrievalReportResponse["data"]["top_no_match_queries"][number],
): KnowledgeNoMatchQuery {
  return {
    query: item.query || "",
    count: item.count || 0,
  };
}

function normalizeLog(
  item: KnowledgeRetrievalReportResponse["data"]["recent_logs"][number],
): KnowledgeRetrievalLog {
  return {
    id: item.id,
    createdAt: item.created_at || "",
    botType: item.bot_type || "",
    audience: item.audience || "",
    query: item.query || "",
    retrievalMode: item.retrieval_mode || "",
    resultCount: item.result_count || 0,
    fallbackReason: item.fallback_reason || "",
    matchedEntryIds: item.matched_entry_ids || [],
    matchedTitles: item.matched_titles || [],
  };
}

function normalizeReport(payload: KnowledgeRetrievalReportResponse["data"]): KnowledgeRetrievalReport {
  return {
    status: payload.status || "ok",
    metadata: {
      generatedAt: payload.metadata?.generated_at || "",
      projectRoot: payload.metadata?.project_root || "",
      db: payload.metadata?.db || "",
      limit: payload.metadata?.limit || 0,
      loaded: payload.metadata?.loaded || 0,
    },
    summary: {
      total: payload.summary?.total || 0,
      hitCount: payload.summary?.hit_count || 0,
      noMatchCount: payload.summary?.no_match_count || 0,
      noMatchRate: payload.summary?.no_match_rate || 0,
    },
    breakdown: {
      byBotType: payload.breakdown?.by_bot_type || {},
      byAudience: payload.breakdown?.by_audience || {},
      byRetrievalMode: payload.breakdown?.by_retrieval_mode || {},
      byFallbackReason: payload.breakdown?.by_fallback_reason || {},
    },
    trend: {
      byDate: (payload.trend?.by_date || []).map(normalizeTrendItem),
    },
    topNoMatchQueries: (payload.top_no_match_queries || []).map(normalizeNoMatchQuery),
    recentLogs: (payload.recent_logs || []).map(normalizeLog),
  };
}

export const knowledgeRetrievalReportService = {
  async getSummary(limit: number): Promise<KnowledgeRetrievalReport> {
    const response = await http.get<KnowledgeRetrievalReportResponse>(
      "/knowledge-retrieval-report/summary",
      {
        params: { limit },
      },
    );
    return normalizeReport(response.data.data);
  },
};
