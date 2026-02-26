import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from icalendar import Calendar, Event
from datetime import datetime, timedelta, date
import uuid
import os
import logging

logger = logging.getLogger(__name__)

SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
SMTP_FROM = os.environ.get('SMTP_FROM', '') or SMTP_USER

RECIPIENT_NAME = 'Michael'
RECIPIENT_EMAIL = 'michaelfoster.public@gmail.com'


# ── Helpers ───────────────────────────────────────────────────────────────────

def format_revenue(amount):
    """Return a human-readable revenue string (e.g. $12.34B)."""
    if amount is None:
        return 'N/A'
    if abs(amount) >= 1e12:
        return f'${amount / 1e12:.2f}T'
    if abs(amount) >= 1e9:
        return f'${amount / 1e9:.2f}B'
    if abs(amount) >= 1e6:
        return f'${amount / 1e6:.2f}M'
    return f'${amount:,.0f}'


# ── ICS generation ────────────────────────────────────────────────────────────

def generate_ics(symbol, company_name, earnings_date,
                 last_revenue=None, prev_year_revenue=None,
                 revenue_yoy_change=None):
    """Build an RFC-5545 VCALENDAR byte string for the earnings event."""
    cal = Calendar()
    cal.add('prodid', '-//Stock Earnings Alerts//firegame//EN')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('method', 'PUBLISH')

    event = Event()
    event.add('uid', str(uuid.uuid4()) + '@firegame')
    event.add('summary', f'{symbol} Earnings Release')
    # All-day event
    event.add('dtstart', earnings_date)
    event.add('dtend', earnings_date + timedelta(days=1))
    event.add('dtstamp', datetime.utcnow())

    desc_lines = [f'{company_name} ({symbol}) — Earnings Release']
    if last_revenue is not None:
        desc_lines.append(f'Last Quarter Revenue: {format_revenue(last_revenue)}')
    if prev_year_revenue is not None:
        desc_lines.append(f'Same Quarter Last Year: {format_revenue(prev_year_revenue)}')
    if revenue_yoy_change is not None:
        sign = '+' if revenue_yoy_change >= 0 else ''
        desc_lines.append(f'Year-over-Year Change: {sign}{revenue_yoy_change:.1f}%')

    event.add('description', '\n'.join(desc_lines))
    cal.add_component(event)
    return cal.to_ical()


# ── HTML email body ───────────────────────────────────────────────────────────

def _build_html(symbol, company_name, earnings_date, days_until,
                last_revenue, prev_year_revenue, revenue_yoy_change):
    date_str = earnings_date.strftime('%B %d, %Y')

    if revenue_yoy_change is not None:
        yoy_color = '#16a34a' if revenue_yoy_change >= 0 else '#dc2626'
        sign = '+' if revenue_yoy_change >= 0 else ''
        yoy_str = f'{sign}{revenue_yoy_change:.1f}%'
        yoy_arrow = '▲' if revenue_yoy_change >= 0 else '▼'
    else:
        yoy_color = '#6b7280'
        yoy_str = 'N/A'
        yoy_arrow = ''

    def row(label, value, value_style=''):
        return f'''
        <tr>
          <td style="padding:10px 16px;color:#6b7280;font-size:14px;border-bottom:1px solid #f3f4f6;">{label}</td>
          <td style="padding:10px 16px;font-weight:600;text-align:right;border-bottom:1px solid #f3f4f6;{value_style}">{value}</td>
        </tr>'''

    fin_rows = ''
    if last_revenue is not None:
        fin_rows += row('Last Quarter Revenue', format_revenue(last_revenue))
    if prev_year_revenue is not None:
        fin_rows += row('Same Quarter Last Year', format_revenue(prev_year_revenue))
    if revenue_yoy_change is not None:
        fin_rows += row(
            'Year-over-Year Change',
            f'{yoy_arrow} {yoy_str}',
            f'color:{yoy_color};'
        )

    financials_block = ''
    if fin_rows:
        financials_block = f'''
        <div style="margin:20px 0;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden;">
          <div style="background:#f9fafb;padding:10px 16px;border-bottom:1px solid #e5e7eb;">
            <span style="font-size:12px;font-weight:700;text-transform:uppercase;
                         letter-spacing:.06em;color:#374151;">Financial Highlights</span>
          </div>
          <table style="width:100%;border-collapse:collapse;background:white;">
            {fin_rows}
          </table>
        </div>'''

    plural = 's' if days_until != 1 else ''
    countdown = (
        f'<strong>{days_until} day{plural}</strong> until earnings'
        if days_until > 0 else 'Earnings are <strong>today</strong>'
    )

    return f'''<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:24px 16px;background:#f3f4f6;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:540px;margin:0 auto;background:#fff;border-radius:14px;
              overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.1);">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,#1e3a5f 0%,#2563eb 100%);
                padding:32px 24px;text-align:center;">
      <div style="font-size:40px;margin-bottom:10px;">📊</div>
      <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;letter-spacing:-.2px;">
        Earnings Alert
      </h1>
      <p style="margin:8px 0 0;color:rgba(255,255,255,.75);font-size:14px;">{countdown}</p>
    </div>

    <!-- Body -->
    <div style="padding:24px;">

      <!-- Ticker card -->
      <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;
                  padding:16px;margin-bottom:4px;">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;">
          <div>
            <span style="font-size:26px;font-weight:800;color:#1e3a5f;letter-spacing:-.5px;">{symbol}</span>
            <div style="color:#6b7280;font-size:13px;margin-top:2px;">{company_name}</div>
          </div>
          <div style="text-align:right;">
            <div style="font-size:12px;color:#6b7280;text-transform:uppercase;
                        letter-spacing:.05em;margin-bottom:2px;">Earnings Date</div>
            <div style="font-size:15px;font-weight:700;color:#1d4ed8;">{date_str}</div>
          </div>
        </div>
      </div>

      {financials_block}

      <!-- ICS note -->
      <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;
                  padding:12px 16px;margin-top:20px;">
        <p style="margin:0;font-size:13px;color:#166534;line-height:1.5;">
          📎 A calendar invite (.ics) is attached — import it into your calendar app
          to set a reminder for this earnings release.
        </p>
      </div>

    </div><!-- /Body -->

    <!-- Footer -->
    <div style="border-top:1px solid #f3f4f6;padding:14px 24px;text-align:center;">
      <p style="margin:0;font-size:12px;color:#9ca3af;">
        Stock Earnings Alerts &mdash; automated notification for {RECIPIENT_NAME}
      </p>
    </div>

  </div>
</body>
</html>'''


# ── Public send function ──────────────────────────────────────────────────────

def send_earnings_alert(symbol, company_name, earnings_date, days_until,
                        last_revenue=None, prev_year_revenue=None,
                        revenue_yoy_change=None):
    """
    Send an HTML email with an .ics attachment for the given earnings event.
    Returns True on success, False on failure.
    If SMTP credentials are not configured, logs a warning and returns False.
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning(
            f"[email_service] SMTP not configured — skipping alert for "
            f"{symbol} (earnings {earnings_date}, {days_until}d away)"
        )
        return False

    try:
        subject = (
            f'Earnings Alert: {symbol} reports in '
            f'{days_until} day{"s" if days_until != 1 else ""} '
            f'({earnings_date.strftime("%b %d, %Y")})'
        )

        msg = MIMEMultipart('mixed')
        msg['From'] = f'Stock Earnings Alerts <{SMTP_FROM or SMTP_USER}>'
        msg['To'] = f'{RECIPIENT_NAME} <{RECIPIENT_EMAIL}>'
        msg['Subject'] = subject

        # HTML part
        html_body = _build_html(
            symbol, company_name, earnings_date, days_until,
            last_revenue, prev_year_revenue, revenue_yoy_change
        )
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        # ICS attachment
        ics_bytes = generate_ics(
            symbol, company_name, earnings_date,
            last_revenue, prev_year_revenue, revenue_yoy_change
        )
        ics_part = MIMEBase('text', 'calendar', method='PUBLISH', name='earnings.ics')
        ics_part.set_payload(ics_bytes)
        encoders.encode_base64(ics_part)
        filename = f'{symbol}_earnings_{earnings_date}.ics'
        ics_part.add_header('Content-Disposition', 'attachment', filename=filename)
        msg.attach(ics_part)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM or SMTP_USER, RECIPIENT_EMAIL, msg.as_string())

        logger.info(f"[email_service] Alert sent: {symbol} earnings on {earnings_date}")
        return True

    except Exception as e:
        logger.error(f"[email_service] Failed to send alert for {symbol}: {e}")
        return False
