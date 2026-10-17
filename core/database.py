import sqlite3
import datetime
import os

class RakshakDatabase:
    def __init__(self, db_path="rakshak_cache.db"):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        """Creates tables for caching URL scans and APK SHA-256 analysis results."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS url_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE,
                risk_score INTEGER,
                risk_level TEXT,
                scan_data TEXT,
                timestamp DATETIME
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS apk_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sha256 TEXT UNIQUE,
                risk_score INTEGER,
                risk_level TEXT,
                scan_data TEXT,
                timestamp DATETIME
            )
        ''')
        
        conn.commit()
        conn.close()

    def cache_url(self, url: str, risk_score: int, risk_level: str, scan_data: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.datetime.now()
        cursor.execute('''
            INSERT OR REPLACE INTO url_cache (url, risk_score, risk_level, scan_data, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (url, risk_score, risk_level, scan_data, now))
        conn.commit()
        conn.close()

    def get_cached_url(self, url: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT risk_score, risk_level, scan_data FROM url_cache WHERE url = ?', (url,))
        row = cursor.fetchone()
        conn.close()
        return row

    def cache_apk(self, sha256: str, risk_score: int, risk_level: str, scan_data: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        now = datetime.datetime.now()
        cursor.execute('''
            INSERT OR REPLACE INTO apk_cache (sha256, risk_score, risk_level, scan_data, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (sha256, risk_score, risk_level, scan_data, now))
        conn.commit()
        conn.close()

    def get_cached_apk(self, sha256: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT risk_score, risk_level, scan_data FROM apk_cache WHERE sha256 = ?', (sha256,))
        row = cursor.fetchone()
        conn.close()
        return row

if __name__ == "__main__":
    db = RakshakDatabase()
    print("Database module initialized successfully.")
