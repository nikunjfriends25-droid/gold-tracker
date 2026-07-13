"""One-time: backfill Dubai history in docs/data/history.json.

Same pattern as the other cities' backfill: derived from the goldapi XAU/INR
spot curve. Chennai's series IS that curve (spot x 1.176 TN premium), and
Dubai-in-INR is spot x a constant (AED is USD-pegged, converted at live rate),
so Dubai history = Chennai history scaled by today's real Dubai/Chennai ratio.
Real scraped Dubai entries are kept; only missing dates are filled.
"""
import json
from pathlib import Path

HIST = Path(__file__).parent.parent / 'docs' / 'data' / 'history.json'


def main():
    history = json.loads(HIST.read_text())
    chennai = history['Chennai']
    dubai = history.setdefault('Dubai', {})

    added = 0
    for karat in ('22K', '24K'):
        entries = dubai.setdefault(karat, [])
        if not entries:
            print(f'No real Dubai {karat} entry to anchor ratio — skipping')
            continue
        anchor = entries[-1]
        ch_by_date = {e['date']: e for e in chennai[karat]}
        ch_anchor = ch_by_date.get(anchor['date'])
        if not ch_anchor:
            print(f'No Chennai {karat} entry on {anchor["date"]} — skipping')
            continue
        ratio = anchor['buy_price'] / ch_anchor['buy_price']
        print(f'{karat}: ratio {ratio:.4f} (Dubai {anchor["buy_price"]} / Chennai {ch_anchor["buy_price"]} on {anchor["date"]})')

        have = {e['date'] for e in entries}
        for e in chennai[karat]:
            if e['date'] in have:
                continue
            buy = int(round(e['buy_price'] * ratio))
            entries.append({'date': e['date'], 'buy_price': buy, 'sell_price': int(buy * 0.985)})
            added += 1
        entries.sort(key=lambda x: x['date'])

    HIST.write_text(json.dumps(history))
    print(f'Added {added} Dubai entries. Series lengths: 22K={len(dubai.get("22K", []))}, 24K={len(dubai.get("24K", []))}')

    # sanity: series must be same length as Chennai and monotonic dates
    for karat in ('22K', '24K'):
        assert len(dubai[karat]) == len(chennai[karat]), karat
        dates = [e['date'] for e in dubai[karat]]
        assert dates == sorted(dates)
    print('Sanity checks passed')


if __name__ == '__main__':
    main()
