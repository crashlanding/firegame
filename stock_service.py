import yfinance as yf
from datetime import datetime, date
import logging
import time

logger = logging.getLogger(__name__)


def get_earnings_info(symbol):
    """
    Fetch upcoming earnings date and quarterly revenue data for a ticker.
    Returns a dict with keys: earnings_date, is_confirmed, company_name,
    last_revenue, prev_year_revenue, revenue_yoy_change.
    Returns None if the ticker is invalid or data cannot be fetched.
    """
    try:
        ticker = yf.Ticker(symbol)

        # ── Company name ──────────────────────────────────────────────────────
        info = {}
        try:
            info = ticker.info or {}
        except Exception:
            pass

        company_name = (
            info.get('longName')
            or info.get('shortName')
            or symbol.upper()
        )

        # ── Earnings date ─────────────────────────────────────────────────────
        earnings_date = None
        is_confirmed = False

        # Method 1: earnings_dates DataFrame (yfinance >= 0.2.x)
        try:
            edf = ticker.earnings_dates
            if edf is not None and not edf.empty:
                # Normalise timezone so we can compare with naive now()
                idx = edf.index
                if hasattr(idx, 'tz') and idx.tz is not None:
                    idx = idx.tz_localize(None)

                now = datetime.now()
                future = edf[idx > now]

                if not future.empty:
                    # earnings_dates is sorted descending; last row = nearest future date
                    raw = future.index[-1]
                    if hasattr(raw, 'tz') and raw.tz is not None:
                        raw = raw.tz_localize(None)
                    earnings_date = raw.date() if hasattr(raw, 'date') else raw
                    is_confirmed = True
        except Exception as e:
            logger.debug(f"earnings_dates failed for {symbol}: {e}")

        # Method 2: calendar dict / DataFrame (fallback)
        if not earnings_date:
            try:
                import pandas as pd
                cal = ticker.calendar
                if cal is not None:
                    if isinstance(cal, dict):
                        ed = cal.get('Earnings Date')
                        if ed is not None:
                            if isinstance(ed, (list, tuple)) and len(ed) > 0:
                                earnings_date = pd.Timestamp(ed[0]).date()
                            elif hasattr(ed, 'date'):
                                earnings_date = ed.date()
                            else:
                                earnings_date = pd.Timestamp(ed).date()
                    elif hasattr(cal, 'columns') and 'Earnings Date' in cal.columns:
                        ed = cal['Earnings Date'].iloc[0]
                        earnings_date = pd.Timestamp(ed).date()
                    elif hasattr(cal, 'loc'):
                        try:
                            ed = cal.loc['Earnings Date'].iloc[0]
                            earnings_date = pd.Timestamp(ed).date()
                        except Exception:
                            pass
                    if earnings_date:
                        is_confirmed = True
            except Exception as e:
                logger.debug(f"calendar failed for {symbol}: {e}")

        # ── Revenue data ──────────────────────────────────────────────────────
        last_revenue = None
        prev_year_revenue = None
        revenue_yoy_change = None

        try:
            qfin = ticker.quarterly_financials
            if qfin is not None and not qfin.empty:
                revenue_row = None
                for key in ('Total Revenue', 'Revenue', 'TotalRevenue'):
                    if key in qfin.index:
                        revenue_row = qfin.loc[key].dropna()
                        break

                if revenue_row is not None and len(revenue_row) >= 1:
                    last_revenue = float(revenue_row.iloc[0])

                    # Compare to the same quarter one year prior (index 4)
                    if len(revenue_row) >= 5:
                        prev_year_revenue = float(revenue_row.iloc[4])
                    elif len(revenue_row) >= 4:
                        prev_year_revenue = float(revenue_row.iloc[-1])

                    if prev_year_revenue and prev_year_revenue != 0 and last_revenue is not None:
                        revenue_yoy_change = (
                            (last_revenue - prev_year_revenue) / abs(prev_year_revenue)
                        ) * 100
        except Exception as e:
            logger.debug(f"quarterly_financials failed for {symbol}: {e}")

        return {
            'earnings_date': earnings_date,
            'is_confirmed': is_confirmed,
            'company_name': company_name,
            'last_revenue': last_revenue,
            'prev_year_revenue': prev_year_revenue,
            'revenue_yoy_change': revenue_yoy_change,
        }

    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {e}")
        return None


def validate_ticker(symbol):
    """
    Return True if the symbol resolves to a real security, False otherwise.
    Uses a short history fetch as the most reliable signal.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period='5d')
        if not hist.empty:
            return True
        # Fallback: check info dict
        info = ticker.info or {}
        return bool(info.get('longName') or info.get('shortName'))
    except Exception:
        return False
