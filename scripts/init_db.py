import sqlite3
import os
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH, SCHEMA_PATH
from scripts.migrations import migrate, VERSION


def init_db(path=None):
    path = Path(path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists() and path.stat().st_size > 0
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        has_versions = conn.execute("SELECT 1 FROM sqlite_master WHERE name='schema_migrations'").fetchone()
        current = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] if has_versions else 0
        if existed and (current or 0) < VERSION:
            backup_dir = path.parent / "backups"
            backup_dir.mkdir(exist_ok=True)
            backup = backup_dir / f"{path.stem}-pre-v{VERSION}-{datetime.now():%Y%m%dT%H%M%S%f}.db"
            dest = sqlite3.connect(backup)
            try:
                conn.backup(dest)
            finally:
                dest.close()
            print(f"Database backup: {backup}")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(Path(SCHEMA_PATH).read_text(encoding="utf-8"))
        migrate(conn)
        conn.execute("INSERT OR IGNORE INTO user_preferences (id) VALUES (1)")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
