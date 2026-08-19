"""まちむすび スコア抽出のユニットテスト (構造非依存の近傍マッチを検証)。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scrapers.machimusubi import (parse_station_scores, normalize_station,
                                  extract_station, _romaji, _romaji_variants,
                                  _normalize_romaji)

SYNTH = """
<html><body>
<h2>住みやすさアンケート</h2>
<ul>
  <li><span class="label">交通の利便性</span><svg>...</svg><span class="pt">4.3</span></li>
  <li><span class="label">治安の良さ</span><span class="pt">4.2</span></li>
  <li><span class="label">買い物のしやすさ</span><span class="pt">3.7</span></li>
  <li><span class="label">子育てのしやすさ</span><span class="pt">3.6</span></li>
  <li><span class="label">自然の多さ</span><span class="pt">3.2</span></li>
</ul>
<script>var noise = {"交通の利便性": 9.9};</script>
</body></html>
"""


def test_parse_station_scores():
    s = parse_station_scores(SYNTH)
    assert s == {"transport": 4.3, "safety": 4.2, "shopping": 3.7,
                 "childcare": 3.6, "nature": 3.2}


def test_parse_missing_returns_partial():
    s = parse_station_scores("<p>交通の利便性 4.0</p><p>治安の良さ n/a</p>")
    assert s == {"transport": 4.0}


def test_normalize_station():
    assert normalize_station("東神奈川駅") == "東神奈川"
    assert normalize_station(" 横浜 ") == "横浜"
    assert normalize_station("") is None
    assert normalize_station(None) is None


def test_extract_station_clean():
    assert extract_station("東神奈川") == "東神奈川"
    assert extract_station("東神奈川駅") == "東神奈川"
    assert extract_station(None) is None


def test_extract_station_dirty_picks_min_walk():
    raw = "ＪＲ山手線/東京駅 歩10分東京メトロ銀座線/京橋駅 歩7分東京メトロ日比谷線/八丁堀駅 歩3分"
    assert extract_station(raw) == "八丁堀"


def test_extract_station_single_with_walk():
    assert extract_station("京急本線/仲木戸駅 歩5分") == "仲木戸"
    assert extract_station("東急東横線/白楽駅 徒歩8分") == "白楽"


def test_romaji_matches_slug_conventions():
    assert _romaji("八丁堀") == "hatchobori"
    assert _romaji("東京") == "tokyo"
    assert _romaji("京橋") == "kyobashi"
    assert _romaji("新橋") == "shimbashi"
    assert _romaji("大倉山") == "okurayama"
    assert _romaji("自由が丘") == "jiyugaoka"
    assert _romaji("東神奈川") == "higashikanagawa"


def test_normalize_romaji_slug_side():
    assert _normalize_romaji("hatchobori") == "hatchobori"
    assert _normalize_romaji("shimbashi") == "shimbashi"


def test_romaji_ke_ga_stations():
    assert "hodogaya" in _romaji_variants("保土ケ谷")
    assert "kibogaoka" in _romaji_variants("希望ヶ丘")
    assert "tsurugamine" in _romaji_variants("鶴ヶ峰")
    assert "ichigaya" in _romaji_variants("市ヶ谷")


def test_romaji_reading_overrides():
    assert _romaji("阿佐ヶ谷") == "asagaya"
    assert _romaji("日ノ出町") == "hinodecho"
    assert _romaji("三ツ境") == "mitsukyo"
    assert _romaji("大井町") == "oimachi"
    assert _romaji("向河原") == "mukaigawara"
    assert _romaji("たまプラーザ") == "tamaplaza"
