"""One-time: fill the Jun 29 + Jul 1-11 2026 gap in docs/data/history.json.

Same pattern as earlier backfills: real daily XAU/INR spot from goldapi,
converted to city retail via each city's premium, linearly interpolated
between the real scraped anchor days (Jun 30 and Jul 12).
Uses ~14 goldapi calls (July quota is fresh).
"""
import json
import urllib.request
from pathlib import Path

HIST = Path(__file__).parent.parent / 'docs' / 'data' / 'history.json'
KEY = 'goldapi-6e4d33a0c3941ba5a847837604201868-io'
OZ = 31.1035

GAP_DATES = ['2026-06-29'] + [f'2026-07-{d:02d}' for d in range(1, 13)]
ANCHOR_A, ANCHOR_B = '2026-06-30', '2026-07-13'


def spot_grams(date_iso):
    """Returns (spot_24k_per_gram, spot_22k_per_gram) INR, or None if no data (weekend)."""
    ymd = date_iso.replace('-', '')
    req = urllib.request.Request(
        f'https://www.goldapi.io/api/XAU/INR/{ymd}',
        headers={'x-access-token': KEY})
    d = json.loads(urllib.request.urlopen(req, timeout=15).read())
    oz_price = d.get('price')
    if not oz_price:
        return None
    g24 = oz_price / OZ
    return g24, g24 * 0.916


def main():
    history = json.loads(HIST.read_text())

    spots = {}
    prev = None
    for dt in [ANCHOR_A] + GAP_DATES + [ANCHOR_B]:
        s = spot_grams(dt)
        if s is None:
            s = prev  # weekend/holiday: carry forward last trading day
            print(f'spot {dt}: no data, carried forward')
        else:
            print(f'spot {dt}: 24K/g = {s[0]:,.0f}')
        spots[dt] = s
        prev = s

    added = 0
    for city, karats in history.items():
        for karat, entries in karats.items():
            by_date = {e['date']: e for e in entries}
            a, b = by_date.get(ANCHOR_A), by_date.get(ANCHOR_B)
            if not a or not b:
                print(f'{city} {karat}: missing anchor, skipped')
                continue
            ki = 0 if karat == '24K' else 1
            prem_a = a['buy_price'] / spots[ANCHOR_A][ki]
            prem_b = b['buy_price'] / spots[ANCHOR_B][ki]
            n = len(GAP_DATES) + 1
            for i, dt in enumerate(GAP_DATES, start=1):
                if dt in by_date:
                    continue
                prem = prem_a + (prem_b - prem_a) * i / n
                buy = int(round(spots[dt][ki] * prem))
                entries.append({'date': dt, 'buy_price': buy, 'sell_price': int(buy * 0.985)})
                added += 1
            entries.sort(key=lambda x: x['date'])

    HIST.write_text(json.dumps(history))
    print(f'Added {added} entries across {len(history)} cities')

    # sanity: no gaps > 1 day remain in Chennai 22K
    from datetime import date
    ds = sorted(date.fromisoformat(e['date']) for e in history['Chennai']['22K'])
    gaps = [(x, y) for x, y in zip(ds, ds[1:]) if (y - x).days > 1]
    assert not gaps, gaps
    print('Sanity check passed: no gaps remain')


if __name__ == '__main__':
    main()
