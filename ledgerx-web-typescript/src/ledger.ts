import type {
  ApiResponse,
  CardRow,
  UtilityRow,
  RawRow,
  HistoryRow
} from "./types";
import { parseDate, toAmount, monthOf } from "./utils"


export function transformApiToFrames(apiJson: ApiResponse): {
  cards: CardRow[];
  utilities: UtilityRow[];
  raw: RawRow[];
  history: HistoryRow[];
} {
  const bills = apiJson.bills ?? [];

  const cardsRaw = bills.filter(
    (b) => (b.category ?? "credit_card").toLowerCase() === "credit_card"
  );
  const utilsRaw = bills.filter(
    (b) => (b.category ?? "credit_card").toLowerCase() !== "credit_card"
  );

  const cards: CardRow[] = cardsRaw.map((b) => {
    const totalDue = toAmount(b.total_amount_due ?? b.amount);
    const minimumDue = toAmount(b.minimum_amount_due);
    const creditLimit = toAmount(b.credit_limit);
    const status = (b.status ?? "").toLowerCase();
    const paid = status === "paid";
    return {
      id: String(b.id ?? ""),
      card: b.name ?? "",
      customer_number: b.customer_number ?? "",
      statement_date: parseDate(b.statement_date ?? b.sent_date),
      due_date: parseDate(b.due_date),
      sent_date: parseDate(b.sent_date),
      status,
      currency: b.currency ?? "PHP",
      credit_limit: creditLimit,
      total_due: totalDue,
      minimum_due: minimumDue,
      amount_paid: paid ? totalDue : 0,
      payment_date: parseDate(b.paid_at),
      remaining_balance: paid ? 0 : totalDue,
      remarks: b.notes ?? "",
      auto_debit: false,
      pdf_path: b.drive_file_id ? `https://drive.google.com/file/d/${b.drive_file_id}/view` : "",
      pdf_name: b.drive_file_name ?? "",
    };
  });

  const utilities: UtilityRow[] = utilsRaw.map((b) => ({
    provider: b.name ?? "",
    bill_period_start: parseDate(b.statement_date ?? b.sent_date),
    bill_period_end: parseDate(b.due_date),
    due_date: parseDate(b.due_date),
    amount: toAmount(b.total_amount_due ?? b.amount),
    status: (b.status ?? "").toLowerCase(),
    paid_date: parseDate(b.paid_at),
    method: "",
    remarks: b.notes ?? "",
    pdf_path: b.drive_file_id ? `https://drive.google.com/file/d/${b.drive_file_id}/view` : "",
  }));

  const raw: RawRow[] = bills.map((b) => ({
    name: b.name ?? "",
    sent_date: parseDate(b.sent_date),
    path: b.drive_file_name ?? "",
    extracted_fields: JSON.stringify(
      {
        customer_number: b.customer_number,
        statement_date: b.statement_date,
        due_date: b.due_date,
        credit_limit: b.credit_limit,
        total_amount_due: b.total_amount_due,
        minimum_amount_due: b.minimum_amount_due,
      },
      null,
      0
    ),
    success: 1,
    duration_sec: "",
  }));

  const historyMap = new Map<string, { credit_cards: number; utilities: number }>();

  for (const row of cards) {
    const month = monthOf(row.statement_date);
    if (!month) continue;
    const current = historyMap.get(month) ?? { credit_cards: 0, utilities: 0 };
    current.credit_cards += row.total_due;
    historyMap.set(month, current);
  }

  for (const row of utilities) {
    const month = monthOf(row.due_date);
    if (!month) continue;
    const current = historyMap.get(month) ?? { credit_cards: 0, utilities: 0 };
    current.utilities += row.amount;
    historyMap.set(month, current);
  }

  const history = [...historyMap.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([month, v]) => ({
      month,
      credit_cards: v.credit_cards,
      utilities: v.utilities,
      total: v.credit_cards + v.utilities,
    }));

  return { cards, utilities, raw, history };
}