"""
Inserts 90 days of synthetic price history so the chart works immediately.
Run once: python seed_test_data.py
"""
from db import init_db, get_conn
from config import ALL_CITIES, KARATS
from datetime import datetime, date, timedelta
import random

# Approximate base prices (per gram) as of late June 2026
BASE_PRICES = {
    'Chennai':            {'22K': 13370, '24K': 14586},
    'Coimbatore':         {'22K': 13370, '24K': 14586},
    'Madurai':            {'22K': 13370, '24K': 14586},
    'Tirupur':            {'22K': 13370, '24K': 14586},
    'Kozhikode':          {'22K': 13195, '24K': 14395},
    'Kochi':              {'22K': 13195, '24K': 14395},
    'Thrissur':           {'22K': 13195, '24K': 14395},
    'Thiruvananthapuram': {'22K': 13195, '24K': 14395},
}

def generate_price_series(base: int, days: int) -> list[int]:
    """Walk backward from today, generating daily prices with realistic drift."""
    prices = [base]
    for _ in range(days - 1):
        change = random.gauss(0, base * 0.004)  # ~0.4% daily vol
        trend = random.uniform(-0.2, 0.3)       # slight upward bias
        prev = prices[-1]
        new_price = int(prev + change + trend * prev * 0.001)
        new_price = max(int(base * 0.85), min(int(base * 1.15), new_price))
        prices.append(new_price)
    return list(reversed(prices))  # oldest first


def seed():
    init_db()
    today = date.today()
    DAYS = 90

    rows_to_insert = []
    for city in ALL_CITIES:
        for karat in KARATS:
            base = BASE_PRICES[city][karat]
            prices = generate_price_series(base, DAYS)
            for i, price in enumerate(prices):
                day = today - timedelta(days=DAYS - 1 - i)
                if day == today:
                    continue  # skip today — real scrape will fill this
                sell = int(price * 0.985)
                scraped_at = datetime.combine(day, datetime.min.time().replace(hour=9)).isoformat()
                rows_to_insert.append((
                    scraped_at,
                    day.isoformat(),
                    city,
                    karat,
                    price,
                    sell,
                    'seed'
                ))

    with get_conn() as conn:
        # Only insert if no seed data already exists for these dates
        existing = conn.execute(
            "SELECT COUNT(*) FROM prices WHERE source='seed'"
        ).fetchone()[0]
        if existing > 0:
            print(f'Seed data already present ({existing} rows). Skipping.')
            return

        conn.executemany(
            'INSERT INTO prices (scraped_at, date, city, karat, buy_price, sell_price, source) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            rows_to_insert
        )

    print(f'Seeded {len(rows_to_insert)} rows of 90-day history.')


if __name__ == '__main__':
    seed()
