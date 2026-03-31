import sqlite3
from contextlib import contextmanager
from werkzeug.security import generate_password_hash
import os
import logging

logger = logging.getLogger(__name__)

DATABASE_PATH = os.environ.get('DATABASE_PATH', 'firegame.db')


@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tickers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id, symbol)
            );

            CREATE TABLE IF NOT EXISTS earnings_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker_id INTEGER NOT NULL UNIQUE,
                earnings_date TEXT,
                is_confirmed INTEGER DEFAULT 0,
                company_name TEXT,
                last_revenue REAL,
                prev_year_revenue REAL,
                revenue_yoy_change REAL,
                last_scanned TIMESTAMP,
                FOREIGN KEY (ticker_id) REFERENCES tickers(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS email_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker_id INTEGER NOT NULL,
                earnings_date TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ticker_id) REFERENCES tickers(id) ON DELETE CASCADE
            );
        ''')
        conn.commit()

        # Seed the initial user if not present
        existing = conn.execute(
            'SELECT id FROM users WHERE username = ?', ('michael',)
        ).fetchone()

        if not existing:
            password_hash = generate_password_hash('Pin123')
            conn.execute(
                'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                ('michael', 'michaelfoster.public@gmail.com', password_hash)
            )
            conn.commit()
            logger.info("Seeded initial user: michael")
