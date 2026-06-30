import requests
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import NAVITIME_CLIENT_KEY

NAVITIME_TRANSFER_URL = "https://api.navitime.jp/sa/v1/transfer"


def get_commute_minutes(from_station, to_station):
    """用 NAVITIME Transfer API 算换乘分钟。无 key 或失败返回 None(降级)。"""
    if not NAVITIME_CLIENT_KEY:
        return None
    try:
        resp = requests.get(NAVITIME_TRANSFER_URL, params={
            "start": from_station,
            "goal": to_station,
            "client_key": NAVITIME_CLIENT_KEY,
        }, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        items = data.get("items", [])
        if not items:
            return None
        return items[0].get("summary", {}).get("moveTime")
    except (requests.RequestException, KeyError, ValueError):
        return None