from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

def run_daily_scrape():
    from scraper import scrape_all
    from db import insert_prices
    print(f'[scheduler] Daily scrape at {datetime.now().isoformat()}')
    rows = scrape_all()
    if rows:
        insert_prices(rows)
        print(f'[scheduler] Inserted {len(rows)} rows')
    else:
        print('[scheduler] Scrape returned no data')

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_daily_scrape, 'cron', hour=9, minute=0)
    scheduler.start()
    print('[scheduler] Started — daily scrape at 09:00')
