export type Bill = {
  id: string | number;
  name?: string;
  customer_number?: string;
  statement_date?: string;
  due_date?: string;
  sent_date?: string;
  paid_at?: string | null;
  created_at?: string;
  credit_limit?: string | number;
  total_amount_due?: string | number;
  minimum_amount_due?: string | number;
  currency?: string;
  amount?: string | number;
  status?: string;
  category?: string;
  notes?: string;
  source_email_id?: string;
  drive_file_id?: string;
  drive_file_name?: string;
};

export type ApiResponse = {
  status?: string;
  bills?: Bill[];
};

export type CardRow = {
  id: string;
  card: string;
  customer_number: string;
  statement_date: string | null;
  due_date: string | null;
  sent_date: string | null;
  status: string;
  currency: string;
  credit_limit: number;
  total_due: number;
  minimum_due: number;
  amount_paid: number;
  payment_date: string | null;
  remaining_balance: number;
  remarks: string;
  auto_debit: boolean;
  pdf_path: string;
  pdf_name: string;
};

export type UtilityRow = {
  provider: string;
  bill_period_start: string | null;
  bill_period_end: string | null;
  due_date: string | null;
  amount: number;
  status: string;
  paid_date: string | null;
  method: string;
  remarks: string;
  pdf_path: string;
};

export type RawRow = {
  name: string;
  sent_date: string | null;
  path: string;
  extracted_fields: string;
  success: number;
  duration_sec: string;
};

export type HistoryRow = {
  month: string;
  credit_cards: number;
  utilities: number;
  total: number;
};