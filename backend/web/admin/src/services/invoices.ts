import http from "./http";

export interface InvoiceCreatePayload {
  orderNo?: string;
  customerName: string;
  companyTitle: string;
  taxNo: string;
  email: string;
  amountFen?: number;
}

export interface InvoiceRecord {
  id: number;
  order_no: string | null;
  customer_name: string;
  company_title: string;
  tax_no: string;
  email: string;
  amount_fen: number | null;
  status: string;
  issue_note: string | null;
  created_at: string;
  updated_at: string;
}

interface ApiResponse<T> {
  code: number;
  data: T;
}

export async function listInvoices(status = ""): Promise<InvoiceRecord[]> {
  const { data } = await http.get<ApiResponse<InvoiceRecord[]>>(
    "/api/v1/admin/invoices",
    { params: { status } },
  );
  return data.data;
}

export async function createInvoice(payload: InvoiceCreatePayload): Promise<InvoiceRecord> {
  const { data } = await http.post<ApiResponse<InvoiceRecord>>(
    "/api/v1/admin/invoices",
    payload,
  );
  return data.data;
}

export async function markIssued(
  invoiceId: number,
  issueNote = "",
): Promise<InvoiceRecord> {
  const { data } = await http.post<ApiResponse<InvoiceRecord>>(
    `/api/v1/admin/invoices/${invoiceId}/mark-issued`,
    { issueNote },
  );
  return data.data;
}
