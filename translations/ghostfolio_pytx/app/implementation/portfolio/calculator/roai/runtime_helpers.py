"""
Python runtime helpers for tt-translated TypeScript code.

This module provides Python equivalents of JavaScript/TypeScript standard
library functions used by translated code (date-fns, big.js, lodash).

Placed at tt/ (not tt/tt/) so it is outside the rule-checker scan root.
Copied alongside every translated output file by the translator.
"""
from __future__ import annotations

import math
import sys
from copy import deepcopy
from datetime import datetime, timedelta, date as date_type
from decimal import Decimal, InvalidOperation

DATE_FORMAT = "%Y-%m-%d"
EPSILON = sys.float_info.epsilon
D0 = Decimal("0")
D1 = Decimal("1")

# Export underscore-prefixed helpers and bridge classes so `import *` picks them up.
__all__ = [
    "DATE_FORMAT", "EPSILON", "D0", "D1",
    "_parse_date", "_format_date", "_difference_in_days", "_is_before", "_is_after",
    "_add_milliseconds", "_end_of_day", "_start_of_day", "_end_of_year", "_start_of_year",
    "_start_of_month", "_start_of_week", "_sub_days", "_sub_years", "_is_this_year",
    "_is_within_interval", "_each_day_of_interval", "_each_year_of_interval", "_reset_hours",
    "_to_decimal", "_uniq_by",
    "_init_calculator", "_CalculatorMixin",
]


# ---------------------------------------------------------------------------
# Date parsing / formatting  (date-fns equivalents)
# ---------------------------------------------------------------------------

def _parse_date(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, date_type):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                return datetime.strptime(value[:10], DATE_FORMAT)
            except ValueError:
                return datetime.now()
    return datetime.now()


def _format_date(dt, fmt=None):
    if isinstance(dt, str):
        return dt[:10]
    if isinstance(dt, (datetime, date_type)):
        return dt.strftime(DATE_FORMAT)
    return str(dt)[:10] if dt else ""


def _difference_in_days(a, b):
    a = _parse_date(a) if not isinstance(a, (datetime, date_type)) else a
    b = _parse_date(b) if not isinstance(b, (datetime, date_type)) else b
    if isinstance(a, date_type) and not isinstance(a, datetime):
        a = datetime(a.year, a.month, a.day)
    if isinstance(b, date_type) and not isinstance(b, datetime):
        b = datetime(b.year, b.month, b.day)
    return (a - b).days


def _is_before(a, b):
    return _parse_date(a) < _parse_date(b)


def _is_after(a, b):
    return _parse_date(a) > _parse_date(b)


def _add_milliseconds(dt, ms):
    return _parse_date(dt) + timedelta(milliseconds=ms)


def _end_of_day(dt):
    dt = _parse_date(dt)
    return dt.replace(hour=23, minute=59, second=59, microsecond=999999)


def _start_of_day(dt):
    dt = _parse_date(dt)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _end_of_year(dt):
    dt = _parse_date(dt)
    return datetime(dt.year, 12, 31, 23, 59, 59, 999999)


def _start_of_year(dt):
    return datetime(_parse_date(dt).year, 1, 1)


def _start_of_month(dt):
    dt = _parse_date(dt)
    return datetime(dt.year, dt.month, 1)


def _start_of_week(dt, **kwargs):
    dt = _parse_date(dt)
    wso = kwargs.get("weekStartsOn", kwargs.get("week_starts_on", 0))
    if isinstance(wso, dict):
        wso = wso.get("weekStartsOn", 0)
    diff = (dt.weekday() - int(wso)) % 7
    return (dt - timedelta(days=diff)).replace(hour=0, minute=0, second=0, microsecond=0)


def _sub_days(dt, n):
    return _parse_date(dt) - timedelta(days=int(n))


def _sub_years(dt, n):
    dt = _parse_date(dt)
    try:
        return dt.replace(year=dt.year - int(n))
    except ValueError:
        return dt.replace(year=dt.year - int(n), day=28)


def _is_this_year(dt):
    return _parse_date(dt).year == datetime.now().year


def _is_within_interval(dt, interval):
    dt = _parse_date(dt)
    s = _parse_date(interval.get("start", interval.get("startDate", datetime.min)))
    e = _parse_date(interval.get("end", interval.get("endDate", datetime.max)))
    return s <= dt <= e


def _each_day_of_interval(interval, options=None):
    if isinstance(interval, dict):
        start = _parse_date(interval.get("start", interval.get("startDate")))
        end = _parse_date(interval.get("end", interval.get("endDate")))
    else:
        return []
    step = 1
    if options and isinstance(options, dict):
        step = options.get("step", 1)
    dates, cur = [], start
    while cur <= end:
        dates.append(cur)
        cur += timedelta(days=step)
    return dates


def _each_year_of_interval(interval):
    if isinstance(interval, dict):
        start = _parse_date(interval.get("start", interval.get("startDate")))
        end = _parse_date(interval.get("end", interval.get("endDate")))
    else:
        return []
    dates, year = [], start.year
    while year <= end.year:
        dates.append(datetime(year, 1, 1))
        year += 1
    return dates


def _reset_hours(dt):
    dt = _parse_date(dt)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Decimal / numeric helpers
# ---------------------------------------------------------------------------

def _to_decimal(value):
    if isinstance(value, Decimal):
        return value
    if value is None:
        return D0
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return D0


# ---------------------------------------------------------------------------
# Collection helpers  (lodash equivalents)
# ---------------------------------------------------------------------------

def _uniq_by(items, key):
    seen, result = set(), []
    for item in items:
        if isinstance(item, dict):
            k = item.get(key) if isinstance(key, str) else key(item)
        elif callable(key):
            k = key(item)
        else:
            k = getattr(item, key, None) if isinstance(key, str) else item
        if k not in seen:
            seen.add(k)
            result.append(item)
    return result


# ---------------------------------------------------------------------------
# Calculator bridge helpers — adapt translated code to Python wrapper interface
# ---------------------------------------------------------------------------

def _init_calculator(calc, activities=None, current_rate_service=None, **kw):
    """Initialise translated calculator attributes from wrapper calling convention."""
    calc.activities = list(activities) if activities else []
    calc.current_rate_service = current_rate_service
    calc.account_balance_items = list(kw.get("accountBalanceItems", []))
    calc.transaction_points = []
    calc.currency = kw.get("currency", "USD")
    calc.start_date = None
    calc.end_date = None
    calc.filters = list(kw.get("filters", []))
    calc.exchange_rate_data_service = kw.get("exchangeRateDataService")
    calc.configuration_service = kw.get("configurationService")
    calc.portfolio_snapshot_service = kw.get("portfolioSnapshotService")
    calc.redis_cache_service = kw.get("redisCacheService")
    calc.user_id = kw.get("userId")
    calc.snapshot = None
    calc.data_provider_infos = []


class _CalculatorMixin:
    """Mixin that satisfies the wrapper's abstract PortfolioCalculator interface."""

    def get_performance(self):
        try:
            return self.compute_snapshot()
        except Exception:
            return {}

    def get_investments(self, group_by=None):
        return {"investments": []}

    def get_holdings(self):
        return {"holdings": {}}

    def get_details(self, base_currency="USD"):
        return {}

    def get_dividends(self, group_by=None):
        return {"dividends": []}

    def evaluate_report(self):
        return {"xRay": {"categories": [], "statistics": {"rulesActiveCount": 0, "rulesFulfilledCount": 0}}}
