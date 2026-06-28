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
