from integrations.gmail_service import extract_bills
from db.database import get_bill_sources, insert_or_update_last_run, get_last_run, db_insert_bill, bill_exists
from jobs.gdrive_job import create_folder_structure, upload_pdf
from utils.bill_preprocessing import extract_bill_fields
from utils.field_extractor import load_model
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
tokenizer, model = load_model()
required_fields = settings.REQUIRED_FIELDS


@retry()
async def extract_bill_fields_async(value: Dict[str, Any], required_fields: List[str]) -> Optional[Dict[str, Any]]:
    # wrap the blocking/CPU work (OCR/regex/PDF) off the event loop
    return await run_blocking(extract_bill_fields, value, required_fields, model=model, tokenizer=tokenizer)

async def process_single_bill(value: Dict[str, Any], folders: Dict[str, str], sem: asyncio.Semaphore, required_fields: List[str] = settings.REQUIRED_FIELDS):
    async with sem:
        try:
            # quick existence check first to avoid wasted OCR
            exists = await run_blocking(bill_exists, value)
            if exists:
                print(f"Bill already exists in database: {value['name']} sent at {value['sent_date']}")
                return

            bill_data, dec_path = await extract_bill_fields_async(value, required_fields)
            if not bill_data:
                print(f"⚠️ No fields extracted for {value['bills_path']}")
                # still write a last_run with success=0 to avoid infinite retries spiking?
                await run_blocking(insert_or_update_last_run, {
                    "name": value["name"],
                    "success": False,
                    "duration_sec": (_now() - value["start_time"]).total_seconds()
                })
                return
            
            drive_file_id = await upload_pdf(dec_path, folders["subfolders"][value["name"]], f"{value['outname']}")

            # make insert idempotent at the DB layer too (unique constraint on (name, sent_date, amount) and use UPSERT)
            record = {
                "name": value["name"],
                "customer_number": bill_data.get("customer_number"),
                "statement_date": bill_data.get("statement_date"),
                "due_date": bill_data.get("payment_due_date"),
                "sent_date": value["sent_date"],
                "credit_limit": str(bill_data.get("credit_limit")),
                "total_amount_due": str(bill_data.get("total_amount_due")),
                "minimum_amount_due": str(bill_data.get("minimum_amount_due")),
                "currency": "PHP",
                "status": "unpaid",
                "source_email_id": value["message_id"],
                "drive_file_id": drive_file_id,
                "drive_file_name": value['outname'],
                "category": value.get("category", "uncategorized"),
            }
            await run_blocking(db_insert_bill, record)
            await run_blocking(insert_or_update_last_run, {
                "name": value["name"],
                "success": True,
                "duration_sec": (_now() - value["start_time"]).total_seconds()
            })
            print(f"Extracted bill data: {bill_data}")
        
        except Exception as e:
            print(f"Error processing bill {value['bills_path']}: {e}")

        finally:
            if dec_path is not None and dec_path.exists():
                try:
                    dec_path.unlink(missing_ok=True)
                except Exception:
                    pass


async def process_source(source: Dict[str, Any], folders: Dict[str, str], bill_sem: asyncio.Semaphore):
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

    encrypted_password = source['encrypted_password']

    # fetch list of bills (blocking I/O), then fan out per bill
    bills_path = await run_blocking(extract_bills, source)
    print(f"Fetched {len(bills_path)} new bills for source {source['name']}.")

    tasks = []
    for idx, (message_id, sent_date, path, outname) in enumerate(bills_path, start=1):
        value = {
            "name": source["name"],
            "sent_date": sent_date,
            "bills_path": path,
            "encrypted_password": encrypted_password,
            "start_time": _now(),
            "label": f"{source['name']} {idx}",
            "category": source.get("category", "uncategorized"),
            "useful_page": source.get("useful_page", [1]),
            "outname": outname,
            "message_id": message_id,
        }
        tasks.append(asyncio.create_task(process_single_bill(value, folders, bill_sem)))

    if tasks:
        await asyncio.gather(*tasks)


async def run_fetch_all_async():
    try:
        sources = await asyncio.to_thread(get_bill_sources)
        bill_sem = asyncio.Semaphore(5)

        folders = await create_folder_structure(sources)

        for source in sources:
            await process_source(source, folders, bill_sem)


    except Exception as e:
        print(f"Error in run_fetch_all_async: {e}")
        raise


# convenience sync entrypoint
def run_fetch_all():
    asyncio.run(run_fetch_all_async())


if __name__ == "__main__":
    run_fetch_all()