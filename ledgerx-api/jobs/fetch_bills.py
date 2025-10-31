from integrations.gmail_service import extract_bills
from db.database import get_bill_sources
from utils.bill_parser import parse_bill_pdf

def fetch_bills_for_all_sources():
    sources = get_bill_sources()
    all_new_bills = []
    for source in sources:
        new_bills = extract_bills(source)
        all_new_bills.extend(new_bills)
    return all_new_bills


def main():
    sources = get_bill_sources()

    for source in sources:
        print(f"Fetching bills for source: {source}")
        query = source['query']
        bills_path = extract_bills(query)
        for bill_pdf in bills_path:
            bill_data = parse_bill_pdf(bill_pdf, source)
            print(f"Extracted bill data: {bill_data}")
        


    print(sources)