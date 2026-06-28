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
