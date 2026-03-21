import React, { useEffect, useMemo, useState } from "react";
import * as XLSX from "xlsx";
import {
  BarChart,
  Bar,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  LineChart,
  Line,
  ResponsiveContainer,
} from "recharts";
import type { ApiResponse, CardRow, UtilityRow, RawRow, HistoryRow } from "./types";
import { joinUrl, peso, parseDate, toAmount, monthOf, daysDiff } from "./utils"
import { transformApiToFrames } from "./ledger"

type Theme = "light" | "dark" | "system";

const sample: ApiResponse = {
  status: "Success",
  bills: [
    {
      id: 1,
      name: "BPI Rewards",
      customer_number: "020100-4-10-7956071",
      statement_date: "2026-01-28",
      due_date: "2026-02-18",
      sent_date: "2026-02-07T16:08:21+00:00",
      credit_limit: "314000.00",
      total_amount_due: "20958.15",
      minimum_amount_due: "850.00",
      currency: "PHP",
      status: "unpaid",
      source_email_id: "19c3b3a0508fb5fa",
      drive_file_id: "1yQCOPjYIp0AI3nLDWeE_c2046tyGFUB0",
      drive_file_name: "BPI Rewards - February 2026.pdf",
      created_at: "2026-03-17T17:28:32.068485+00:00",
      paid_at: null,
      category: "credit_card",
      notes: "",
    },
  ],
};

const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
const DEFAULT_MODE = (import.meta.env.VITE_DATA_MODE ?? "sample").toLowerCase();
const BILLS_PATH = import.meta.env.VITE_BILLS_PATH ?? "/get_bills";
const PAY_PATH_TEMPLATE = import.meta.env.VITE_PAY_PATH_TEMPLATE ?? "/:id/pay";

function getBillsEndpoint(): string {
  return joinUrl(API_BASE, BILLS_PATH);
}

function getPayEndpoint(id: string): string {
  const replaced = PAY_PATH_TEMPLATE.replace(":id", encodeURIComponent(id));
  return joinUrl(API_BASE, replaced);
}

function hasApiConfig(): boolean {
  return Boolean(API_BASE);
}

function App() {
  const [theme, setTheme] = useState<Theme>("system");

const toggleTheme = () => {
  setTheme((prev) =>
    prev === "light" ? "dark" : prev === "dark" ? "system" : "light"
  );
};

  useEffect(() => {
  const media = window.matchMedia("(prefers-color-scheme: dark)");

  const isDark =
    theme === "dark" ? true :
    theme === "light" ? false :
    media.matches;

  const html = document.documentElement;

  if (isDark) {
    html.classList.add("dark");
  } else {
    html.classList.remove("dark");
  }

  console.log("theme:", theme, "isDark:", isDark);
  console.log("html classes:", html.className);
  }, [theme]);

  const [mode, setMode] = useState<"paste" | "fetch">(
    DEFAULT_MODE === "fetch" && hasApiConfig() ? "fetch" : "paste"
  );
  const [jsonText, setJsonText] = useState(JSON.stringify(sample, null, 2));
  const [apiUrl] = useState(getBillsEndpoint());
  const [apiJson, setApiJson] = useState<ApiResponse | null>(sample);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>("");
  const [payingId, setPayingId] = useState<string | null>(null);

  const { cards, utilities, raw, history } = useMemo(() => {
    if (!apiJson) return { cards: [], utilities: [], raw: [], history: [] };
    return transformApiToFrames(apiJson);
  }, [apiJson]);

  const periodOptions = useMemo(() => {
    const months = new Set<string>();
    for (const row of cards) if (row.statement_date) months.add(row.statement_date.slice(0, 7));
    for (const row of utilities) if (row.due_date) months.add(row.due_date.slice(0, 7));
    const sorted = [...months].sort();
    if (sorted.length) return sorted;
    return [new Date().toISOString().slice(0, 7)];
  }, [cards, utilities]);

  const [selectedMonth, setSelectedMonth] = useState<string>(periodOptions[periodOptions.length - 1]);

  useEffect(() => {
    setSelectedMonth(periodOptions[periodOptions.length - 1]);
  }, [periodOptions]);

  const cardsMonth = useMemo(
    () => cards.filter((x) => monthOf(x.statement_date) === selectedMonth),
    [cards, selectedMonth]
  );

  const utilsMonth = useMemo(
    () => utilities.filter((x) => monthOf(x.due_date) === selectedMonth),
    [utilities, selectedMonth]
  );

  const today = new Date().toISOString().slice(0, 10);
  const next7 = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  const lastMonth = (() => {
    const [y, m] = selectedMonth.split("-").map(Number);
    const d = new Date(y, m - 2, 1);
    return d.toISOString().slice(0, 7);
  })();

  const thisMonthPaid =
    cardsMonth.reduce((s, x) => s + x.amount_paid, 0) +
    utilsMonth.reduce((s, x) => s + (x.status === "paid" ? x.amount : 0), 0);

  const lastMonthPaid =
    cards.filter((x) => monthOf(x.statement_date) === lastMonth).reduce((s, x) => s + x.amount_paid, 0) +
    utilities
      .filter((x) => monthOf(x.due_date) === lastMonth)
      .reduce((s, x) => s + (x.status === "paid" ? x.amount : 0), 0);

  const creditTotalDue = cardsMonth.reduce((s, x) => s + x.total_due, 0);
  const creditMinimumDue = cardsMonth.reduce((s, x) => s + x.minimum_due, 0);
  const creditLimitTotal = cardsMonth.reduce((s, x) => s + x.credit_limit, 0);
  const utilitiesTotalDue = utilsMonth.reduce((s, x) => s + x.amount, 0);

  const upcoming7 =
    cardsMonth
      .filter((x) => x.due_date && x.due_date >= today && x.due_date <= next7)
      .reduce((s, x) => s + x.total_due, 0) +
    utilsMonth
      .filter((x) => x.due_date && x.due_date >= today && x.due_date <= next7)
      .reduce((s, x) => s + x.amount, 0);

  const delays = [
    ...cardsMonth
      .filter((x) => x.payment_date && x.due_date)
      .map((x) => daysDiff(x.due_date!, x.payment_date!)),
    ...utilsMonth
      .filter((x) => x.paid_date && x.due_date)
      .map((x) => daysDiff(x.due_date!, x.paid_date!)),
  ];
  const avgDelay = delays.length ? delays.reduce((a, b) => a + b, 0) / delays.length : null;
  const autoPaidRate = cardsMonth.length
    ? cardsMonth.filter((x) => x.auto_debit).length / cardsMonth.length
    : 0;

  const totalTarget = creditTotalDue + utilitiesTotalDue;
  const progressRatio = totalTarget > 0 ? Math.min(1, Math.max(0, thisMonthPaid / totalTarget)) : 1;

  const alerts = useMemo(() => {
    const all = [
      ...cardsMonth.map((x) => ({ bill: x.card, due_date: x.due_date, amount: x.total_due })),
      ...utilsMonth.map((x) => ({ bill: x.provider, due_date: x.due_date, amount: x.amount })),
    ];
    return all
      .map((x) => {
        const daysLeft = x.due_date ? daysDiff(today, x.due_date) : NaN;
        const status = Number.isNaN(daysLeft)
          ? "Pending"
          : daysLeft < 0
            ? "Overdue"
            : daysLeft <= 7
              ? "Due soon"
              : "Pending";
        return { ...x, days_left: daysLeft, status };
      })
      .sort((a, b) => a.days_left - b.days_left);
  }, [cardsMonth, utilsMonth, today]);

  async function handleParseJson() {
    setError("");
    try {
      const parsed = JSON.parse(jsonText) as ApiResponse;
      setApiJson(parsed);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Invalid JSON");
    }
  }

  async function handleFetch() {
    setLoading(true);
    setError("");
    try {
      if (!hasApiConfig()) {
        throw new Error("Missing VITE_API_URL. Add it to your environment before using fetch mode.");
      }
      const res = await fetch(getBillsEndpoint());
      if (!res.ok) throw new Error(`Fetch failed: ${res.status} ${res.statusText}`);
      const data = (await res.json()) as ApiResponse;
      setApiJson(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fetch failed");
    } finally {
      setLoading(false);
    }
  }

  async function handlePay(id: string) {
    setPayingId(id);
    setError("");
    try {
      if (!hasApiConfig()) {
        throw new Error("Missing VITE_API_URL. Add it to your environment before using pay actions.");
      }
      const res = await fetch(getPayEndpoint(id), { method: "POST" });
      if (!res.ok) throw new Error(`Payment failed: ${res.status} ${res.statusText}`);
      setApiJson((prev) => {
        if (!prev?.bills) return prev;
        return {
          ...prev,
          bills: prev.bills.map((bill) =>
            String(bill.id) === id
              ? { ...bill, status: "paid", paid_at: new Date().toISOString() }
              : bill
          ),
        };
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Payment failed");
    } finally {
      setPayingId(null);
    }
  }

  function exportExcel() {
    const summary = [
      ["Metric", "Value"],
      ["Total Bills Paid (This Month)", thisMonthPaid],
      ["Credit Card Total Due", creditTotalDue],
      ["Utilities Total Due", utilitiesTotalDue],
      ["Upcoming Due (7 days)", upcoming7],
    ];

    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, XLSX.utils.aoa_to_sheet(summary), "Summary");
    XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(cardsMonth), "CreditCards");
    XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(utilsMonth), "Utilities");
    XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(alerts), "Alerts");
    XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(raw), "RawExtract");
    XLSX.utils.book_append_sheet(workbook, XLSX.utils.json_to_sheet(history), "History");
    XLSX.writeFile(workbook, `ledgerx_report_${selectedMonth}.xlsx`);
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-900 dark:text-white">
      <div className="mx-auto max-w-7xl p-6">
        <div className="mb-6 rounded-3xl bg-white p-6 shadow-sm dark:bg-slate-800">
          <button
            onClick={toggleTheme}
            className="rounded-xl border border-slate-300 px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-white"
          >
            Theme: {theme}
          </button>
          <h1 className="text-3xl font-bold">🧾 LedgerX – Bills Report</h1>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
            Static TypeScript frontend version of your Streamlit app. Deployable on Render as a static site.
          </p>
          <p className="mt-2 text-xs text-slate-500">
            Frontend config is environment-driven via <code>VITE_API_URL</code>, <code>VITE_BILLS_PATH</code>, <code>VITE_PAY_PATH_TEMPLATE</code>, and <code>VITE_DATA_MODE</code>.
          </p>
        </div>

        <div className="grid gap-6 lg:grid-cols-[360px,1fr]">
          <aside className="rounded-3xl bg-white p-5 shadow-sm">
            <h2 className="text-xl font-semibold">Data Source</h2>
            <div className="mt-4 flex gap-2">
              <button
                className={`rounded-2xl px-4 py-2 text-sm font-medium ${mode === "paste" ? "bg-slate-900 text-white" : "bg-slate-100"}`}
                onClick={() => setMode("paste")}
              >
                Paste JSON
              </button>
              <button
                className={`rounded-2xl px-4 py-2 text-sm font-medium ${mode === "fetch" ? "bg-slate-900 text-white" : "bg-slate-100"}`}
                onClick={() => setMode("fetch")}
              >
                Fetch from API
              </button>
            </div>

            {mode === "paste" ? (
              <div className="mt-4">
                <textarea
                  className="h-72 w-full rounded-2xl border p-3 font-mono text-xs"
                  value={jsonText}
                  onChange={(e) => setJsonText(e.target.value)}
                />
                <button
                  className="mt-3 w-full rounded-2xl bg-slate-900 px-4 py-2 text-white"
                  onClick={handleParseJson}
                >
                  Render JSON
                </button>
              </div>
            ) : (
              <div className="mt-4">
                <input
                  className="w-full rounded-2xl border bg-slate-50 p-3 text-sm text-slate-600"
                  value={apiUrl || "No API configured"}
                  readOnly
                  placeholder="Configured by VITE_API_URL"
                />
                <button
                  className="mt-3 w-full rounded-2xl bg-slate-900 px-4 py-2 text-white disabled:opacity-50"
                  onClick={handleFetch}
                  disabled={loading || !hasApiConfig()}
                >
                  {!hasApiConfig() ? "Set VITE_API_URL first" : loading ? "Fetching..." : "Fetch"}
                </button>
              </div>
            )}

            {!!error && <div className="mt-4 rounded-2xl bg-red-50 p-3 text-sm text-red-700">{error}</div>}

            <div className="mt-6">
              <label className="mb-2 block text-sm font-medium">Report Month</label>
              <select
                className="w-full rounded-2xl border p-3"
                value={selectedMonth}
                onChange={(e) => setSelectedMonth(e.target.value)}
              >
                {periodOptions.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>

            <button
              className="mt-6 w-full rounded-2xl bg-emerald-600 px-4 py-2 text-white"
              onClick={exportExcel}
            >
              Export XLSX
            </button>
          </aside>

          <main className="space-y-6">
            <section className="rounded-3xl bg-white p-5 shadow-sm">
              <h2 className="text-xl font-semibold">1) Summary Dashboard</h2>
              <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-6">
                {[
                  ["Total Bills Paid (This Month)", peso(thisMonthPaid), `${peso(thisMonthPaid - lastMonthPaid)} vs prev`],
                  ["Credit Card Total Due", peso(creditTotalDue), `${cardsMonth.length} card statement(s)`],
                  ["Minimum Amount Due", peso(creditMinimumDue), "Across visible cards"],
                  ["Total Credit Limit", peso(creditLimitTotal), "Available card limits in view"],
                  ["Utilities Total Due", peso(utilitiesTotalDue), ""],
                  ["Upcoming Due (7 days)", peso(upcoming7), ""],
                  ["Avg Delay (days)", avgDelay == null ? "—" : avgDelay.toFixed(1), ""],
                  ["Auto-Paid (%)", `${Math.round(autoPaidRate * 100)}%`, ""],
                ].map((item) => {
                  const [label, value, sub] = item as [string, string, string];
                  return (
                  <div key={label} className="rounded-2xl bg-slate-50 p-4">
                    <div className="text-xs text-slate-500">{label}</div>
                    <div className="mt-2 text-2xl font-semibold">{value}</div>
                    {sub ? <div className="mt-1 text-xs text-slate-500">{sub}</div> : null}
                  </div>
                )})}
              </div>
              <div className="mt-4">
                <div className="mb-2 text-sm text-slate-600">
                  {peso(thisMonthPaid)} / {peso(totalTarget)} paid this period
                </div>
                <div className="h-3 w-full rounded-full bg-slate-100">
                  <div
                    className="h-3 rounded-full bg-slate-900 transition-all"
                    style={{ width: `${progressRatio * 100}%` }}
                  />
                </div>
              </div>
            </section>

            <section className="rounded-3xl bg-white p-5 shadow-sm">
              <h2 className="text-xl font-semibold">2) Credit Card Statements</h2>
              <p className="mt-2 text-sm text-slate-500">
                Optimized for the fields coming from your API: statement date, customer number, credit limit, total amount due, and minimum amount due.
              </p>
              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                {cardsMonth.map((row) => {
                  const disabled = row.status === "paid";
                  return (
                    <div key={row.id} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <div className="text-lg font-semibold">{row.card}</div>
                          <div className="mt-1 text-sm text-slate-500">Customer No. {row.customer_number || "—"}</div>
                        </div>
                        <div className={`rounded-full px-3 py-1 text-xs font-medium ${row.status === "paid" ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                          {row.status || "unknown"}
                        </div>
                      </div>

                      <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                        <div className="rounded-xl bg-white p-3">
                          <div className="text-xs text-slate-500">Statement Date</div>
                          <div className="mt-1 font-medium">{row.statement_date ?? "—"}</div>
                        </div>
                        <div className="rounded-xl bg-white p-3">
                          <div className="text-xs text-slate-500">Due Date</div>
                          <div className="mt-1 font-medium">{row.due_date ?? "—"}</div>
                        </div>
                        <div className="rounded-xl bg-white p-3">
                          <div className="text-xs text-slate-500">Credit Limit</div>
                          <div className="mt-1 font-medium">{peso(row.credit_limit)}</div>
                        </div>
                        <div className="rounded-xl bg-white p-3">
                          <div className="text-xs text-slate-500">Minimum Due</div>
                          <div className="mt-1 font-medium">{peso(row.minimum_due)}</div>
                        </div>
                      </div>

                      <div className="mt-4 rounded-2xl bg-white p-4">
                        <div className="text-xs text-slate-500">Total Amount Due</div>
                        <div className="mt-1 text-2xl font-semibold">{peso(row.total_due)}</div>
                        <div className="mt-2 text-xs text-slate-500">Currency: {row.currency}</div>
                      </div>

                      <div className="mt-4 flex flex-wrap items-center gap-3">
                        {row.pdf_path ? (
                          <a
                            className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700"
                            href={row.pdf_path}
                            target="_blank"
                            rel="noreferrer"
                          >
                            View PDF
                          </a>
                        ) : null}
                        {row.pdf_name ? <span className="text-sm text-slate-500">{row.pdf_name}</span> : null}
                        <button
                          className="rounded-xl bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
                          disabled={disabled || payingId === row.id}
                          onClick={() => handlePay(row.id)}
                        >
                          {disabled ? "Paid" : payingId === row.id ? "Processing..." : "Mark as Paid"}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>

            <section className="rounded-3xl bg-white p-5 shadow-sm">
              <h2 className="text-xl font-semibold">3) Utilities & Subscriptions</h2>
              {utilsMonth.length === 0 ? (
                <p className="mt-4 text-sm text-slate-500">No utilities/subscriptions found in this API response.</p>
              ) : (
                <div className="mt-4 overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-slate-500">
                        <th className="py-3 pr-4">Provider</th>
                        <th className="py-3 pr-4">Due Date</th>
                        <th className="py-3 pr-4">Amount</th>
                        <th className="py-3 pr-4">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {utilsMonth.map((row, idx) => (
                        <tr key={`${row.provider}-${idx}`} className="border-b last:border-0">
                          <td className="py-3 pr-4">{row.provider}</td>
                          <td className="py-3 pr-4">{row.due_date ?? "—"}</td>
                          <td className="py-3 pr-4">{peso(row.amount)}</td>
                          <td className="py-3 pr-4 capitalize">{row.status || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section className="rounded-3xl bg-white p-5 shadow-sm">
              <h2 className="text-xl font-semibold">4) Upcoming & Overdue Alerts</h2>
              <div className="mt-4 overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-slate-500">
                      <th className="py-3 pr-4">Bill</th>
                      <th className="py-3 pr-4">Due Date</th>
                      <th className="py-3 pr-4">Amount</th>
                      <th className="py-3 pr-4">Days Left</th>
                      <th className="py-3 pr-4">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {alerts.map((row, idx) => (
                      <tr key={`${row.bill}-${idx}`} className="border-b last:border-0">
                        <td className="py-3 pr-4">{row.bill}</td>
                        <td className="py-3 pr-4">{row.due_date ?? "—"}</td>
                        <td className="py-3 pr-4">{peso(row.amount)}</td>
                        <td className="py-3 pr-4">{Number.isNaN(row.days_left) ? "—" : row.days_left}</td>
                        <td className="py-3 pr-4">{row.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="rounded-3xl bg-white p-5 shadow-sm">
              <h2 className="text-xl font-semibold">5) Visual Analytics</h2>
              {history.length === 0 ? (
                <p className="mt-4 text-sm text-slate-500">Not enough history to plot trends yet.</p>
              ) : (
                <div className="mt-4 grid gap-6 xl:grid-cols-2">
                  <div className="h-80 rounded-2xl bg-slate-50 p-3">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={history}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="month" />
                        <YAxis />
                        <Tooltip formatter={(v: number) => peso(v)} />
                        <Legend />
                        <Bar dataKey="credit_cards" name="Credit Cards" />
                        <Bar dataKey="utilities" name="Utilities" />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="h-80 rounded-2xl bg-slate-50 p-3">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={history}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="month" />
                        <YAxis />
                        <Tooltip formatter={(v: number) => peso(v)} />
                        <Legend />
                        <Line type="monotone" dataKey="total" name="Total" strokeWidth={2} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
            </section>

            <section className="rounded-3xl bg-white p-5 shadow-sm">
              <h2 className="text-xl font-semibold">6) Extracted API Fields</h2>
              <div className="mt-4 overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-slate-500">
                      <th className="py-3 pr-4">Name</th>
                      <th className="py-3 pr-4">Statement Date</th>
                      <th className="py-3 pr-4">Customer Number</th>
                      <th className="py-3 pr-4">Credit Limit</th>
                      <th className="py-3 pr-4">Total Due</th>
                      <th className="py-3 pr-4">Minimum Due</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(apiJson?.bills ?? []).map((bill, idx) => (
                      <tr key={`${bill.name}-${idx}`} className="border-b last:border-0">
                        <td className="py-3 pr-4">{bill.name ?? "—"}</td>
                        <td className="py-3 pr-4">{parseDate(bill.statement_date) ?? "—"}</td>
                        <td className="py-3 pr-4">{bill.customer_number ?? "—"}</td>
                        <td className="py-3 pr-4">{peso(toAmount(bill.credit_limit))}</td>
                        <td className="py-3 pr-4">{peso(toAmount(bill.total_amount_due ?? bill.amount))}</td>
                        <td className="py-3 pr-4">{peso(toAmount(bill.minimum_amount_due))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </main>
        </div>
      </div>
    </div>
  );
}

export default App;
