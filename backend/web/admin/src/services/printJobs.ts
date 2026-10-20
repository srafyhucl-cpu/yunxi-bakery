import http from "./http";

import type {
  PrintJobListPayload,
  PrintJobMarkPrintedPayload,
  PrintJobProcessResult,
  PrintJobReprintResult,
  PrintJobStatus,
  PrintTicketType,
  ProcessPendingSummary,
} from "@/types/printJob";

interface PrintJobListResponse {
  code: number;
  data: PrintJobListPayload;
}

interface ProcessPendingResponse {
  code: number;
  data: ProcessPendingSummary;
}

interface PrintJobProcessResponse {
  code: number;
  data: PrintJobProcessResult;
}

interface PrintJobMarkPrintedResponse {
  code: number;
  data: PrintJobMarkPrintedPayload;
}

interface PrintJobReprintResponse {
  code: number;
  data: PrintJobReprintResult;
}

export const printJobsService = {
  async list(status: PrintJobStatus | "" = "", limit: number = 50): Promise<PrintJobListPayload> {
    const response = await http.get<PrintJobListResponse>("/print-jobs", {
      params: {
        status: status || undefined,
        limit,
      },
    });
    return response.data.data;
  },

  async processPending(limit: number = 20): Promise<ProcessPendingSummary> {
    const response = await http.post<ProcessPendingResponse>(
      "/print-jobs/process-pending",
      null,
      { params: { limit } },
    );
    return response.data.data;
  },

  async retry(jobId: string): Promise<PrintJobProcessResult> {
    const response = await http.post<PrintJobProcessResponse>(
      `/print-jobs/${jobId}/retry`,
    );
    return response.data.data;
  },

  async markPrinted(jobId: string): Promise<PrintJobMarkPrintedPayload> {
    const response = await http.post<PrintJobMarkPrintedResponse>(
      `/print-jobs/${jobId}/mark-printed`,
    );
    return response.data.data;
  },

  async reprint(
    orderId: string,
    ticketType: PrintTicketType,
  ): Promise<PrintJobReprintResult> {
    const response = await http.post<PrintJobReprintResponse>(
      `/orders/${orderId}/print-jobs/${ticketType}/reprint`,
    );
    return response.data.data;
  },
};
