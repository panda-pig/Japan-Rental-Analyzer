import sqlite3
import sys
import os
from contextlib import contextmanager
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    # schema.sql は外部キーを宣言しているが、SQLite は既定で強制しない。
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def transaction(immediate=False):
    """複数の書き込みを1つの接続・1つのトランザクションで行う。

    途中で失敗したらロールバックする。物件の削除のように複数テーブルを
    触る操作を execute() で並べると接続もコミットも分かれ、
    途中で失敗すると中途半端に消えた状態が残ってしまう。
    """
    conn = get_conn()
    try:
        if immediate:
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query_all(sql, args=()):
    conn = get_conn()
    try:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def query_one(sql, args=()):
    conn = get_conn()
    try:
        row = conn.execute(sql, args).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def execute(sql, args=()):
    with transaction() as conn:
        return conn.execute(sql, args).lastrowid
