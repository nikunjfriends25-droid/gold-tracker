"""Run once to seed docs/data/ from existing SQLite DB."""
import json
import sqlite3
from pathlib import Path
from datetime import date, datetime

DB_PATH = Path(__file__).parent.parent / 'data' / 'gold.db'
OUT_DIR = Path(__file__).parent.parent / 'docs' / 'data'


def export():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # All historical data — one entry per city/karat/day (latest scrape of that day)
    rows = conn.execute("""
        SELECT city, karat, date, buy_price, sell_price
        FROM prices
        GROUP BY city, karat, date HAVING scraped_at = MAX(scraped_at)
        ORDER BY city, karat, date
    """).fetchall()

    history = {}
    for r in rows:
        c, k = r['city'], r['karat']
        history.setdefault(c, {}).setdefault(k, []).append({
            'date': r['date'],
            'buy_price': r['buy_price'],
            'sell_price': r['sell_price'],
        })

    (OUT_DIR / 'history.json').write_text(json.dumps(history))
    total = sum(len(v) for d in history.values() for v in d.values())
    print(f'Wrote history.json ({total} entries across {len(history)} cities)')

    # Latest available prices (today if scraped, otherwise most recent date)
    today = date.today().isoformat()
    latest_date = conn.execute(
        "SELECT MAX(date) as d FROM prices"
    ).fetchone()['d'] or today
    if latest_date != today:
        print(f'No data for today ({today}), using latest available: {latest_date}')
    today_rows = conn.execute("""
        SELECT city, karat, buy_price, sell_price, scraped_at
        FROM prices WHERE date = ?
        GROUP BY city, karat HAVING scraped_at = MAX(scraped_at)
    """, (latest_date,)).fetchall()

    if not today_rows:
        print(f'No data in DB at all — prices.json will have empty data')

    data = {}
    for r in today_rows:
        city, karat = r['city'], r['karat']

        # Previous day buy price
        prev = conn.execute("""
            SELECT buy_price FROM prices
            WHERE city = ? AND karat = ? AND date < ?
            GROUP BY date HAVING scraped_at = MAX(scraped_at)
            ORDER BY date DESC LIMIT 1
        """, (city, karat, latest_date)).fetchone()

        # 30-day high/low
        hi_lo = conn.execute("""
            SELECT MAX(buy_price) as hi, MIN(buy_price) as lo FROM (
                SELECT buy_price FROM prices WHERE city = ? AND karat = ?
                GROUP BY date HAVING scraped_at = MAX(scraped_at)
                ORDER BY date DESC LIMIT 30
            )
        """, (city, karat)).fetchone()

        data.setdefault(city, {})[karat] = {
            'buy':      r['buy_price'],
            'sell':     r['sell_price'],
            'prev_buy': prev['buy_price'] if prev else r['buy_price'],
            'hi30':     hi_lo['hi'] or r['buy_price'],
            'lo30':     hi_lo['lo'] or r['buy_price'],
        }

    (OUT_DIR / 'prices.json').write_text(json.dumps({
        'ok': True,
        'data': data,
        'updated_at': datetime.now().isoformat(),
    }))
    print(f'Wrote prices.json ({len(today_rows)} rows for {today})')
    conn.close()


if __name__ == '__main__':
    export()
