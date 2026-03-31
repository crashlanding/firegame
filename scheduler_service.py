"""
Background scheduler for stock earnings alerts.

  Job 1 – scan_earnings_dates   : runs every 15 days
           Queries yfinance for each saved ticker and updates earnings_data.

  Job 2 – check_and_send_emails : runs daily at 09:00 UTC
           Sends an email alert (with .ics) 10 days before each upcoming
           earnings date, or immediately if fewer than 10 days remain.
"""

import threading
import logging
from datetime import datetime, date

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler = None
ALERT_WINDOW_DAYS = 10  # Send alert when earnings are ≤ this many days away


# ── Core jobs ─────────────────────────────────────────────────────────────────

def scan_earnings_dates():
    """Refresh earnings date + revenue data for every tracked ticker."""
    import time
    from database import get_db
    from stock_service import get_earnings_info

    logger.info("[scheduler] Starting earnings date scan for all tickers …")

    with get_db() as conn:
        tickers = conn.execute('SELECT id, symbol FROM tickers').fetchall()

    for ticker_row in tickers:
        ticker_id = ticker_row['id']
        symbol = ticker_row['symbol']

        try:
            info = get_earnings_info(symbol)
            if info is None:
                logger.warning(f"[scheduler] No data for {symbol}; skipping.")
                continue

            _upsert_earnings_data(ticker_id, info)
            logger.info(
                f"[scheduler] {symbol}: earnings={info['earnings_date']}, "
                f"confirmed={info['is_confirmed']}, "
                f"revenue={info['last_revenue']}"
            )
        except Exception as exc:
            logger.error(f"[scheduler] Error scanning {symbol}: {exc}")

        time.sleep(1)  # be polite to Yahoo Finance

    logger.info("[scheduler] Earnings scan complete.")


def check_and_send_emails():
    """Send email alerts for earnings occurring within ALERT_WINDOW_DAYS."""
    from database import get_db
    from email_service import send_earnings_alert

    logger.info("[scheduler] Checking for upcoming earnings to alert …")
    today = date.today()

    with get_db() as conn:
        rows = conn.execute('''
            SELECT  t.id   AS ticker_id,
                    t.symbol,
                    e.earnings_date,
                    e.company_name,
                    e.last_revenue,
                    e.prev_year_revenue,
                    e.revenue_yoy_change
            FROM    tickers t
            JOIN    earnings_data e ON t.id = e.ticker_id
            WHERE   e.earnings_date IS NOT NULL
        ''').fetchall()

    for row in rows:
        try:
            earnings_date = date.fromisoformat(row['earnings_date'])
            days_until = (earnings_date - today).days

            # Only alert for future events within the alert window
            if days_until < 0 or days_until > ALERT_WINDOW_DAYS:
                continue

            # Skip if we already sent an alert for this specific earnings date
            with get_db() as conn:
                already = conn.execute(
                    'SELECT id FROM email_log WHERE ticker_id=? AND earnings_date=?',
                    (row['ticker_id'], row['earnings_date'])
                ).fetchone()

            if already:
                continue

            success = send_earnings_alert(
                symbol=row['symbol'],
                company_name=row['company_name'] or row['symbol'],
                earnings_date=earnings_date,
                days_until=days_until,
                last_revenue=row['last_revenue'],
                prev_year_revenue=row['prev_year_revenue'],
                revenue_yoy_change=row['revenue_yoy_change'],
            )

            if success:
                with get_db() as conn:
                    conn.execute(
                        'INSERT INTO email_log (ticker_id, earnings_date) VALUES (?, ?)',
                        (row['ticker_id'], row['earnings_date'])
                    )
                    conn.commit()
                logger.info(
                    f"[scheduler] Alert sent for {row['symbol']} "
                    f"(earnings in {days_until} days)"
                )

        except Exception as exc:
            logger.error(f"[scheduler] Error processing alert for {row['symbol']}: {exc}")

    logger.info("[scheduler] Email check complete.")


# ── Helper ────────────────────────────────────────────────────────────────────

def _upsert_earnings_data(ticker_id, info):
    """Insert or update a row in earnings_data for the given ticker."""
    from database import get_db

    earnings_date_str = str(info['earnings_date']) if info['earnings_date'] else None
    now_iso = datetime.now().isoformat()

    with get_db() as conn:
        existing = conn.execute(
            'SELECT id FROM earnings_data WHERE ticker_id = ?', (ticker_id,)
        ).fetchone()

        if existing:
            conn.execute('''
                UPDATE earnings_data
                SET    earnings_date    = ?,
                       is_confirmed     = ?,
                       company_name     = ?,
                       last_revenue     = ?,
                       prev_year_revenue = ?,
                       revenue_yoy_change = ?,
                       last_scanned     = ?
                WHERE  ticker_id = ?
            ''', (
                earnings_date_str,
                1 if info['is_confirmed'] else 0,
                info['company_name'],
                info['last_revenue'],
                info['prev_year_revenue'],
                info['revenue_yoy_change'],
                now_iso,
                ticker_id,
            ))
        else:
            conn.execute('''
                INSERT INTO earnings_data
                    (ticker_id, earnings_date, is_confirmed, company_name,
                     last_revenue, prev_year_revenue, revenue_yoy_change, last_scanned)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                ticker_id,
                earnings_date_str,
                1 if info['is_confirmed'] else 0,
                info['company_name'],
                info['last_revenue'],
                info['prev_year_revenue'],
                info['revenue_yoy_change'],
                now_iso,
            ))
        conn.commit()


def scan_single_ticker(ticker_id, symbol):
    """
    Immediately fetch and persist earnings data for one newly added ticker.
    Runs in a daemon thread so it doesn't block the HTTP response.
    """
    from stock_service import get_earnings_info

    try:
        info = get_earnings_info(symbol)
        if info:
            _upsert_earnings_data(ticker_id, info)
            logger.info(f"[scheduler] Immediate scan done for {symbol}: {info['earnings_date']}")
    except Exception as exc:
        logger.error(f"[scheduler] Immediate scan failed for {symbol}: {exc}")


# ── Scheduler lifecycle ───────────────────────────────────────────────────────

def start_scheduler():
    """
    Initialise APScheduler with two recurring jobs and start it.
    Safe to call multiple times (no-op after first call).
    """
    global _scheduler

    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler(timezone='UTC')

    # Job 1: scan every 15 days
    _scheduler.add_job(
        func=scan_earnings_dates,
        trigger=IntervalTrigger(days=15),
        id='scan_earnings',
        name='Scan Earnings Dates',
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # Job 2: send email alerts daily at 09:00 UTC
    _scheduler.add_job(
        func=check_and_send_emails,
        trigger=CronTrigger(hour=9, minute=0, timezone='UTC'),
        id='send_email_alerts',
        name='Send Email Alerts',
        replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.start()
    logger.info(
        "[scheduler] Started: earnings scan every 15 days; "
        "email check daily at 09:00 UTC"
    )

    # Run an initial full scan in a background thread so existing tickers
    # get data on first deploy without blocking app startup.
    t = threading.Thread(target=scan_earnings_dates, name='initial-scan', daemon=True)
    t.start()


def get_scheduler():
    return _scheduler
