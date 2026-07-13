"""
Replaces goldapi_backfill data with accurate daily prices for Jan 15 – Mar 31 2026.
Data was already fetched from goldapi.io (no additional API calls needed here).
The chart will now correctly show the Jan 29 peak (~₹17,500 for 22K).
"""
from db import init_db, get_conn
from config import ALL_CITIES, CITIES_TN, CITIES_KL

# Spot prices (INR/gram) from goldapi XAU/INR historical API
# (22K spot, 24K spot) per day — fetched 2026-06-28
DAILY_SPOTS = {
    '2026-01-15': (12272, 13387),
    '2026-01-16': (12339, 13461),
    '2026-01-17': (12339, 13461),
    '2026-01-18': (12339, 13461),
    '2026-01-19': (12499, 13635),
    '2026-01-20': (12665, 13817),
    '2026-01-21': (13137, 14331),
    '2026-01-22': (13030, 14214),
    '2026-01-23': (13350, 14563),
    '2026-01-24': (13350, 14563),
    '2026-01-25': (13350, 14563),
    '2026-01-26': (13755, 15005),
    '2026-01-27': (13755, 15005),
    '2026-01-28': (14278, 15576),
    '2026-01-29': (14910, 16265),   # 22K PEAK ~₹17,533 retail
    '2026-01-30': (13727, 14975),
    '2026-01-31': (13727, 14975),
    '2026-02-01': (13727, 14975),
    '2026-02-02': (12636, 13785),
    '2026-02-03': (13099, 14290),
    '2026-02-04': (13464, 14688),
    '2026-02-05': (12939, 14116),
    '2026-02-06': (13013, 14196),
    '2026-02-07': (13013, 14196),
    '2026-02-08': (13013, 14196),
    '2026-02-09': (13357, 14572),
    '2026-02-10': (13475, 14700),
    '2026-02-11': (13553, 14786),
    '2026-02-12': (13523, 14752),
    '2026-02-13': (13276, 14483),
    '2026-02-14': (13276, 14483),
    '2026-02-15': (13276, 14483),
    '2026-02-16': (13372, 14588),
    '2026-02-17': (13153, 14349),
    '2026-02-18': (13141, 14336),
    '2026-02-19': (13412, 14631),
    '2026-02-20': (13495, 14722),
    '2026-02-21': (13495, 14722),
    '2026-02-22': (13495, 14722),
    '2026-02-23': (13495, 14722),
    '2026-02-24': (13495, 14722),
    '2026-02-25': (13495, 14722),
    '2026-02-26': (13495, 14722),
    '2026-02-27': (13495, 14722),
    '2026-02-28': (13495, 14722),
    '2026-03-01': (13873, 15135),
    '2026-03-02': (14533, 15854),   # March peak ~₹17,090 for 22K
    '2026-03-03': (14298, 15598),
    '2026-03-04': (14071, 15350),
    '2026-03-05': (13912, 15177),
    '2026-03-06': (13759, 15010),
    '2026-03-07': (13759, 15010),
    '2026-03-08': (13759, 15010),
    '2026-03-09': (13862, 15123),
    '2026-03-10': (13997, 15270),
    '2026-03-11': (14061, 15339),
    '2026-03-12': (14078, 15358),
    '2026-03-13': (13849, 15108),
    '2026-03-14': (13849, 15108),
    '2026-03-15': (13849, 15108),
    '2026-03-16': (13582, 14817),
    '2026-03-17': (13627, 14866),
    '2026-03-18': (13605, 14842),
    '2026-03-19': (12866, 14036),
    '2026-03-20': (12848, 14016),
    '2026-03-21': (12848, 14016),
    '2026-03-22': (12848, 14016),
    '2026-03-23': (11807, 12881),
    '2026-03-24': (12227, 13338),
    '2026-03-25': (12625, 13773),
    '2026-03-26': (12320, 13440),
    '2026-03-27': (12371, 13496),
    '2026-03-28': (12371, 13496),
    '2026-03-29': (12371, 13496),
    '2026-03-30': (12643, 13793),
    '2026-03-31': (12614, 13761),
}

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


def run():
    init_db()

    # Delete the interpolated goldapi_backfill rows for this date range only
    dates = list(DAILY_SPOTS.keys())
    placeholders = ','.join('?' * len(dates))
    with get_conn() as conn:
        deleted = conn.execute(
            f"DELETE FROM prices WHERE source='goldapi_backfill' AND date IN ({placeholders})",
            dates
        ).rowcount
        print(f'Removed {deleted} interpolated rows for Jan 15 – Mar 31.')

    # Build accurate daily rows
    rows = []
    for d_str, (spot22, spot24) in DAILY_SPOTS.items():
        scraped_at = f'{d_str}T09:00:00'
        for city in ALL_CITIES:
            p22 = CITY_PREMIUM[city]['22K']
            p24 = CITY_PREMIUM[city]['24K']
            buy22  = int(spot22 * p22)
            sell22 = int(buy22  * 0.985)
            buy24  = int(spot24 * p24)
            sell24 = int(buy24  * 0.985)
            rows.append((scraped_at, d_str, city, '22K', buy22, sell22, 'goldapi_daily'))
            rows.append((scraped_at, d_str, city, '24K', buy24, sell24, 'goldapi_daily'))

    with get_conn() as conn:
        conn.executemany(
            'INSERT OR IGNORE INTO prices (scraped_at, date, city, karat, buy_price, sell_price, source) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            rows
        )

    print(f'Inserted {len(rows)} accurate daily rows (Jan 15 – Mar 31 2026).')

    # Verify the peak is now visible
    with get_conn() as conn:
        peak = conn.execute(
            "SELECT date, buy_price FROM prices WHERE city='Chennai' AND karat='22K' "
            "AND date BETWEEN '2026-01-01' AND '2026-03-31' ORDER BY buy_price DESC LIMIT 1"
        ).fetchone()
        if peak:
            print(f'\nChennai 22K peak: Rs{peak[1]:,} on {peak[0]}')


if __name__ == '__main__':
    run()
