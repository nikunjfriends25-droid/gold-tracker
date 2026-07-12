"""GitHub Actions: scrape all 8 cities, update docs/data/prices.json and history.json."""
import json
import sys
import time
import random
from pathlib import Path
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup

OUT_DIR = Path(__file__).parent.parent / 'docs' / 'data'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

CITIES = {
    'Chennai': 'chennai', 'Coimbatore': 'coimbatore',
    'Madurai': 'madurai', 'Tirupur': 'tirupur',
    'Kozhikode': 'kozhikode', 'Kochi': 'kochi',
    'Thrissur': 'thrissur', 'Thiruvananthapuram': 'trivandrum',
}


def parse_price(text):
    text = text.split('(')[0]
    digits = ''.join(filter(str.isdigit, text))
    return int(digits) if digits else 0


def scrape_city(city, slug):
    url = f'https://www.goodreturns.in/gold-rates/{slug}.html'
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f'[scraper] Failed {city}: {e}')
        return None
    soup = BeautifulSoup(r.text, 'html.parser')
    try:
        table = soup.find('table', class_='gr-table')
        if not table:
            print(f'[scraper] No gr-table for {city}')
            return None
        for row in table.find_all('tr'):
            cells = row.find_all('td')
            if not cells or cells[0].get_text(strip=True) != '1':
                continue
            if len(cells) < 3:
                continue
            p24 = parse_price(cells[1].get_text())
            p22 = parse_price(cells[2].get_text())
            results = []
            if p22 > 0:
                results.append({'city': city, 'karat': '22K', 'buy': p22, 'sell': int(p22 * 0.985)})
            if p24 > 0:
                results.append({'city': city, 'karat': '24K', 'buy': p24, 'sell': int(p24 * 0.985)})
            return results if results else None
    except Exception as e:
        print(f'[scraper] Parse error {city}: {e}')
    return None


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    # Load existing files
    hist_path = OUT_DIR / 'history.json'
    prices_path = OUT_DIR / 'prices.json'
    history = json.loads(hist_path.read_text()) if hist_path.exists() else {}
    old_prices = json.loads(prices_path.read_text()) if prices_path.exists() else {'data': {}}

    # Scrape
    scraped = {}
    for city, slug in CITIES.items():
        rows = scrape_city(city, slug)
        if rows:
            scraped[city] = {r['karat']: r for r in rows}
            print(f'[scraper] {city}: 22K={scraped[city].get("22K", {}).get("buy")} 24K={scraped[city].get("24K", {}).get("buy")}')
        else:
            print(f'[scraper] {city}: FAILED')
        time.sleep(random.uniform(1.5, 2.5))

    if not scraped:
        print('ERROR: No data scraped. Aborting to avoid overwriting with empty data.')
        sys.exit(1)

    # Update history.json — one entry per city/karat/day
    for city, karats in scraped.items():
        for karat, r in karats.items():
            entries = history.setdefault(city, {}).setdefault(karat, [])
            entries[:] = [e for e in entries if e['date'] != today]
            entries.append({'date': today, 'buy_price': r['buy'], 'sell_price': r['sell']})
            entries.sort(key=lambda x: x['date'])
            if len(entries) > 365:
                entries[:] = entries[-365:]

    hist_path.write_text(json.dumps(history))

    # Build prices.json with 30d stats from history
    def get_30d_range(city, karat):
        entries = history.get(city, {}).get(karat, [])[-30:]
        if not entries:
            return 0, 0
        buys = [e['buy_price'] for e in entries]
        return max(buys), min(buys)

    def get_prev_buy(city, karat):
        entries = [e for e in history.get(city, {}).get(karat, []) if e['date'] < today]
        return entries[-1]['buy_price'] if entries else None

    data = {}
    for city, karats in scraped.items():
        data[city] = {}
        for karat, r in karats.items():
            hi30, lo30 = get_30d_range(city, karat)
            prev = get_prev_buy(city, karat)
            data[city][karat] = {
                'buy':      r['buy'],
                'sell':     r['sell'],
                'prev_buy': prev if prev else r['buy'],
                'hi30':     hi30 or r['buy'],
                'lo30':     lo30 or r['buy'],
            }

    prices_path.write_text(json.dumps({
        'ok': True,
        'data': data,
        'updated_at': datetime.now().isoformat(),
    }))
    print(f'Updated prices.json and history.json for {today} ({len(scraped)} cities)')


if __name__ == '__main__':
    main()
