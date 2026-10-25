import sys
import os
from decimal import Decimal
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    DEFAULT_BROKER_FEE_RATE, DEFAULT_PREPAID_RENT_MONTHS, DEFAULT_MISC_COST,
)


def initial_cost_breakdown(rent, deposit, key_money,
                          broker_fee_rate=DEFAULT_BROKER_FEE_RATE,
                          prepaid_rent_months=DEFAULT_PREPAID_RENT_MONTHS,
                          misc_cost=DEFAULT_MISC_COST):
    """Return integer-yen components, truncating each calculated fee once."""
    if rent is None or deposit is None or key_money is None:
        return None
    amount = Decimal(str(rent))
    return {
        "deposit": int(deposit), "key_money": int(key_money),
        "broker_fee": int(amount * Decimal(str(broker_fee_rate))),
        "prepaid_rent": int(amount * Decimal(str(prepaid_rent_months))),
        "misc_cost": int(misc_cost),
    }


def estimate_initial_cost(rent, deposit, key_money,
                          broker_fee_rate=DEFAULT_BROKER_FEE_RATE,
                          prepaid_rent_months=DEFAULT_PREPAID_RENT_MONTHS,
                          misc_cost=DEFAULT_MISC_COST):
    """Use the same components for storage, report totals and charts."""
    parts = initial_cost_breakdown(rent, deposit, key_money, broker_fee_rate, prepaid_rent_months, misc_cost)
    return sum(parts.values()) if parts is not None else None
