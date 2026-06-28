"""Run once: python setup.py"""
from db import init_db, set_config, get_config

def run_setup():
    init_db()
    print('\n=== Gold Tracker — First-time setup ===\n')

    # Step 1: goldapi.io — pre-configured, just test it
    print('Step 1 of 2: Testing goldapi.io connection...')
    gold_key = 'goldapi-6e4d33a0c3941ba5a847837604201868-io'
    set_config('goldapi_key', gold_key)
    import requests
    try:
        r = requests.get(
            'https://www.goldapi.io/api/XAU/USD',
            headers={'x-access-token': gold_key},
            timeout=8
        )
        price = r.json().get('price')
        if price:
            print(f'  OK goldapi.io working. XAU/USD: ${price:,.2f}\n')
        else:
            print(f'  WARN Unexpected response: {r.json()}\n')
    except Exception as e:
        print(f'  WARN goldapi.io failed: {e}\n')

    # Step 2: Alert thresholds
    print('Step 2 of 2: Sell alert thresholds')
    t22 = input('  22K alert price in Rs/gram (press Enter for 16000): ').strip()
    t24 = input('  24K alert price in Rs/gram (press Enter for 16000): ').strip()
    set_config('alert_22k', t22 if t22.isdigit() else '16000')
    set_config('alert_24k', t24 if t24.isdigit() else '16000')
    print(f'  Saved: 22K Rs{get_config("alert_22k")}  24K Rs{get_config("alert_24k")}\n')

    # Step 3: First scrape
    print('Running first scrape of all 8 cities...')
    from scraper import scrape_all
    from db import insert_prices
    rows = scrape_all()
    if rows:
        insert_prices(rows)
        print(f'  OK Scraped {len(rows)} rows:')
        for r in rows:
            print(f'    {r["city"]:22s} {r["karat"]}  Buy Rs{r["buy"]:,}  Sell Rs{r["sell"]:,}')
    else:
        print('  FAIL Scrape failed -- check selectors in scraper.py')

    set_config('setup_complete', '1')
    print('\n=== Done. Run: python app.py ===\n')
    print('Dashboard: http://127.0.0.1:5050')
    print('Alerts are shown in the dashboard when you open it.')
    print('Thresholds can be changed anytime from the dashboard.\n')

if __name__ == '__main__':
    run_setup()
