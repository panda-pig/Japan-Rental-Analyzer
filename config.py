import os
from dotenv import load_dotenv

load_dotenv()

NAVITIME_CLIENT_KEY = os.getenv("NAVITIME_CLIENT_KEY", "")
NAVITIME_ENABLED = bool(NAVITIME_CLIENT_KEY)

DB_PATH = os.path.join(os.path.dirname(__file__), "db", "database.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

# 初期费用估算默认系数(设置页可改,存 user_preferences)
DEFAULT_BROKER_FEE_RATE = 0.55      # 仲介手数料 = 家賃 × 0.55
DEFAULT_PREPAID_RENT_MONTHS = 1     # 前家賃月数
DEFAULT_MISC_COST = 40000           # 火災保険/保証会社等固定杂费

# 抓取礼仪
SCRAPE_SLEEP_SECONDS = 2.5
SCRAPE_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)