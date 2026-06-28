# Gold Price Tracker — Claude Code Build Spec

## What this is
A local Python web app that scrapes gold buy/sell prices for 8 cities across
Tamil Nadu and Kerala, stores history in SQLite, and serves a dashboard on
localhost. Alerts are dashboard-only — a banner, browser tab title change,
and browser notification fire when the user opens the dashboard and prices
have crossed their saved thresholds. No WhatsApp. No external messaging.

Runs entirely on one machine. No cloud. No auth. No external hosting.

---

## Tech stack

| Layer | Choice | Reason |
|---|---|---|
| Language | Python 3.11+ | |
| Web server | Flask | Lightweight, no overhead |
| Scheduler | APScheduler | In-process, no cron setup |
| Database | SQLite (via sqlite3) | Zero config, local only |
| Scraping | requests + BeautifulSoup4 | GoodReturns HTML parsing |
| Frontend | Single HTML file served by Flask | No build step, matches approved layout |

---

## Project structure

```
gold-tracker/
├── CLAUDE.md               ← this file
├── app.py                  ← Flask app + routes
├── scraper.py              ← GoodReturns + IBJA scrapers
├── scheduler.py            ← APScheduler setup
├── db.py                   ← SQLite init + all queries
├── config.py               ← constants (cities, URLs, defaults)
├── templates/
│   └── dashboard.html      ← single-file dashboard (HTML + CSS + JS)
├── data/
│   └── gold.db             ← SQLite database (auto-created)
└── requirements.txt
```

---

## Database schema — `data/gold.db`

### Table: `prices`

```sql
CREATE TABLE IF NOT EXISTS prices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scraped_at  TEXT NOT NULL,
    date        TEXT NOT NULL,
    city        TEXT NOT NULL,
    karat       TEXT NOT NULL,
    buy_price   INTEGER NOT NULL,
    sell_price  INTEGER NOT NULL,
    source      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prices_date_city ON prices(date, city, karat);
```

### Table: `config`
**Never truncate or recreate this table on startup — only INSERT OR IGNORE.**

```sql
CREATE TABLE IF NOT EXISTS config (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT OR IGNORE INTO config VALUES ('alert_22k', '16000', datetime('now'));
INSERT OR IGNORE INTO config VALUES ('alert_24k', '16000', datetime('now'));
INSERT OR IGNORE INTO config VALUES ('goldapi_key', 'goldapi-6e4d33a0c3941ba5a847837604201868-io', datetime('now'));
INSERT OR IGNORE INTO config VALUES ('setup_complete', '', datetime('now'));
```

---

## City list — `config.py`

```python
CITIES_TN = ['Chennai', 'Coimbatore', 'Madurai', 'Tirupur']
CITIES_KL = ['Kozhikode', 'Kochi', 'Thrissur', 'Thiruvananthapuram']
ALL_CITIES = CITIES_TN + CITIES_KL
KARATS = ['22K', '24K']

GOODRETURNS_SLUGS = {
    'Chennai':            'chennai',
    'Coimbatore':         'coimbatore',
    'Madurai':            'madurai',
    'Tirupur':            'tirupur',
    'Kozhikode':          'calicut',   # site uses "calicut" not "kozhikode"
    'Kochi':              'kochi',
    'Thrissur':           'thrissur',
    'Thiruvananthapuram': 'trivandrum',
}

GOODRETURNS_BASE = 'https://www.goodreturns.in/gold-rates/'
IBJA_URL         = 'https://ibja.co/'
GOLDAPI_URL      = 'https://www.goldapi.io/api/XAU/USD'
```

---

## Scraper — `scraper.py`

```python
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import time

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

def scrape_city(city: str, slug: str) -> list | None:
    """
    Returns list of {city, karat, buy, sell} for 22K and 24K.
    Returns None on failure — caller logs and continues.
    IMPORTANT: inspect goodreturns.in/gold-rates/chennai.html live before
    hardcoding selectors. The table structure changes periodically.
    """
    url = f'https://www.goodreturns.in/gold-rates/{slug}.html'
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f'[scraper] Failed {city}: {e}')
        return None

    soup = BeautifulSoup(r.text, 'html.parser')
    results = []
    try:
        rows = soup.select('table.gold-rate-table tr')  # verify selector live
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 3:
                continue
            label = cells[0].get_text(strip=True)
            if '22' in label:
                karat = '22K'
            elif '24' in label:
                karat = '24K'
            else:
                continue
            buy  = int(''.join(filter(str.isdigit, cells[1].get_text())))
            sell = int(''.join(filter(str.isdigit, cells[2].get_text())))
            results.append({'city': city, 'karat': karat, 'buy': buy, 'sell': sell})
    except Exception as e:
        print(f'[scraper] Parse error {city}: {e}')
        return None

    return results or None


def scrape_all() -> list[dict]:
    """Scrapes all cities. Skips failures silently."""
    from config import GOODRETURNS_SLUGS
    all_results = []
    for city, slug in GOODRETURNS_SLUGS.items():
        rows = scrape_city(city, slug)
        if rows:
            all_results.extend(rows)
        time.sleep(1.5)
    return all_results


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
    except:
        return None


def get_usd_inr() -> float | None:
    """Fetches live USD/INR rate."""
    try:
        r = requests.get('https://api.exchangerate-api.com/v4/latest/USD', timeout=8)
        return round(r.json()['rates']['INR'], 2)
    except:
        return None
```

---

## Database layer — `db.py`

```python
import sqlite3
from datetime import datetime, date
from pathlib import Path

DB_PATH = Path(__file__).parent / 'data' / 'gold.db'

def get_conn():
    Path(DB_PATH).parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scraped_at TEXT NOT NULL,
                date TEXT NOT NULL,
                city TEXT NOT NULL,
                karat TEXT NOT NULL,
                buy_price INTEGER NOT NULL,
                sell_price INTEGER NOT NULL,
                source TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_prices_date_city ON prices(date, city, karat);
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        seeds = [
            ('alert_22k', '16000'),
            ('alert_24k', '16000'),
            ('goldapi_key', 'goldapi-6e4d33a0c3941ba5a847837604201868-io'),
            ('setup_complete', ''),
        ]
        for key, val in seeds:
            conn.execute(
                'INSERT OR IGNORE INTO config VALUES (?, ?, ?)',
                (key, val, datetime.now().isoformat())
            )

def insert_prices(rows: list[dict]):
    now = datetime.now().isoformat()
    today = date.today().isoformat()
    with get_conn() as conn:
        conn.executemany(
            'INSERT INTO prices (scraped_at, date, city, karat, buy_price, sell_price, source) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            [(now, today, r['city'], r['karat'], r['buy'], r['sell'], r.get('source', 'goodreturns'))
             for r in rows]
        )

def get_today_prices() -> list[dict]:
    today = date.today().isoformat()
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT city, karat, buy_price, sell_price, scraped_at
            FROM prices WHERE date = ?
            GROUP BY city, karat HAVING scraped_at = MAX(scraped_at)
        """, (today,)).fetchall()
    return [dict(r) for r in rows]

def get_price_history(city: str, karat: str, days: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT date, buy_price, sell_price FROM prices
            WHERE city = ? AND karat = ?
            GROUP BY date HAVING scraped_at = MAX(scraped_at)
            ORDER BY date DESC LIMIT ?
        """, (city, karat, days)).fetchall()
    return [dict(r) for r in reversed(rows)]

def get_30d_range(city: str, karat: str) -> dict:
    with get_conn() as conn:
        row = conn.execute("""
            SELECT MAX(buy_price) as hi, MIN(buy_price) as lo FROM (
                SELECT buy_price FROM prices WHERE city = ? AND karat = ?
                GROUP BY date HAVING scraped_at = MAX(scraped_at)
                ORDER BY date DESC LIMIT 30
            )
        """, (city, karat)).fetchone()
    return {'hi': row['hi'] or 0, 'lo': row['lo'] or 0}

def get_yesterday_prices(city: str, karat: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("""
            SELECT buy_price, sell_price FROM prices
            WHERE city = ? AND karat = ? AND date < date('now')
            GROUP BY date HAVING scraped_at = MAX(scraped_at)
            ORDER BY date DESC LIMIT 1
        """, (city, karat)).fetchone()
    return dict(row) if row else None

def get_config(key: str) -> str:
    with get_conn() as conn:
        row = conn.execute('SELECT value FROM config WHERE key = ?', (key,)).fetchone()
    return row['value'] if row else ''

def set_config(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO config VALUES (?, ?, ?)',
            (key, str(value), datetime.now().isoformat())
        )
```

---

## Flask app — `app.py`

```python
from flask import Flask, jsonify, render_template, request
from db import init_db, get_today_prices, get_price_history, get_30d_range
from db import get_config, set_config, get_yesterday_prices

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/api/prices/today')
def api_today():
    rows = get_today_prices()
    data = {}
    for r in rows:
        city, karat = r['city'], r['karat']
        if city not in data:
            data[city] = {}
        prev = get_yesterday_prices(city, karat)
        rng  = get_30d_range(city, karat)
        data[city][karat] = {
            'buy':      r['buy_price'],
            'sell':     r['sell_price'],
            'prev_buy': prev['buy_price'] if prev else r['buy_price'],
            'hi30':     rng['hi'],
            'lo30':     rng['lo'],
        }
    return jsonify({
        'ok': True,
        'data': data,
        'alerts': {
            'alert_22k': int(get_config('alert_22k') or 16000),
            'alert_24k': int(get_config('alert_24k') or 16000),
        }
    })

@app.route('/api/prices/history')
def api_history():
    city  = request.args.get('city', 'Chennai')
    karat = request.args.get('karat', '22K')
    days  = min(int(request.args.get('days', 30)), 180)
    rows  = get_price_history(city, karat, days)
    return jsonify({'ok': True, 'city': city, 'karat': karat, 'history': rows})

@app.route('/api/alerts', methods=['GET'])
def api_get_alerts():
    return jsonify({
        'alert_22k': int(get_config('alert_22k') or 16000),
        'alert_24k': int(get_config('alert_24k') or 16000),
    })

@app.route('/api/alerts', methods=['POST'])
def api_set_alerts():
    body = request.get_json()
    a22 = int(body.get('alert_22k', 0))
    a24 = int(body.get('alert_24k', 0))
    if a22 < 1000 or a24 < 1000:
        return jsonify({'ok': False, 'error': 'Invalid threshold'}), 400
    set_config('alert_22k', a22)
    set_config('alert_24k', a24)
    return jsonify({'ok': True, 'alert_22k': a22, 'alert_24k': a24})

@app.route('/api/scrape', methods=['POST'])
def api_scrape():
    from scraper import scrape_all
    rows = scrape_all()
    if rows:
        from db import insert_prices
        insert_prices(rows)
        return jsonify({'ok': True, 'scraped': len(rows)})
    return jsonify({'ok': False, 'error': 'Scrape returned no data'}), 500

if __name__ == '__main__':
    init_db()
    if not get_config('setup_complete'):
        print("First run detected. Please run: python setup.py")
        exit(1)
    from scheduler import start_scheduler
    start_scheduler()
    app.run(host='127.0.0.1', port=5050, debug=False)
```

---

## Scheduler — `scheduler.py`

Scheduler runs the daily scrape only. No alerting logic here —
alerts are evaluated entirely in the browser when the dashboard loads.

```python
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
```

---

## Dashboard alert behaviour — `templates/dashboard.html`

Alerts are dashboard-only. When the user opens the dashboard, the JS
evaluates prices against thresholds on every page load and on every
Refresh. Three things happen simultaneously if a threshold is crossed:

### 1. Alert banner
A full-width red banner appears at the top of the page (already in the
approved layout). It shows which city/karat crossed the threshold, the
current price, and the threshold value.

### 2. Browser tab title
Change `document.title` dynamically:
```javascript
// If alert triggered:
document.title = '⚠️ SELL ALERT — Gold Tracker';
// Normal state:
document.title = 'Gold Tracker';
```
This means even if the tab is open in the background, the title in the
tab bar shows the alert. The user sees it the moment they look at the browser.

### 3. Browser Notification API
Request permission once on first load. Fire a notification if alert triggered:
```javascript
function requestNotificationPermission() {
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }
}

function fireAlertNotification(message) {
    if ('Notification' in window && Notification.permission === 'granted') {
        new Notification('Gold Price Alert', {
            body: message,
            icon: '/static/gold-icon.png'  // optional, can omit
        });
    }
}

// Call after prices load, if threshold crossed:
fireAlertNotification('Kozhikode 22K buy ₹16,200 has crossed your ₹16,000 alert');
```
The browser will show a desktop notification popup even if the tab is
in the background — it appears in the OS notification area (works on
Windows, Mac, Linux).

### All three together in the price-load callback:
```javascript
async function loadPrices() {
    const res = await fetch('/api/prices/today');
    const json = await res.json();
    // ... render cards, chart, signal meter ...

    // Alert evaluation
    const alerts = json.alerts;
    let alertMessages = [];
    for (const [city, karats] of Object.entries(json.data)) {
        for (const [karat, prices] of Object.entries(karats)) {
            const thresh = karat === '22K' ? alerts.alert_22k : alerts.alert_24k;
            if (prices.buy >= thresh) {
                alertMessages.push(
                    `${city} ${karat} buy ₹${prices.buy.toLocaleString('en-IN')} crossed ₹${thresh.toLocaleString('en-IN')}`
                );
            }
        }
    }

    if (alertMessages.length > 0) {
        document.title = '⚠️ SELL ALERT — Gold Tracker';
        showAlertBanner(alertMessages);
        fireAlertNotification(alertMessages[0]);
    } else {
        document.title = 'Gold Tracker';
        hideAlertBanner();
    }
}
```

### Other dashboard JS behaviour (from approved layout):
- On page load: fetch `/api/prices/today` → populate city cards, signal
  meter, thresholds, run alert evaluation
- Karat toggle (22K/24K): re-renders using cached data, re-runs alert evaluation
- Signal meter: 30D range bar, current price marker, threshold line marker
- "Set alert" panel: inline toggle, live hints showing distance from current
  price, POSTs to `/api/alerts` on save, re-runs alert evaluation immediately
- Chart: fetches `/api/prices/history?city=X&karat=Y&days=N` on change
- Two city selectors on chart: separate fetches, two lines plotted
- Refresh button: POSTs to `/api/scrape`, shows spinner, refreshes on success
- All prices as integers: ₹14,760 not ₹14,760.00

---

## requirements.txt

```
flask>=3.0
requests>=2.31
beautifulsoup4>=4.12
apscheduler>=3.10
```

---

## First-run setup — `setup.py`

Claude Code creates this script. User runs it once.

```python
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
            print(f'  ✓ goldapi.io working. XAU/USD: ${price:,.2f}\n')
        else:
            print(f'  ✗ Unexpected response: {r.json()}\n')
    except Exception as e:
        print(f'  ✗ goldapi.io failed: {e}\n')

    # Step 2: Alert thresholds
    print('Step 2 of 2: Sell alert thresholds')
    t22 = input('  22K alert price in ₹/gram (press Enter for 16000): ').strip()
    t24 = input('  24K alert price in ₹/gram (press Enter for 16000): ').strip()
    set_config('alert_22k', t22 if t22.isdigit() else '16000')
    set_config('alert_24k', t24 if t24.isdigit() else '16000')
    print(f'  Saved: 22K ₹{get_config("alert_22k")}  24K ₹{get_config("alert_24k")}\n')

    # Step 3: First scrape
    print('Running first scrape of all 8 cities...')
    from scraper import scrape_all
    from db import insert_prices
    rows = scrape_all()
    if rows:
        insert_prices(rows)
        print(f'  ✓ Scraped {len(rows)} rows:')
        for r in rows:
            print(f'    {r["city"]:22s} {r["karat"]}  Buy ₹{r["buy"]:,}  Sell ₹{r["sell"]:,}')
    else:
        print('  ✗ Scrape failed — check selectors in scraper.py')

    set_config('setup_complete', '1')
    print('\n=== Done. Run: python app.py ===\n')
    print('Dashboard: http://127.0.0.1:5050')
    print('Alerts are shown in the dashboard when you open it.')
    print('Thresholds can be changed anytime from the dashboard.\n')

if __name__ == '__main__':
    run_setup()
```

---

## Startup sequence

```bash
cd gold-tracker
pip install -r requirements.txt
python setup.py        # once only
python app.py          # every time after that
# open http://127.0.0.1:5050
```

---

## What Claude Code must do before first scrape

1. Fetch `https://www.goodreturns.in/gold-rates/chennai.html`, print the
   HTML, identify the correct price table selector, update `scraper.py`.

2. Fetch `https://ibja.co/`, identify the 24K rate element, implement
   `scrape_ibja()` in `scraper.py`.

3. Run `scrape_all()` standalone and print results — verify all 8 cities
   return sensible prices before wiring into Flask.

4. Create `seed_test_data.py` that inserts 90 days of synthetic price history
   so the chart works immediately without waiting for real data to accumulate.

5. Verify alert persistence: set thresholds via the API, restart app,
   confirm thresholds are unchanged.

---

## Known constraints

- GoodReturns has no public API — scraping only. If blocked, increase delay
  between requests (2–5s random) or rotate User-Agent strings.
- goldapi.io free tier: 100 calls/month. Fetch XAU/USD once per day in the
  scheduler, cache the result in the config table as `xau_usd_today`.
  Dashboard reads from the cache, not live.
- SQLite is sufficient. Do not migrate to PostgreSQL.
- No WhatsApp, no external notification services. Dashboard alerts only.
