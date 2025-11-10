from integrations.gmail_service import extract_bills
from db.database import get_bill_sources, insert_or_update_last_run, get_last_run, db_insert_bill, bill_exists
from utils.bill_parser_v2 import extract_bill_fields
from core.config import settings
from datetime import datetime, timedelta

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple, Optional
from services.progress import PROGRESS

# ---- tiny helpers -----------------------------------------------------------

def _now():
    return datetime.now()

async def run_blocking(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)

def retry(backoff=(0.5, 1.0, 2.0), exceptions=(Exception,)):
    def deco(fn):
        async def wrapped(*args, **kwargs):
            last = None
            for i, delay in enumerate(backoff + (float('inf'),), 1):
                try:
                    return await fn(*args, **kwargs)
                except exceptions as e:
                    last = e
                    if delay == float('inf'):
                        print(f"Function {fn.__name__} failed after {i} attempts.")
                        raise
                    await asyncio.sleep(delay)
            raise last
        return wrapped
    return deco


CONCURRENCY_PER_BILL = 4   # tune: start with 4-8 for mixed IO/CPU
CONCURRENCY_PER_SOURCE = 2 # if sources fetch from network/drive
LANG = "eng"

@retry()
async def extract_bill_fields_async(path: str, password: str) -> Optional[Dict[str, Any]]:
    # wrap the blocking/CPU work (OCR/regex/PDF) off the event loop
    return await run_blocking(extract_bill_fields, path, password=password, lang=LANG)

async def process_single_bill(value: Dict[str, Any], sem: asyncio.Semaphore):
    async with sem:
        # quick existence check first to avoid wasted OCR
        exists = await run_blocking(bill_exists, value)
        if exists:
            print(f"Bill already exists in database: {value['name']} sent at {value['sent_date']}")
            return

        bill_data = await extract_bill_fields_async(value["bills_path"], password=value["password"])
        if not bill_data:
            print(f"⚠️ No fields extracted for {value['bills_path']}")
            # still write a last_run with success=0 to avoid infinite retries spiking?
            await run_blocking(insert_or_update_last_run, {
                "name": value["name"],
                "success": 0,
                "duration_sec": (_now() - value["start_time"]).total_seconds()
            })
            return

        # make insert idempotent at the DB layer too (unique constraint on (name, sent_date, amount) and use UPSERT)
        record = {
            "name": value["name"],
            "due_date": bill_data.get("payment_due_date"),
            "sent_date": value["sent_date"],
            "amount": str(bill_data.get("total_amount_due")),
            "currency": "PHP",
            "status": "unpaid",
            "source_email_id": None,
            "drive_file_id": None,
            "drive_file_name": value["bills_path"],
            "category": value.get("category", "uncategorized"),
        }
        await run_blocking(db_insert_bill, record)
        await run_blocking(insert_or_update_last_run, {
            "name": value["name"],
            "success": 1,
            "duration_sec": (_now() - value["start_time"]).total_seconds()
        })
        print(f"Extracted bill data: {bill_data}")

async def process_source(source: Dict[str, Any], bill_sem: asyncio.Semaphore):
    # 1-day skip
    last_run = await run_blocking(get_last_run, source["name"])
    if last_run:
        last_fetch_at = last_run[0]
        if last_fetch_at:
            try:
                last_fetch = datetime.fromisoformat(str(last_fetch_at).rstrip("Z"))
            except Exception:
                print(f"Could not parse last_fetch_at for {source['name']}: {last_fetch_at}")
            else:
                if _now() - last_fetch < timedelta(days=1):
                    print(f"Skipping source {source['name']} as it was fetched less than 1 day ago.")
                    return

    password = settings.model_extra[source['password_env']] if source['password_env'] != "None" else ""

    # fetch list of bills (blocking I/O), then fan out per bill
    bills_path: List[Tuple[str, str]] = await run_blocking(extract_bills, source)
    print(f"Fetched {len(bills_path)} new bills for source {source['name']}.")

    tasks = []
    for idx, (sent_date, path) in enumerate(bills_path, start=1):
        value = {
            "name": source["name"],
            "sent_date": sent_date,
            "bills_path": path,
            "password": password,
            "start_time": _now(),
            "label": f"{source['name']} {idx}",
            "category": source.get("category", "uncategorized"),
        }
        tasks.append(asyncio.create_task(process_single_bill(value, bill_sem)))

    if tasks:
        await asyncio.gather(*tasks)

async def run_fetch_all_async():
    try:
        sources = await asyncio.to_thread(get_bill_sources)
        bill_sem = asyncio.Semaphore(5)

        for source in sources:
            print(f"Processing source: {source['name']}")
            print(f"Source details: {source['category']}")
            await process_source(source, bill_sem)

    except Exception as e:
        print(f"Error in run_fetch_all_async: {e}")
        raise

# convenience sync entrypoint
def run_fetch_all():
    asyncio.run(run_fetch_all_async())

if __name__ == "__main__":
    run_fetch_all()