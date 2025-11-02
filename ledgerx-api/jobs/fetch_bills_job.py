from integrations.gmail_service import extract_bills
from db.database import get_bill_sources, insert_or_update_last_run, get_last_run, db_insert_bill, bill_exists
from utils.bill_parser_v2 import extract_bill_fields
from core.config import settings
from datetime import datetime, timedelta

def fetch_bills_for_all_sources():
    sources = get_bill_sources()
    all_new_bills = []
    for source in sources:
        new_bills = extract_bills(source)
        all_new_bills.extend(new_bills)
    return all_new_bills

def main():
    sources = get_bill_sources()
    result_dict = {}

    for source in sources:
        last_run = get_last_run(source["name"])
        if last_run:
            print(last_run)
            last_fetch_at = last_run[0]
            if last_fetch_at:
                try:
                    # support ISO strings with a trailing 'Z'
                    last_fetch = datetime.fromisoformat(last_fetch_at.rstrip("Z"))
                except Exception:
                    print(f"Could not parse last_fetch_at for {source['name']}: {last_fetch_at}")
                else:
                    if datetime.now() - last_fetch < timedelta(days=1):
                        print(f"Skipping source {source['name']} as it was fetched less than 1 day ago.")
                        continue
        password = settings.model_extra[source['password_env']] if source['password_env'] != "None" else ""
        bills_path = extract_bills(source)

        print(f"Fetched {len(bills_path)} new bills for source {source['name']}.")
        
        counter = 1
        for bills in bills_path:
            result_dict[f"{source['name']} {counter}"] = {
                "name": source['name'],
                "sent_date": bills[0],
                "bills_path": bills[1],
                "password": password,
                "start_time": datetime.now()
            }
            counter += 1
    
    for key, value in result_dict.items():
        if bill_exists(value):
            print(f"Bill already exists in database: {value['name']} sent at {value['sent_date']}")
            continue

        bill_data = extract_bill_fields(value["bills_path"], password=value["password"], lang="eng")
        if bill_data:
            db_insert_bill({
                "name":value["name"],
                "due_date": bill_data.get("payment_due_date"),
                "sent_date": value["sent_date"],
                "amount": str(bill_data.get("total_amount_due")),
                "currency": "PHP",
                "status": "unpaid",
                "source_email_id": None,
                "drive_file_id": None,
                "drive_file_name": value["bills_path"]})
            
            insert_or_update_last_run({
                "name":value["name"],
                "success": 1,
                "duration_sec": (datetime.now() - value["start_time"]).total_seconds()})
            print(f"Extracted bill data: {bill_data}")

if __name__ == "__main__":
    main()