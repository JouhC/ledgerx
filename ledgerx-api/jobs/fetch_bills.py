from integrations.gmail_service import extract_bills
from db.database import get_bill_sources

def fetch_bills_for_all_sources():
    sources = get_bill_sources()
    all_new_bills = []
    for source in sources:
        new_bills = extract_bills(source)
        all_new_bills.extend(new_bills)
    return all_new_bills


def main():
    sources = get_bill_sources()
    print(sources)