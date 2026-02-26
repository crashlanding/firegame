import os
import threading
import logging

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, flash
)
from werkzeug.security import check_password_hash
from dotenv import load_dotenv
from functools import wraps

load_dotenv()

# ── App setup ─────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-me-in-production-use-long-random-string')


# ── Jinja2 template helpers ───────────────────────────────────────────────────

def _fmt_rev(amount):
    """Format a revenue number as a human-readable string."""
    if amount is None:
        return '—'
    abs_v = abs(amount)
    if abs_v >= 1e12:
        return f'${amount / 1e12:.2f}T'
    if abs_v >= 1e9:
        return f'${amount / 1e9:.2f}B'
    if abs_v >= 1e6:
        return f'${amount / 1e6:.2f}M'
    return f'${amount:,.0f}'


def _fmt_yoy(change):
    """Format a YoY percentage change with directional indicator."""
    if change is None:
        return '—'
    sign  = '+' if change >= 0 else ''
    arrow = '▲' if change >= 0 else '▼'
    cls   = 'yoy-up' if change >= 0 else 'yoy-down'
    return f'<span class="{cls}">{arrow} {sign}{change:.1f}%</span>'


app.jinja_env.globals.update(fmt_rev=_fmt_rev, fmt_yoy=_fmt_yoy)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)


# ── Auth helpers ──────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '').strip()

        from database import get_db
        with get_db() as conn:
            user = conn.execute(
                'SELECT * FROM users WHERE username = ?', (username,)
            ).fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session.permanent = False
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['email'] = user['email']
            return redirect(url_for('dashboard'))

        flash('Invalid username or password.', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    from database import get_db
    with get_db() as conn:
        tickers = conn.execute('''
            SELECT  t.id,
                    t.symbol,
                    t.added_at,
                    e.earnings_date,
                    e.is_confirmed,
                    e.company_name,
                    e.last_revenue,
                    e.prev_year_revenue,
                    e.revenue_yoy_change,
                    e.last_scanned
            FROM    tickers t
            LEFT JOIN earnings_data e ON t.id = e.ticker_id
            WHERE   t.user_id = ?
            ORDER BY t.symbol ASC
        ''', (session['user_id'],)).fetchall()

    return render_template(
        'dashboard.html',
        tickers=tickers,
        username=session['username'],
    )


# ── Ticker API ────────────────────────────────────────────────────────────────

@app.route('/api/tickers', methods=['POST'])
@login_required
def add_ticker():
    data = request.get_json(force=True, silent=True) or {}
    symbol = data.get('symbol', '').upper().strip()

    if not symbol:
        return jsonify({'error': 'Symbol is required.'}), 400

    if len(symbol) > 10:
        return jsonify({'error': 'Symbol is too long.'}), 400

    from database import get_db
    with get_db() as conn:
        try:
            conn.execute(
                'INSERT INTO tickers (user_id, symbol) VALUES (?, ?)',
                (session['user_id'], symbol)
            )
            conn.commit()
            ticker_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
        except Exception as exc:
            if 'UNIQUE' in str(exc):
                return jsonify({'error': f'{symbol} is already in your watchlist.'}), 409
            logger.error(f"DB error adding ticker {symbol}: {exc}")
            return jsonify({'error': 'Database error.'}), 500

    # Kick off an immediate background scan for this ticker
    from scheduler_service import scan_single_ticker
    t = threading.Thread(
        target=scan_single_ticker,
        args=(ticker_id, symbol),
        daemon=True
    )
    t.start()

    return jsonify({'success': True, 'symbol': symbol, 'id': ticker_id})


@app.route('/api/tickers/<int:ticker_id>', methods=['DELETE'])
@login_required
def delete_ticker(ticker_id):
    from database import get_db
    with get_db() as conn:
        ticker = conn.execute(
            'SELECT * FROM tickers WHERE id = ? AND user_id = ?',
            (ticker_id, session['user_id'])
        ).fetchone()

        if not ticker:
            return jsonify({'error': 'Ticker not found.'}), 404

        conn.execute('DELETE FROM tickers WHERE id = ?', (ticker_id,))
        conn.commit()

    return jsonify({'success': True})


@app.route('/api/tickers', methods=['GET'])
@login_required
def get_tickers():
    """Return current ticker data as JSON (used to refresh dashboard table)."""
    from database import get_db
    with get_db() as conn:
        rows = conn.execute('''
            SELECT  t.id,
                    t.symbol,
                    e.earnings_date,
                    e.is_confirmed,
                    e.company_name,
                    e.last_revenue,
                    e.prev_year_revenue,
                    e.revenue_yoy_change,
                    e.last_scanned
            FROM    tickers t
            LEFT JOIN earnings_data e ON t.id = e.ticker_id
            WHERE   t.user_id = ?
            ORDER BY t.symbol ASC
        ''', (session['user_id'],)).fetchall()

    result = []
    for r in rows:
        result.append({
            'id': r['id'],
            'symbol': r['symbol'],
            'earnings_date': r['earnings_date'],
            'is_confirmed': bool(r['is_confirmed']),
            'company_name': r['company_name'],
            'last_revenue': r['last_revenue'],
            'prev_year_revenue': r['prev_year_revenue'],
            'revenue_yoy_change': r['revenue_yoy_change'],
            'last_scanned': r['last_scanned'],
        })
    return jsonify(result)


@app.route('/api/scan', methods=['POST'])
@login_required
def trigger_scan():
    """Manually trigger a full earnings scan (runs in background thread)."""
    from scheduler_service import scan_earnings_dates
    t = threading.Thread(target=scan_earnings_dates, daemon=True)
    t.start()
    return jsonify({'success': True, 'message': 'Scan started in background.'})


@app.route('/api/test-email', methods=['POST'])
@login_required
def test_email():
    """Send a test email alert for a given ticker (dev/debug helper)."""
    from database import get_db
    from email_service import send_earnings_alert
    from datetime import date, timedelta

    data = request.get_json(force=True, silent=True) or {}
    ticker_id = data.get('ticker_id')

    if not ticker_id:
        return jsonify({'error': 'ticker_id required'}), 400

    with get_db() as conn:
        row = conn.execute('''
            SELECT t.symbol, e.*
            FROM tickers t
            LEFT JOIN earnings_data e ON t.id = e.ticker_id
            WHERE t.id = ? AND t.user_id = ?
        ''', (ticker_id, session['user_id'])).fetchone()

    if not row:
        return jsonify({'error': 'Ticker not found'}), 404

    earnings_date = date.today() + timedelta(days=5)  # fake date for test
    success = send_earnings_alert(
        symbol=row['symbol'],
        company_name=row['company_name'] or row['symbol'],
        earnings_date=earnings_date,
        days_until=5,
        last_revenue=row['last_revenue'],
        prev_year_revenue=row['prev_year_revenue'],
        revenue_yoy_change=row['revenue_yoy_change'],
    )
    if success:
        return jsonify({'success': True, 'message': 'Test email sent.'})
    return jsonify({'error': 'Email send failed (check SMTP config).'}), 500


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def create_app():
    from database import init_db
    init_db()

    from scheduler_service import start_scheduler
    start_scheduler()

    return app


# Initialise on import (works with gunicorn and `flask run`)
create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
