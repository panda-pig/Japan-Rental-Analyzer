import ipaddress
import socket
import time
import urllib.robotparser
from urllib.parse import urlparse, urljoin
import requests
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SCRAPE_SLEEP_SECONDS, SCRAPE_USER_AGENT

# 取得を許可する不動産サイト。ホスト名の完全一致かサブドメインのみ通す。
ALLOWED_DOMAINS = ("suumo.jp", "homes.co.jp", "athome.jp", "yahoo.co.jp")
MAX_REDIRECTS = 5


def allowed_domain(url):
    """許可ドメインなら該当ドメインを返す。それ以外は None。"""
    try:
        p = urlparse(url)
    except ValueError:
        return None
    if p.scheme not in ("http", "https"):
        return None
    host = (p.hostname or "").lower().rstrip(".")
    if not host:
        return None
    for d in ALLOWED_DOMAINS:
        if host == d or host.endswith("." + d):
            return d
    return None


def _resolves_to_public_ip(host):
    """DNS リバインディング対策: 名前解決した先が全てグローバル IP か確認する。"""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if not ip.is_global:
            return False
    return True


def is_safe_url(url):
    """許可ドメインで、かつ解決先が公開 IP のときだけ True。"""
    if not allowed_domain(url):
        return False
    return _resolves_to_public_ip(urlparse(url).hostname)


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
    """抓取单页 HTML。返回 HTML 字符串或 None(不許可ドメイン / robots disallow / 网络错误)。

    リダイレクトは自動追従させず、1ホップごとに許可ドメインか検査する。
    自動追従だと許可ドメインから内部アドレスへ逃がされる余地が残るため。
    """
    if not is_safe_url(url):
        return None
    if not check_robots_allowed(url):
        return None
    try:
        for _hop in range(MAX_REDIRECTS):
            resp = requests.get(url, headers={"User-Agent": SCRAPE_USER_AGENT},
                                timeout=15, allow_redirects=False)
            if resp.is_redirect or resp.is_permanent_redirect:
                nxt = urljoin(url, resp.headers.get("Location", ""))
                if not is_safe_url(nxt):
                    return None
                url = nxt
                continue
            resp.raise_for_status()
            time.sleep(SCRAPE_SLEEP_SECONDS)
            return resp.text
        return None
    except requests.RequestException:
        return None