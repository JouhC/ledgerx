from db.database import db_all
from datetime import datetime



def remind_me(bill_value):
    today = datetime.now()
    days_before_due = (due_date - today).days

    if days_before_due > 5:
        trigger if day_of_week == preferred_day  # weekly
    elif 0 < days_before_due <= 5:
        trigger daily
    elif days_before_due == 0:
        trigger "due today"