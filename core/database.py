import datetime, sqlite3
class RakshakDatabase:
    def __init__(self, db_path: str = "rakshak_cache.db"):
        self.db_path = db_path; self.init_db()
    def get_connection(self): return sqlite3.connect(self.db_path, timeout=10)
    def init_db(self):
        c = self.get_connection()
        try:
            c.execute("CREATE TABLE IF NOT EXISTS url_cache (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT UNIQUE, risk_score INTEGER, risk_level TEXT, scan_data TEXT, timestamp TEXT)")
            c.execute("CREATE TABLE IF NOT EXISTS apk_cache (id INTEGER PRIMARY KEY AUTOINCREMENT, sha256 TEXT UNIQUE, risk_score INTEGER, risk_level TEXT, scan_data TEXT, timestamp TEXT)")
            c.execute("CREATE TABLE IF NOT EXISTS scan_history (id INTEGER PRIMARY KEY AUTOINCREMENT, scan_type TEXT NOT NULL, target TEXT NOT NULL, risk_score INTEGER NOT NULL, risk_level TEXT NOT NULL, source TEXT DEFAULT 'fresh_scan', timestamp TEXT NOT NULL)")
            c.commit()
        finally: c.close()
    def cache_url(self, url, risk_score, risk_level, scan_data):
        c = self.get_connection()
        try: c.execute("INSERT OR REPLACE INTO url_cache (url, risk_score, risk_level, scan_data, timestamp) VALUES (?, ?, ?, ?, ?)", (url, risk_score, risk_level, scan_data, datetime.datetime.now(datetime.timezone.utc).isoformat())); c.commit()
        finally: c.close()
    def get_cached_url(self, url):
        c = self.get_connection()
        try: return c.execute("SELECT risk_score, risk_level, scan_data FROM url_cache WHERE url = ?", (url,)).fetchone()
        finally: c.close()
    def cache_apk(self, sha256, risk_score, risk_level, scan_data):
        c = self.get_connection()
        try: c.execute("INSERT OR REPLACE INTO apk_cache (sha256, risk_score, risk_level, scan_data, timestamp) VALUES (?, ?, ?, ?, ?)", (sha256, risk_score, risk_level, scan_data, datetime.datetime.now(datetime.timezone.utc).isoformat())); c.commit()
        finally: c.close()
    def get_cached_apk(self, sha256):
        c = self.get_connection()
        try: return c.execute("SELECT risk_score, risk_level, scan_data FROM apk_cache WHERE sha256 = ?", (sha256,)).fetchone()
        finally: c.close()
    def log_scan(self, scan_type, target, risk_score, risk_level, source="fresh_scan"):
        c = self.get_connection()
        try: c.execute("INSERT INTO scan_history (scan_type, target, risk_score, risk_level, source, timestamp) VALUES (?, ?, ?, ?, ?, ?)", (scan_type, target[:180], int(risk_score), str(risk_level), source, datetime.datetime.now(datetime.timezone.utc).isoformat())); c.commit()
        finally: c.close()
    def get_recent_scans(self, limit=12):
        c = self.get_connection()
        try: return [{"type": r[0], "target": r[1], "risk_score": r[2], "risk_level": r[3], "source": r[4], "timestamp": r[5]} for r in c.execute("SELECT scan_type, target, risk_score, risk_level, source, timestamp FROM scan_history ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]
        finally: c.close()
    def clear_history(self):
        c = self.get_connection()
        try: c.execute("DELETE FROM scan_history"); c.commit()
        finally: c.close()
