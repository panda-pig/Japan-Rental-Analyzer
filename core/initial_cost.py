import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    DEFAULT_BROKER_FEE_RATE, DEFAULT_PREPAID_RENT_MONTHS, DEFAULT_MISC_COST,
)


def estimate_initial_cost(rent, deposit, key_money,
                          broker_fee_rate=DEFAULT_BROKER_FEE_RATE,
                          prepaid_rent_months=DEFAULT_PREPAID_RENT_MONTHS,
                          misc_cost=DEFAULT_MISC_COST):
    """初期费用估算 = 敷金 + 礼金 + 仲介手数料 + 前家賃 + 固定杂费"""
    if rent is None:
        return None
    deposit = deposit or 0
    key_money = key_money or 0
    broker = int(rent * broker_fee_rate)
    prepaid = rent * prepaid_rent_months
    return int(deposit + key_money + broker + prepaid + misc_cost)