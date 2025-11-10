# app.py
# Streamlit app adapted to your LedgerX /bills API response
# Run:  streamlit run app.py

from __future__ import annotations
import io
import json
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional

import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
from config import settings

try:
    import requests  # optional for live API fetch
except Exception:
    requests = None

# -----------------------------
# App Config
# -----------------------------
st.set_page_config(
    page_title="LedgerX – Bills Report (API-driven)",
    page_icon="🧾",
    layout="wide",
)

# -----------------------------
# Helpers
# -----------------------------

def _init_state():
    st.session_state.setdefault("paying_id", None)
    st.session_state.setdefault("pay_inflight", False)
    st.session_state.setdefault("api_json", None)
    st.session_state.setdefault("last_url", None)
    st.session_state.setdefault("auto_fetch_done", False)

_init_state()

def _queue_pay(bid: str, disabled: bool):
    if disabled or st.session_state.get("pay_inflight"):
        return
    st.session_state["paying_id"] = bid

def _peso(x: Any) -> str:
    if pd.isna(x):
        return "—"
    try:
        return f"₱{float(x):,.2f}"
    except Exception:
        return str(x)


def _parse_date(x: Optional[str]) -> Optional[date]:
    if not x:
        return None
    try:
        # supports 'YYYY-MM-DD' and 'YYYY-MM-DD hh:mm:ss' and ISO with Z
        return pd.to_datetime(str(x).rstrip("Z"), errors="coerce").date()
    except Exception:
        return None


def transform_api_to_frames(api_json: Dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Transform your /bills API payload into the tables used by the report.
    Returns (cards_df, utilities_df, raw_df, history_df)
    """
    bills = api_json.get("bills", []) or []
    df = pd.DataFrame(bills)

    # Normalize/ensure columns exist
    for col in ["due_date", "sent_date", "paid_at", "created_at"]:
        if col in df.columns:
            df[col] = df[col].astype(str)

    # Derive common fields
    df["due_date_d"] = df["due_date"].apply(_parse_date)
    df["sent_date_d"] = df["sent_date"].apply(_parse_date)
    df["paid_date_d"] = df.get("paid_at", pd.Series([None]*len(df))).apply(_parse_date)

    # Amount as float
    if "amount" in df.columns:
        df["amount_f"] = pd.to_numeric(df["amount"], errors="coerce")
    else:
        df["amount_f"] = 0.0

    # Split by category; your sample only has credit_card, but we'll keep it generic
    cards_raw = df.loc[df["category"].fillna("").str.lower().eq("credit_card")].copy()
    utils_raw = df.loc[~df["category"].fillna("").str.lower().eq("credit_card")].copy()

    # ---- Credit Cards table mapping ----
    # Map API → report schema
    cards = pd.DataFrame({
        "id": cards_raw.get("id"),
        "card": cards_raw.get("name"),
        "status": cards_raw.get("status"),
        # Use sent_date as proxy for statement_date (fits email statement date semantics)
        "statement_date": cards_raw.get("sent_date_d"),
        "due_date": cards_raw.get("due_date_d"),
        "total_due": cards_raw.get("amount_f"),
        "min_due": np.nan,  # not provided by API
        "amount_paid": np.where(cards_raw.get("status", "").str.lower().eq("paid"), cards_raw.get("amount_f"), 0.0),
        "payment_date": cards_raw.get("paid_date_d"),
        "remaining_balance": np.where(cards_raw.get("status", "").str.lower().eq("paid"), 0.0, cards_raw.get("amount_f")),
        "remarks": cards_raw.get("notes"),
        "auto_debit": False,  # unknown from API
        "pdf_path": cards_raw.get("drive_file_name"),
    })

    # ---- Utilities & Subscriptions mapping ----
    # Your API doesn't supply these fields yet; derive a minimal table if any non-CC exist
    utils = pd.DataFrame()
    if not utils_raw.empty:
        utils = pd.DataFrame({
            "provider": utils_raw.get("name"),
            "bill_period_start": utils_raw.get("sent_date_d"),  # best-effort proxy
            "bill_period_end": utils_raw.get("sent_date_d"),
            "due_date": utils_raw.get("due_date_d"),
            "amount": utils_raw.get("amount_f"),
            "status": utils_raw.get("status"),
            "paid_date": utils_raw.get("paid_date_d"),
            "method": None,
            "remarks": utils_raw.get("notes"),
            "pdf_path": utils_raw.get("drive_file_name"),
        })

    # ---- Raw Extract Appendix ----
    raw = pd.DataFrame({
        "name": df.get("name"),
        "sent_date": df.get("sent_date_d"),
        "path": df.get("drive_file_name"),
        "extracted_fields": None,
        "success": np.where(df.get("status", "").str.lower().eq("paid"), 1, 1),  # extraction success unknown
        "duration_sec": None,
    })

    # ---- History (monthly aggregates) ----
    # Build a small history from available records by month using sent_date as statement proxy
    if not cards.empty:
        cards_hist = (
            cards.assign(month=pd.to_datetime(cards["statement_date"]).dt.to_period("M").astype(str))
                 .groupby("month", dropna=True)["total_due"].sum()
                 .rename("credit_cards")
        )
    else:
        cards_hist = pd.Series(dtype=float)
    if not utils.empty:
        utils_hist = (
            utils.assign(month=pd.to_datetime(utils["due_date"]).dt.to_period("M").astype(str))
                 .groupby("month", dropna=True)["amount"].sum()
                 .rename("utilities")
        )
    else:
        utils_hist = pd.Series(dtype=float)
    hist = pd.concat([cards_hist, utils_hist], axis=1).fillna(0.0)
    if hist.empty:
        hist = pd.DataFrame({"month": [], "credit_cards": [], "utilities": [], "total": []})
    else:
        hist = hist.reset_index().rename(columns={"index": "month"})
        hist["total"] = hist.get("credit_cards", 0.0) + hist.get("utilities", 0.0)

    return cards, utils, raw, hist


# -----------------------------
# UI – Data Ingestion
# -----------------------------
st.title("🧾 LedgerX – Bills Report (API-driven)")
st.caption("Auto-adapts to your /bills API format. Paste JSON or fetch from a URL.")

with st.sidebar:
    st.header("Data Source")
    mode = st.radio("Choose input method", ["Paste JSON", "Fetch from API"], horizontal=True)

    api_json: Dict[str, Any] | None = None

    if mode == "Paste JSON":
        sample = {
            "status": "Success",
            "bills": [
                {"id": 1, "name": "BPI Rewards", "due_date": "2025-09-17", "amount": "37265.35", "status": "unpaid"},
                {"id": 2, "name": "BPI Rewards", "due_date": "2025-10-20", "amount": "27977.21", "status": "unpaid"},
                {"id": 3, "name": "HSBC Gold Visa", "due_date": "2025-11-03", "amount": "5617.13", "status": "unpaid"},
            ],
        }
        default_text = json.dumps(sample, indent=2)
        raw_text = st.text_area("Paste your /bills JSON here", value=default_text, height=250)
        try:
            api_json = json.loads(raw_text)
            st.session_state["api_json"] = api_json
            st.session_state["auto_fetch_done"] = False  # reset
        except Exception as e:
            st.error(f"Invalid JSON: {e}")
            api_json = None

    else:
        default_url = st.session_state.get("last_url") or f"{settings.API}/get_bills"
        url = st.text_input("API URL (GET)", value=default_url)
        go = st.button("Fetch")

        # Manual fetch button
        if go:
            try:
                resp = requests.get(url, timeout=20)
                resp.raise_for_status()
                st.session_state["api_json"] = resp.json()
                st.session_state["last_url"] = url
                st.session_state["auto_fetch_done"] = True
                st.success("Fetched successfully.")
            except Exception as e:
                st.error(f"Fetch failed: {e}")

        # Automatic re-fetch on reload if same URL was used before
        elif (
            st.session_state.get("last_url") == url
            and not st.session_state.get("auto_fetch_done")
            and url
        ):
            try:
                resp = requests.get(url, timeout=20)
                resp.raise_for_status()
                st.session_state["api_json"] = resp.json()
                st.session_state["auto_fetch_done"] = True
                st.info(f"Auto-fetched data from {url}")
            except Exception as e:
                st.warning(f"Auto-fetch skipped: {e}")

# ---------- Use fetched or pasted data ----------
api_json = st.session_state.get("api_json")
if not api_json:
    st.info("Provide JSON (sidebar) to render the report.")
    st.stop()

# Transform
cards_m, utils_m, raw_view, hist = transform_api_to_frames(api_json)

# Month selector driven by available dates
all_dates = pd.concat([
    pd.to_datetime(cards_m.get("statement_date"), errors="coerce"),
    pd.to_datetime(utils_m.get("due_date"), errors="coerce")
]).dropna()

if all_dates.empty:
    default_period = pd.Period(date.today(), freq="M")
    period_options = [str(default_period)]
else:
    months = sorted(all_dates.dt.to_period("M").astype(str).unique())
    period_options = months

sel_month = st.selectbox("Report Month", options=period_options, index=len(period_options)-1)

# Filter by selected month
mask_cards = pd.to_datetime(cards_m["statement_date"], errors="coerce").dt.to_period("M").astype(str).eq(sel_month)
mask_utils = pd.to_datetime(utils_m.get("due_date"), errors="coerce").dt.to_period("M").astype(str).eq(sel_month) if not utils_m.empty else pd.Series([], dtype=bool)
cards_month = cards_m.loc[mask_cards].copy()
utils_month = utils_m.loc[mask_utils].copy() if not utils_m.empty else pd.DataFrame(columns=["amount", "status", "due_date", "provider", "paid_date", "method", "remarks", "pdf_path"]) 

# -----------------------------
# 1) Summary Dashboard
# -----------------------------
st.subheader("1) Summary Dashboard")

this_month_paid = (cards_month.get("amount_paid", pd.Series(0.0)).sum() + utils_month.get("amount", pd.Series(0.0)).where(utils_month.get("status", "").str.lower().eq("paid"), 0.0).sum())
last_month = str((pd.Period(sel_month, freq="M") - 1))
mask_cards_prev = pd.to_datetime(cards_m["statement_date"], errors="coerce").dt.to_period("M").astype(str).eq(last_month)
mask_utils_prev = pd.to_datetime(utils_m.get("due_date"), errors="coerce").dt.to_period("M").astype(str).eq(last_month) if not utils_m.empty else pd.Series([], dtype=bool)
last_month_paid = (cards_m.loc[mask_cards_prev, "amount_paid"].sum() + utils_m.loc[mask_utils_prev & utils_m.get("status", "").str.lower().eq("paid"), "amount"].sum()) if not utils_m.empty else cards_m.loc[mask_cards_prev, "amount_paid"].sum()

credit_total_due = cards_month.get("total_due", pd.Series(0.0)).sum()
utilities_total_due = utils_month.get("amount", pd.Series(0.0)).sum()

# Upcoming 7 days (from today)
_today = date.today()
upcoming_7 = (
    cards_month.loc[(pd.to_datetime(cards_month["due_date"]).dt.date >= _today) & (pd.to_datetime(cards_month["due_date"]).dt.date <= _today + timedelta(days=7)), "total_due"].sum()
    + utils_month.loc[(pd.to_datetime(utils_month["due_date"]).dt.date >= _today) & (pd.to_datetime(utils_month["due_date"]).dt.date <= _today + timedelta(days=7)), "amount"].sum()
)

# Avg delay (only utilities have paid_date/due_date reliably; cards use payment_date)
util_delays = (pd.to_datetime(utils_month.get("paid_date"), errors="coerce") - pd.to_datetime(utils_month.get("due_date"), errors="coerce")).dt.days.dropna()
card_delays = (pd.to_datetime(cards_month.get("payment_date"), errors="coerce") - pd.to_datetime(cards_month.get("due_date"), errors="coerce")).dt.days.dropna()
all_delays = pd.concat([util_delays, card_delays])
avg_delay = all_delays.mean() if not all_delays.empty else np.nan

# Auto-paid rate (unknown → assume False)
auto_paid_rate = float(cards_month.get("auto_debit", pd.Series([False]*len(cards_month))).mean())

col1, col2, col3, col4, col5, col6 = st.columns([1.8, 1.8, 1.2, 1.3, 1.1, 1.1])
col1.metric("Total Bills Paid (This Month)", _peso(this_month_paid), _peso(this_month_paid - last_month_paid))
col2.metric("Credit Card Total Due", _peso(credit_total_due))
col3.metric("Utilities Total Due", _peso(utilities_total_due))
col4.metric("Upcoming Due (7 days)", _peso(upcoming_7))
col5.metric("Avg Delay (days)", f"{avg_delay:.1f}" if not np.isnan(avg_delay) else "—")
col6.metric("Auto-Paid (%)", f"{auto_paid_rate*100:.0f}%")

paid_total = this_month_paid
total_target = credit_total_due + utilities_total_due
progress_ratio = (paid_total / total_target) if total_target > 0 else 1.0
st.progress(min(max(progress_ratio, 0.0), 1.0), text=f"{_peso(paid_total)} / {_peso(total_target)} paid this period")

# -----------------------------
# 2) Credit Card Section
# -----------------------------
st.subheader("2) Credit Cards")
cc_cols = ["card","statement_date","due_date","total_due","payment_date","remaining_balance","remarks","auto_debit","pdf_path", "status", "id"]
show_cards = cards_month.copy()
for c in ["statement_date","due_date","payment_date"]:
    if c in show_cards:
        show_cards[c] = pd.to_datetime(show_cards[c], errors="coerce").dt.date.astype(str)

#st.dataframe(
#    show_cards[ [c for c in cc_cols if c in show_cards.columns] ]
#        .rename(columns={
#            "card":"Card","statement_date":"Statement Date","due_date":"Due Date","total_due":"Total Due",
#            "payment_date":"Payment Date","remaining_balance":"Remaining Balance","remarks":"Remarks",
#            "pdf_path":"PDF Path"
#        }),
#    width='stretch',
#    hide_index=True,
#)
import os
st.markdown("### Bills")
header = st.columns([3, 2, 2, 1.5, 2, 2])
header[0].markdown("**Name**")
header[1].markdown("**Due Date**")
header[2].markdown("**Amount**")
header[3].markdown("**Status**")
header[4].markdown("**PDF**")
header[5].markdown("**Action**")

for _, row in cards_month.iterrows():
    c1, c2, c3, c4, c5, c6 = st.columns([3, 2, 2, 1.5, 2, 2])
    bill_id = row.get("id")
    name = row.get("card", "")
    due = row.get("due_date", "")
    amt = row.get("total_due", 0.0)
    status = str(row.get("status", "")).lower()
    pdf_path = row.get("pdf_path", "")

    c1.write(name)
    c2.write(str(due))
    c3.write(_peso(float(amt)))
    c4.write(status.capitalize() if status else "—")

    # --- PDF button ---
    if isinstance(pdf_path, str) and pdf_path:
        if pdf_path.startswith(("http://", "https://")):
            # open in new tab
            c5.link_button("Open PDF", pdf_path, key=f"pdf_link_{bill_id}")
        else:
            # local file -> download button
            try:
                with open(pdf_path, "rb") as f:
                    c5.download_button(
                        "Download PDF",
                        data=f,
                        file_name=os.path.basename(pdf_path),
                        key=f"pdf_dl_{bill_id}",
                    )
            except Exception as e:
                c5.error("PDF not found")

    # --- Pay button (calls API) ---
    disabled = status == "paid"
    c6.button(
        "Paid" if disabled else "Pay",
        key=f"pay_{bill_id}",
        disabled=disabled,
        on_click=_queue_pay,
        args=(bill_id, disabled),
        use_container_width=True,
    )

# ---------- Handle queued payment once, after rendering ----------
paying_id = st.session_state.get("paying_id")
if paying_id and not st.session_state.get("pay_inflight"):
    st.session_state["pay_inflight"] = True
    with st.spinner(f"Processing payment for {paying_id}..."):
        try:
            # Choose ONE style. Example below assumes RESTful:
            # settings.API should be the /bills base, e.g., https://api.example.com/bills
            resp = requests.post(
                f"{settings.API}/{paying_id}/pay",
                timeout=30,
            )
            if resp.ok:
                st.success(f"Bill {paying_id} marked as paid.")
                # Clear queued action so rerun doesn't repeat the call
                st.session_state["paying_id"] = None
                # If you repopulate 'cards_month' from API, you can allow natural rerun.
                # If you need an immediate refresh of cached data, uncomment:
                # st.rerun()
            else:
                st.error(f"Payment failed: {resp.status_code} {resp.text}")
                st.session_state["paying_id"] = None
        except Exception as e:
            st.error(f"Payment error: {e}")
            st.session_state["paying_id"] = None
        finally:
            st.session_state["pay_inflight"] = False

# -----------------------------
# 3) Utilities & Subscriptions (if any)
# -----------------------------
st.subheader("3) Utilities & Subscriptions")
if utils_month.empty:
    st.info("No utilities/subscriptions found in this API response.")
else:
    utils_view = utils_month.copy()
    utils_view["bill_period"] = utils_view.apply(lambda r: f"{r.get('bill_period_start')} – {r.get('bill_period_end')}", axis=1)
    utils_cols = ["provider","bill_period","due_date","amount","status","paid_date","method","remarks","pdf_path"]
    st.dataframe(
        utils_view[[c for c in utils_cols if c in utils_view.columns]]
            .rename(columns={"provider":"Provider","bill_period":"Bill Period","due_date":"Due Date","amount":"Amount","status":"Status","paid_date":"Paid Date","method":"Method","remarks":"Remarks","pdf_path":"PDF Path"}),
        width='stretch',
        hide_index=True,
    )

# -----------------------------
# 4) Upcoming & Overdue Alerts
# -----------------------------
st.subheader("4) Upcoming & Overdue Alerts")
_today = date.today()
alerts_cc = cards_month[["card","due_date","total_due"]].rename(columns={"card":"bill","total_due":"amount"}) if not cards_month.empty else pd.DataFrame(columns=["bill","due_date","amount"]) 
alerts_ut = utils_month[["provider","due_date","amount"]].rename(columns={"provider":"bill"}) if not utils_month.empty else pd.DataFrame(columns=["bill","due_date","amount"]) 
alerts = pd.concat([alerts_cc, alerts_ut], ignore_index=True)
if not alerts.empty:
    alerts["days_left"] = alerts["due_date"].apply(lambda d: (pd.to_datetime(d).date() - _today).days if pd.notna(d) else np.nan)
    alerts["status"] = np.where(alerts["days_left"] < 0, "Overdue", np.where(alerts["days_left"] <= 7, "Due soon", "Pending"))
    alerts = alerts.sort_values(["status","days_left"], ascending=[True, True])
    st.dataframe(alerts.rename(columns={"bill":"Bill","due_date":"Due Date","amount":"Amount","days_left":"Days Left","status":"Status"}), width='stretch', hide_index=True)
else:
    st.info("No upcoming or overdue items for the selected month.")

# -----------------------------
# 5) Visual Analytics
# -----------------------------
st.subheader("5) Visual Analytics")
if hist is not None and not hist.empty:
    col_a, col_b = st.columns(2)

    with col_a:
        ycols = [c for c in ["credit_cards", "utilities"] if c in hist.columns]
        if ycols:
            fig_bar = px.bar(
                hist,
                x="month",
                y=ycols,
                barmode="group",
                title="Monthly Spend Trend"
            )
            st.plotly_chart(fig_bar, config={"responsive": True}, use_container_width=True)
        else:
            st.warning("No matching columns ('credit_cards' or 'utilities') found.")

    with col_b:
        if "total" in hist.columns:
            fig_line = px.line(
                hist,
                x="month",
                y="total",
                markers=True,
                title="Total Bills Over Time"
            )
            st.plotly_chart(fig_line, config={"responsive": True}, use_container_width=True)
        else:
            st.warning("Column 'total' not found in historical data.")
else:
    st.info("Not enough history to plot trends yet. Add more months of data.")

# -----------------------------
# 6) Raw Extract (Appendix)
# -----------------------------
st.subheader("6) Raw Extract (Appendix)")
raw_show = raw_view.copy()
if "sent_date" in raw_show:
    raw_show["sent_date"] = pd.to_datetime(raw_show["sent_date"], errors="coerce").dt.date
st.dataframe(
    raw_show.rename(columns={
        "name": "Name",
        "sent_date": "Sent Date",
        "path": "Path",
        "extracted_fields": "Extracted Fields",
        "success": "Success",
        "duration_sec": "Duration (sec)",
    }),
    width='stretch',
    hide_index=True,
)

# -----------------------------
# Export Section
# -----------------------------
st.markdown("---")
st.subheader("Export Report")

def _build_excel(cards: pd.DataFrame, utils: pd.DataFrame, alerts: pd.DataFrame, raw: pd.DataFrame, hist: pd.DataFrame, sel_month: str) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        # Summary
        summary_df = pd.DataFrame({
            "Metric": [
                "Total Bills Paid (This Month)",
                "Credit Card Total Due",
                "Utilities Total Due",
                "Upcoming Due (7 days)",
            ],
            "Value": [this_month_paid, credit_total_due, utilities_total_due, upcoming_7],
        })
        summary_df.to_excel(writer, sheet_name="Summary", index=False)

        # Sheets
        cards.to_excel(writer, sheet_name="CreditCards", index=False)
        (utils if utils is not None else pd.DataFrame()).to_excel(writer, sheet_name="Utilities", index=False)
        (alerts if alerts is not None else pd.DataFrame()).to_excel(writer, sheet_name="Alerts", index=False)
        raw.to_excel(writer, sheet_name="RawExtract", index=False)
        (hist if hist is not None else pd.DataFrame()).to_excel(writer, sheet_name="History", index=False)

        # Basic formatting
        wb = writer.book
        peso_fmt = wb.add_format({"num_format": "₱#,##0.00"})
        try:
            ws = writer.sheets["Summary"]
            ws.set_column("A:A", 35)
            ws.set_column("B:B", 22, peso_fmt)
        except Exception:
            pass
    output.seek(0)
    return output.read()

# Build Alerts df for export scope
_today = date.today()
alerts_cc_all = cards_m[["card","due_date","total_due"]].rename(columns={"card":"bill","total_due":"amount"}) if not cards_m.empty else pd.DataFrame(columns=["bill","due_date","amount"]) 
alerts_ut_all = utils_m[["provider","due_date","amount"]].rename(columns={"provider":"bill"}) if not utils_m.empty else pd.DataFrame(columns=["bill","due_date","amount"]) 
alerts_all = pd.concat([alerts_cc_all, alerts_ut_all], ignore_index=True)
if not alerts_all.empty:
    alerts_all["days_left"] = alerts_all["due_date"].apply(lambda d: (pd.to_datetime(d).date() - _today).days if pd.notna(d) else np.nan)
    alerts_all["status"] = np.where(alerts_all["days_left"] < 0, "Overdue", np.where(alerts_all["days_left"] <= 7, "Due soon", "Pending"))

excel_bytes = _build_excel(cards_month, utils_month, alerts_all, raw_view, hist, sel_month)
st.download_button(
    label="⬇️ Download XLSX",
    data=excel_bytes,
    file_name=f"ledgerx_report_{sel_month}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

# -----------------------------
# Integration Notes
# -----------------------------
with st.expander("Integration Notes – mapping from API to report"):
    st.markdown(
        """
        **Mapped fields (credit cards):**
        - `name` → `card`
        - `sent_date` → `statement_date` (proxy)
        - `due_date` → `due_date`
        - `amount` → `total_due`
        - `paid_at` → `payment_date`
        - `status` → used for `amount_paid` (paid = amount, else 0) and `remaining_balance`
        - `drive_file_name` → `pdf_path`

        **Utilities/Subs:** Not present in your sample. If your API returns `category != 'credit_card'`, those rows will appear under Utilities with best-effort columns.

        **Next enhancements:**
        - If your API can add `min_due`, `auto_debit`, and proper `bill_period_start`/`bill_period_end`, the app will show them automatically.
        - Provide historical months for better charts (we aggregate per month).
        """
    )

st.success("App adapted to your /bills API. Paste JSON or fetch from your endpoint in the sidebar.")