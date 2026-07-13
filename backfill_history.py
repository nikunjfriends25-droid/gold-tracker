"""
Fetches 6 months of real XAU/INR history from goldapi.io (one call per week = 26 API calls),
converts to estimated Indian retail prices using today's city premium ratios,
and inserts daily interpolated data into the DB.

Run once: python backfill_history.py
Uses ~26 of the 100 calls/month goldapi free tier.
"""
import requests
import time
from datetime import date, timedelta
from db import init_db, get_conn, get_config
from config import ALL_CITIES, CITIES_TN, CITIES_KL

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# Premium multiplier: GoodReturns retail / goldapi spot (verified 2026-06-28)
# TN cities historically trade ~1.7% higher than KL cities
CITY_PREMIUM = {
    'Chennai':            {'22K': 1.176, '24K': 1.176},
    'Coimbatore':         {'22K': 1.176, '24K': 1.176},
    'Madurai':            {'22K': 1.176, '24K': 1.176},
    'Tirupur':            {'22K': 1.176, '24K': 1.176},
    'Kozhikode':          {'22K': 1.160, '24K': 1.161},
    'Kochi':              {'22K': 1.160, '24K': 1.161},
    'Thrissur':           {'22K': 1.160, '24K': 1.161},
    'Thiruvananthapuram': {'22K': 1.160, '24K': 1.161},
}


def fetch_weekly_spots(days_back: int = 180) -> dict:
    """
    Fetches XAU/INR spot from goldapi for weekly dates going back `days_back` days.
    Returns dict of {date_str: {22K: price, 24K: price}}.
    """
    key = get_config('goldapi_key')
    today = date.today()
    spots = {}

    # Collect dates: every 7 days from today going back
    dates_to_fetch = []
    d = today
    while d >= today - timedelta(days=days_back):
        dates_to_fetch.append(d)
        d -= timedelta(days=7)

    print(f'Fetching {len(dates_to_fetch)} weekly reference points from goldapi...')
    for fetch_date in dates_to_fetch:
        date_str = fetch_date.strftime('%Y%m%d')
        url = f'https://www.goldapi.io/api/XAU/INR/{date_str}'
        try:
            r = requests.get(url, headers={'x-access-token': key, **HEADERS}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                p24 = data.get('price_gram_24k')
                p22 = data.get('price_gram_22k')
                if p24 and p22:
                    spots[fetch_date.isoformat()] = {'22K': p22, '24K': p24}
                    print(f'  {fetch_date}: 24K=Rs{p24:,.0f}  22K=Rs{p22:,.0f}')
            else:
                print(f'  {fetch_date}: HTTP {r.status_code}')
        except Exception as e:
            print(f'  {fetch_date}: error {e}')
        time.sleep(0.4)

    return spots


def interpolate_daily(spots: dict, days_back: int = 180) -> dict:
    """
    Given weekly spot prices, interpolates a value for every calendar day.
    Returns dict of {date_str: {22K: float, 24K: float}}.
    """
    today = date.today()
    sorted_dates = sorted(spots.keys())
    if not sorted_dates:
        return {}

    daily = {}
    start = today - timedelta(days=days_back)

    for i in range(days_back + 1):
        d = start + timedelta(days=i)
        if d >= today:
            continue
        d_str = d.isoformat()

        # Find surrounding anchor dates
        before = [s for s in sorted_dates if s <= d_str]
        after  = [s for s in sorted_dates if s >= d_str]

        if not before and not after:
            continue
        elif not before:
            # Extrapolate from earliest
            daily[d_str] = spots[after[0]]
        elif not after:
            # Extrapolate from latest
            daily[d_str] = spots[before[-1]]
        elif before[-1] == d_str:
            daily[d_str] = spots[d_str]
        else:
            # Linear interpolation
            d0, d1 = date.fromisoformat(before[-1]), date.fromisoformat(after[0])
            t = (d - d0).days / max((d1 - d0).days, 1)
            s0, s1 = spots[before[-1]], spots[after[0]]
            daily[d_str] = {
                '22K': s0['22K'] + t * (s1['22K'] - s0['22K']),
                '24K': s0['24K'] + t * (s1['24K'] - s0['24K']),
            }

    return daily


def build_rows(daily_spots: dict) -> list:
    """Convert daily spot prices → estimated Indian retail rows for all cities."""
    from datetime import datetime
    rows = []
    for d_str, spots in sorted(daily_spots.items()):
        scraped_at = f'{d_str}T09:00:00'
        for city in ALL_CITIES:
            for karat in ['22K', '24K']:
                premium = CITY_PREMIUM[city][karat]
                buy = int(spots[karat] * premium)
                sell = int(buy * 0.985)
                rows.append((scraped_at, d_str, city, karat, buy, sell, 'goldapi_backfill'))
    return rows


def run():
    init_db()

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT COUNT(*) FROM prices WHERE source='goldapi_backfill'"
        ).fetchone()[0]
        if existing > 0:
            print(f'Backfill already done ({existing} rows). Delete them first if you want to re-run.')
            print("  DELETE FROM prices WHERE source='goldapi_backfill';")
            return

        # Also remove synthetic seed data since we're replacing with real data
        seed_count = conn.execute("SELECT COUNT(*) FROM prices WHERE source='seed'").fetchone()[0]
        if seed_count > 0:
            conn.execute("DELETE FROM prices WHERE source='seed'")
            print(f'Removed {seed_count} synthetic seed rows.')

    spots = fetch_weekly_spots(days_back=180)
    if not spots:
        print('No data fetched. Check goldapi key and quota.')
        return

    daily = interpolate_daily(spots, days_back=180)
    rows = build_rows(daily)

    with get_conn() as conn:
        conn.executemany(
            'INSERT OR IGNORE INTO prices (scraped_at, date, city, karat, buy_price, sell_price, source) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            rows
        )

    print(f'\nInserted {len(rows)} rows of 6-month history ({len(daily)} days × {len(ALL_CITIES)} cities × 2 karats).')
    print('Chart now has real XAU/INR-based price history.')


if __name__ == '__main__':
    run()
