import requests
from bs4 import BeautifulSoup
from datetime import datetime
import time
import random

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def _parse_price(text: str) -> int:
    digits = ''.join(filter(str.isdigit, text))
    return int(digits) if digits else 0


def scrape_city(city: str, slug: str) -> list | None:
    """
    Scrapes GoodReturns for 22K and 24K buy prices for one city.
    Sell price is approximated as buy * 0.985 (GoodReturns shows buy only).
    Table structure (verified 2026-06-28):
      class='gr-table', header row: Gram | 24K | 22K | 18K
      1g data row: 1 | <24K price> | <22K price> | <18K price>
    Returns list of {city, karat, buy, sell} or None on failure.
    """
    url = f'https://www.goodreturns.in/gold-rates/{slug}.html'
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f'[scraper] Failed {city}: {e}')
        return None

    soup = BeautifulSoup(r.text, 'html.parser')
    results = []
    try:
        # First gr-table is today's price table; second is historical
        table = soup.find('table', class_='gr-table')
        if not table:
            print(f'[scraper] No gr-table found for {city}')
            return None

        rows = table.find_all('tr')
        # Find the 1-gram row (cells[0] == '1')
        for row in rows:
            cells = row.find_all('td')
            if not cells:
                continue
            gram_text = cells[0].get_text(strip=True)
            if gram_text != '1':
                continue
            # Header is: Gram | 24K | 22K | 18K
            # Data row:  1    | p24  | p22  | p18
            if len(cells) < 3:
                continue
            price_24k = _parse_price(cells[1].get_text())
            price_22k = _parse_price(cells[2].get_text())
            if price_22k > 0:
                sell_22k = int(price_22k * 0.985)
                results.append({'city': city, 'karat': '22K', 'buy': price_22k, 'sell': sell_22k})
            if price_24k > 0:
                sell_24k = int(price_24k * 0.985)
                results.append({'city': city, 'karat': '24K', 'buy': price_24k, 'sell': sell_24k})
            break
    except Exception as e:
        print(f'[scraper] Parse error {city}: {e}')
        return None

    return results or None


def scrape_all() -> list[dict]:
    """Scrapes all 8 cities. Skips failures silently."""
    from config import GOODRETURNS_SLUGS
    all_results = []
    for city, slug in GOODRETURNS_SLUGS.items():
        rows = scrape_city(city, slug)
        if rows:
            all_results.extend(rows)
            print(f'[scraper] {city}: OK ({len(rows)} rows)')
        else:
            print(f'[scraper] {city}: FAILED')
        time.sleep(random.uniform(1.5, 2.5))
    return all_results


def scrape_ibja() -> dict | None:
    """
    Fetches 22K and 24K rates from IBJA (India Bullion and Jewellers Association).
    Returns {22K: price, 24K: price} or None on failure.
    IBJA shows official buy/sell rates set by the association.
    """
    from config import IBJA_URL
    try:
        r = requests.get(IBJA_URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        rates = {}
        # IBJA page structure varies — try common patterns
        # Pattern 1: table with Fine/Standard headers
        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                cells = row.find_all(['td', 'th'])
                if len(cells) < 2:
                    continue
                label = cells[0].get_text(strip=True).lower()
                # 999 = 24K, 916 = 22K
                if '999' in label or '24' in label:
                    price = _parse_price(cells[1].get_text())
                    if price > 5000:
                        rates['24K'] = price
                elif '916' in label or '22' in label:
                    price = _parse_price(cells[1].get_text())
                    if price > 5000:
                        rates['22K'] = price

        return rates if rates else None
    except Exception as e:
        print(f'[scraper] IBJA failed: {e}')
        return None


def get_xau_usd() -> float | None:
    """Fetches XAU/USD spot from goldapi.io."""
    from db import get_config
    key = get_config('goldapi_key')
    try:
        r = requests.get(
            'https://www.goldapi.io/api/XAU/USD',
            headers={**HEADERS, 'x-access-token': key},
            timeout=8
        )
        return r.json().get('price')
    except Exception:
        return None


def get_usd_inr() -> float | None:
    """Fetches live USD/INR rate."""
    try:
        r = requests.get('https://api.exchangerate-api.com/v4/latest/USD', timeout=8)
        return round(r.json()['rates']['INR'], 2)
    except Exception:
        return None
