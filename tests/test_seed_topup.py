import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import pytest
from scripts import seed_regions as seed


@pytest.fixture
def db(tmp_path, monkeypatch):
    from scripts.init_db import init_db
    path = str(tmp_path / "t.db")
    init_db(path)
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


def test_matches_existing_rows_stored_in_the_older_shape(db):
    """大阪市が (city=大阪市, ward=NULL) で入っていても重複させないこと。

    タプル完全一致で照合していたため、本番で大阪市・京都市が二重になった。
    """
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO region_stats (prefecture, city, ward, avg_rent) "
                 "VALUES ('大阪府', '大阪市', NULL, 95000)")
    conn.commit()
    conn.close()

    added = seed.seed_missing_regions()
    assert "大阪市" not in added

    conn = sqlite3.connect(db)
    n = conn.execute("SELECT COUNT(*) FROM region_stats "
                     "WHERE COALESCE(ward, city)='大阪市'").fetchone()[0]
    conn.close()
    assert n == 1


def test_dedupe_collapses_mixed_shapes_and_keeps_public_data(db):
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO region_stats (prefecture, city, ward, avg_rent) "
                 "VALUES ('大阪府', '大阪市', NULL, 95000)")
    conn.execute("INSERT INTO region_stats (prefecture, city, ward, avg_rent) "
                 "VALUES ('大阪府', NULL, '大阪市', 95000)")
    # 公的データを持つ行は形が違っても残す
    conn.execute("INSERT INTO region_stats (prefecture, city, ward, trade_price_per_m2, hazard_level) "
                 "VALUES ('東京都', NULL, '港区', 1900000, '高')")
    conn.execute("INSERT INTO region_stats (prefecture, city, ward) "
                 "VALUES ('東京都', '港区', NULL)")
    conn.commit()
    conn.close()

    seed.dedupe_regions()

    conn = sqlite3.connect(db)
    dupes = conn.execute("SELECT COUNT(*) FROM (SELECT prefecture, COALESCE(ward, city) "
                         "FROM region_stats GROUP BY 1,2 HAVING COUNT(*)>1)").fetchone()[0]
    minato = conn.execute("SELECT trade_price_per_m2, hazard_level FROM region_stats "
                          "WHERE COALESCE(ward, city)='港区'").fetchone()
    conn.close()
    assert dupes == 0
    assert minato == (1900000, '高'), "公的データを持つ行を残すこと"


def test_dedupe_is_idempotent(db):
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO region_stats (prefecture, city, ward) VALUES ('大阪府','大阪市',NULL)")
    conn.execute("INSERT INTO region_stats (prefecture, city, ward) VALUES ('大阪府',NULL,'大阪市')")
    conn.commit()
    conn.close()
    assert len(seed.dedupe_regions()) == 1
    assert seed.dedupe_regions() == []
