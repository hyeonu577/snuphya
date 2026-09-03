import datetime
import sqlite3

import xxhash

from config import DB_PATH

_conn = None


def init_db():
    global _conn
    _conn = sqlite3.connect(DB_PATH)
    cursor = _conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS checked_items (
            hash_value TEXT PRIMARY KEY,
            title TEXT,
            created_at TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS click_counts (
            title_hash TEXT PRIMARY KEY,
            title TEXT,
            click_count INTEGER DEFAULT 0,
            first_clicked_at TEXT,
            last_clicked_at TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processing_batches (
            batch_id TEXT PRIMARY KEY,
            created_at TEXT
        )
    ''')
    _conn.commit()


def _get_conn():
    if _conn is None:
        init_db()
    return _conn


def update_checked_item_list(hash_value, title):
    conn = _get_conn()
    current_time = datetime.datetime.now().isoformat()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO checked_items (hash_value, title, created_at)
            VALUES (?, ?, ?)
        ''', (hash_value, title, current_time))
        conn.commit()
    except sqlite3.Error:
        raise


def is_checked(hash_value):
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM checked_items WHERE hash_value = ?', (hash_value,))
    return cursor.fetchone() is not None


def increment_click_count(title_hash, title):
    conn = _get_conn()
    current_time = datetime.datetime.now().isoformat()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO click_counts (title_hash, title, click_count, first_clicked_at, last_clicked_at)
        VALUES (?, ?, 1, ?, ?)
        ON CONFLICT(title_hash) DO UPDATE SET
            click_count = click_count + 1,
            last_clicked_at = excluded.last_clicked_at
    ''', (title_hash, title, current_time, current_time))
    conn.commit()


def get_click_count(title_hash):
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT click_count FROM click_counts WHERE title_hash = ?', (title_hash,))
    result = cursor.fetchone()
    return result[0] if result else 0


def get_xxh3_128(string):
    byte_string = string.encode('utf-8')
    return xxhash.xxh3_128(byte_string).hexdigest()


# --- Processing batch list (replaces text file) ---

def add_processing_batch(batch_id):
    conn = _get_conn()
    current_time = datetime.datetime.now().isoformat()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO processing_batches (batch_id, created_at)
        VALUES (?, ?)
    ''', (batch_id, current_time))
    conn.commit()


def get_processing_batches():
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT batch_id FROM processing_batches')
    return [row[0] for row in cursor.fetchall()]


def remove_processing_batch(batch_id):
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM processing_batches WHERE batch_id = ?', (batch_id,))
    conn.commit()


