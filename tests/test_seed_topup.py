import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import pytest
from scripts import seed_regions as seed


@pytest.fixture
def db(tmp_path, monkeypatch):
    """region_stats だけを持つ空DBを用意し、seed_regions が見る DB_PATH を差し替える。"""
    path = str(tmp_path / "t.db")
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE region_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        prefecture TEXT, city TEXT, ward TEXT, avg_rent INTEGER,
        avg_area REAL, avg_building_age INTEGER,
        safety_level TEXT, convenience_level TEXT, environment_level TEXT,
        trade_price_per_m2 INTEGER, hazard_level TEXT, updated_at TEXT)""")
    conn.commit()
    conn.close()
    monkeypatch.setattr(seed, "DB_PATH", path)
    return path


def _rows(path):
    conn = sqlite3.connect(path)
    out = conn.execute("SELECT prefecture, city, ward FROM region_stats").fetchall()
    conn.close()
    return out


def test_adds_only_what_is_missing(db):
    added = seed.seed_missing_regions()
    assert len(added) == len(seed._major_rows())
    assert len(_rows(db)) == len(seed._major_rows())


def test_is_idempotent(db):
    seed.seed_missing_regions()
    n = len(_rows(db))
    assert seed.seed_missing_regions() == []
    assert len(_rows(db)) == n


def test_leaves_existing_rows_and_their_public_data_alone(db):
    """公的データ(取引価格・災害)を持つ既存行に触れないこと。"""
    conn = sqlite3.connect(db)
    conn.execute("""INSERT INTO region_stats
        (prefecture, city, ward, avg_rent, trade_price_per_m2, hazard_level)
        VALUES ('東京都', NULL, '港区', 277000, 1900000, '高')""")
    # 主要都市のうち1件は既にある状態にする
    conn.execute("INSERT INTO region_stats (prefecture, city, ward, avg_rent) "
                 "VALUES ('大阪府', NULL, '大阪市', 95000)")
    conn.commit()
    conn.close()

    added = seed.seed_missing_regions()
    assert "大阪市" not in added

    conn = sqlite3.connect(db)
    row = conn.execute("SELECT avg_rent, trade_price_per_m2, hazard_level "
                       "FROM region_stats WHERE ward='港区'").fetchone()
    dupes = conn.execute("SELECT COUNT(*) FROM (SELECT prefecture, city, ward "
                         "FROM region_stats GROUP BY 1,2,3 HAVING COUNT(*)>1)").fetchone()[0]
    conn.close()
    assert row == (277000, 1900000, '高')
    assert dupes == 0
