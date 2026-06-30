import time
import urllib.robotparser
from urllib.parse import urlparse
import requests
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SCRAPE_SLEEP_SECONDS, SCRAPE_USER_AGENT


def check_robots_allowed(url):
    """检查 url 是否被 robots.txt 允许。"""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    try:
        resp = requests.get(robots_url, headers={"User-Agent": SCRAPE_USER_AGENT}, timeout=10)
        if resp.status_code == 200:
            rp.parse(resp.text.splitlines())
        else:
            return True
    except requests.RequestException:
        return True
    return rp.can_fetch(SCRAPE_USER_AGENT, url)


def fetch_html(url):
    """抓取单页 HTML。返回 HTML 字符串或 None(robots disallow / 网络错误)。"""
    if not check_robots_allowed(url):
        return None
    try:
        resp = requests.get(url, headers={"User-Agent": SCRAPE_USER_AGENT}, timeout=15)
        resp.raise_for_status()
        time.sleep(SCRAPE_SLEEP_SECONDS)
        return resp.text
    except requests.RequestException:
        return None