export type PrintJobStatus =
  | "PENDING"
  | "CLAIMED"
  | "SUBMITTED"
  | "PRINTED"
  | "FAILED"
  | "MOCKED"
  | "CANCELLED";

export type PrintTicketType = "CAKE_KITCHEN" | "DAILY_FRONT";

export interface PrintJobItem {
  id: string;
  orderId: string;
  ticketType: PrintTicketType;
  status: PrintJobStatus;
  provider: string;
  printerId: string;
  attempts: number;
  lastError: string;
  providerJobId: string;
  idempotencyKey: string;
  /** 服务端截取的小票内容摘要，后台不展示完整快照。 */
  contentPreview: string;
  operator: string;
  createdAt: string;
  updatedAt: string;
  printedAt: string;
}

export interface PrintJobListPayload {
  items: PrintJobItem[];
}

export interface ProcessPendingSummary {
  success: number;
  failed: number;
  mocked: number;
  submitted: number;
}

export interface PrintJobProcessResult {
  success: boolean;
  jobId: string;
  orderId?: string;
  ticketType?: PrintTicketType;
  status: PrintJobStatus | "NOT_FOUND";
  attempts: number;
  providerJobId: string;
  error: string;
  skipped?: boolean;
}

export interface PrintJobMarkPrintedPayload {
  jobId: string;
  status: PrintJobStatus;
}

export interface PrintJobReprintResult {
  id: string;
  orderId: string;
  ticketType: PrintTicketType;
  status: PrintJobStatus;
  provider: string;
  printerId: string;
  attempts: number;
  lastError: string;
  providerJobId: string;
  idempotencyKey: string;
  operator: string;
  createdAt: string;
  updatedAt: string;
  printedAt: string;
  created: boolean;
}
