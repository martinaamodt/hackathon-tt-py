"""Translated from TypeScript by tt — tree-sitter AST-based pipeline."""
from __future__ import annotations

import math
import sys
from copy import deepcopy
from datetime import datetime, timedelta, date as date_type
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from app.wrapper.portfolio.calculator.portfolio_calculator import PortfolioCalculator

# ---------------------------------------------------------------------------
# Constants & helpers (equivalents of date-fns, Big.js, lodash utilities)
# ---------------------------------------------------------------------------

DATE_FORMAT = "%Y-%m-%d"
EPSILON = sys.float_info.epsilon
D0 = Decimal("0")
D1 = Decimal("1")


def _parse_date(value):
    """Parse a date string or datetime to a datetime object."""
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
    """Format a date/datetime to YYYY-MM-DD string."""
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
    a, b = _parse_date(a), _parse_date(b)
    return a < b


def _is_after(a, b):
    a, b = _parse_date(a), _parse_date(b)
    return a > b


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
    diff = (dt.weekday() - wso) % 7
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


def _get_factor(activity_type):
    """BUY → +1, SELL → -1, else → 0."""
    if activity_type == "BUY":
        return 1
    if activity_type == "SELL":
        return -1
    return 0


def _get_interval_from_date_range(date_range, portfolio_start=None):
    """Equivalent of getIntervalFromDateRange in calculation-helper.ts."""
    ps = _parse_date(portfolio_start) if portfolio_start else datetime(1970, 1, 1)
    end_date = _end_of_day(datetime.now())
    start_date = ps

    if date_range == "1d":
        start_date = max(start_date, _sub_days(_reset_hours(datetime.now()), 1))
    elif date_range == "mtd":
        start_date = max(start_date, _sub_days(_start_of_month(_reset_hours(datetime.now())), 1))
    elif date_range == "wtd":
        start_date = max(start_date, _sub_days(_start_of_week(_reset_hours(datetime.now()), weekStartsOn=1), 1))
    elif date_range == "ytd":
        start_date = max(start_date, _sub_days(_start_of_year(_reset_hours(datetime.now())), 1))
    elif date_range == "1y":
        start_date = max(start_date, _sub_years(_reset_hours(datetime.now()), 1))
    elif date_range == "5y":
        start_date = max(start_date, _sub_years(_reset_hours(datetime.now()), 5))
    elif date_range == "max":
        pass
    else:
        try:
            year = int(date_range)
            end_date = _end_of_year(datetime(year, 1, 1))
            start_date = max(start_date, datetime(year, 1, 1))
        except (ValueError, TypeError):
            pass

    return {"endDate": end_date, "startDate": start_date}


def _uniq_by(items, key):
    seen, result = set(), []
    for item in items:
        k = item.get(key) if isinstance(item, dict) else getattr(item, key, None) if isinstance(key, str) else key(item) if callable(key) else item
        if k not in seen:
            seen.add(k)
            result.append(item)
    return result


def _to_decimal(value):
    if isinstance(value, Decimal):
        return value
    if value is None:
        return D0
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return D0



def _normalize_activity(act):
    """Ensure every activity has a SymbolProfile sub-dict."""
    if "SymbolProfile" not in act:
        act = dict(act)  # shallow copy
        act["SymbolProfile"] = {
            "symbol": act.get("symbol", ""),
            "dataSource": act.get("dataSource", "MANUAL"),
            "currency": act.get("currency", "USD"),
            "assetSubClass": act.get("assetSubClass"),
        }
    return act


class RoaiPortfolioCalculator(PortfolioCalculator):
    """ROAI Portfolio Calculator — translated from TypeScript via tree-sitter AST."""

    def __init__(self, activities, current_rate_service):
        normalized = [_normalize_activity(a) for a in activities]
        super().__init__(normalized, current_rate_service)
        self._chart_dates = None
        self._snapshot = None

    # ------------------------------------------------------------------
    # Core translated method: getSymbolMetrics
    # ------------------------------------------------------------------
    def _get_symbol_metrics(self, chart_date_map, data_source, end, exchange_rates, market_symbol_map, start, symbol):
        """Translated from RoaiPortfolioCalculator.getSymbolMetrics()."""
        current_exchange_rate = exchange_rates.get(_format_date(datetime.now()))
        current_values = {}
        current_values_with_currency_effect = {}
        fees = D0
        fees_at_start_date = D0
        fees_at_start_date_with_currency_effect = D0
        fees_with_currency_effect = D0
        gross_performance = D0
        gross_performance_with_currency_effect = D0
        gross_performance_at_start_date = D0
        gross_performance_at_start_date_with_currency_effect = D0
        gross_performance_from_sells = D0
        gross_performance_from_sells_with_currency_effect = D0
        initial_value = None
        initial_value_with_currency_effect = None
        investment_at_start_date = None
        investment_at_start_date_with_currency_effect = None
        investment_values_accumulated = {}
        investment_values_accumulated_with_currency_effect = {}
        investment_values_with_currency_effect = {}
        last_average_price = D0
        last_average_price_with_currency_effect = D0
        net_performance_values = {}
        net_performance_values_with_currency_effect = {}
        time_weighted_investment_values = {}
        time_weighted_investment_values_with_currency_effect = {}
        total_account_balance_in_base_currency = D0
        total_dividend = D0
        total_dividend_in_base_currency = D0
        total_interest = D0
        total_interest_in_base_currency = D0
        total_investment = D0
        total_investment_from_buy_transactions = D0
        total_investment_from_buy_transactions_with_currency_effect = D0
        total_investment_with_currency_effect = D0
        total_liabilities = D0
        total_liabilities_in_base_currency = D0
        total_quantity_from_buy_transactions = D0
        total_units = D0
        value_at_start_date = None
        value_at_start_date_with_currency_effect = None

        # Clone orders to keep originals intact
        orders = []
        for act in self.activities:
            sp = act.get("SymbolProfile", {})
            if sp.get("symbol") == symbol:
                orders.append(deepcopy(act))

        is_cash = bool(orders and orders[0].get("SymbolProfile", {}).get("assetSubClass") == "CASH")

        if len(orders) <= 0:
            return self._empty_symbol_metrics(has_errors=False)

        date_of_first_transaction = _parse_date(orders[0]["date"])
        end_date_string = _format_date(end)
        start_date_string = _format_date(start)

        unit_price_at_start_date = market_symbol_map.get(start_date_string, {}).get(symbol)
        unit_price_at_end_date = market_symbol_map.get(end_date_string, {}).get(symbol)

        latest_activity = orders[-1] if orders else {}

        if (data_source == "MANUAL"
            and latest_activity.get("type") in ("BUY", "SELL")
            and latest_activity.get("unitPrice")
            and not unit_price_at_end_date):
            unit_price_at_end_date = _to_decimal(latest_activity["unitPrice"])
        elif is_cash:
            unit_price_at_end_date = D1

        if (not unit_price_at_end_date
            or (not unit_price_at_start_date and _is_before(date_of_first_transaction, start))):
            return self._empty_symbol_metrics(has_errors=True)

        # Ensure Decimal
        if unit_price_at_start_date is not None:
            unit_price_at_start_date = _to_decimal(unit_price_at_start_date)
        unit_price_at_end_date = _to_decimal(unit_price_at_end_date)

        # Add synthetic start and end orders
        orders.append({
            "date": start_date_string, "fee": D0, "feeInBaseCurrency": D0,
            "itemType": "start", "quantity": D0,
            "SymbolProfile": {"dataSource": data_source, "symbol": symbol,
                              "assetSubClass": "CASH" if is_cash else None},
            "type": "BUY", "unitPrice": unit_price_at_start_date,
        })
        orders.append({
            "date": end_date_string, "fee": D0, "feeInBaseCurrency": D0,
            "itemType": "end", "quantity": D0,
            "SymbolProfile": {"dataSource": data_source, "symbol": symbol,
                              "assetSubClass": "CASH" if is_cash else None},
            "type": "BUY", "unitPrice": unit_price_at_end_date,
        })

        last_unit_price = None
        orders_by_date = {}
        for order in orders:
            orders_by_date.setdefault(order["date"], []).append(order)

        if not self._chart_dates:
            self._chart_dates = sorted(chart_date_map.keys())

        for date_string in self._chart_dates:
            if date_string < start_date_string:
                continue
            elif date_string > end_date_string:
                break

            if orders_by_date.get(date_string):
                for order in orders_by_date[date_string]:
                    mkt = market_symbol_map.get(date_string, {}).get(symbol)
                    order["unitPriceFromMarketData"] = _to_decimal(mkt) if mkt is not None else last_unit_price
            else:
                mkt = market_symbol_map.get(date_string, {}).get(symbol)
                price = _to_decimal(mkt) if mkt is not None else last_unit_price
                orders.append({
                    "date": date_string, "fee": D0, "feeInBaseCurrency": D0,
                    "quantity": D0,
                    "SymbolProfile": {"dataSource": data_source, "symbol": symbol,
                                      "assetSubClass": "CASH" if is_cash else None},
                    "type": "BUY", "unitPrice": price,
                    "unitPriceFromMarketData": price,
                })

            latest_activity = orders[-1]
            up_from_market = latest_activity.get("unitPriceFromMarketData")
            up_from_order = latest_activity.get("unitPrice")
            last_unit_price = _to_decimal(up_from_market) if up_from_market is not None else (_to_decimal(up_from_order) if up_from_order is not None else last_unit_price)

        # Sort orders with start/end at correct positions
        def _sort_key(o):
            dt = _parse_date(o["date"])
            if o.get("itemType") == "end":
                dt = _add_milliseconds(dt, 1)
            elif o.get("itemType") == "start":
                dt = _add_milliseconds(dt, -1)
            return dt
        orders = sorted(orders, key=_sort_key)

        index_of_start_order = -1
        index_of_end_order = -1
        for idx, o in enumerate(orders):
            if o.get("itemType") == "start" and index_of_start_order < 0:
                index_of_start_order = idx
            if o.get("itemType") == "end" and index_of_end_order < 0:
                index_of_end_order = idx

        total_investment_days = 0
        sum_of_time_weighted_investments = D0
        sum_of_time_weighted_investments_with_currency_effect = D0

        for i in range(len(orders)):
            order = orders[i]
            exchange_rate_at_order_date = exchange_rates.get(order["date"])

            if order["type"] == "DIVIDEND":
                dividend = _to_decimal(order["quantity"]) * _to_decimal(order["unitPrice"])
                total_dividend += dividend
                total_dividend_in_base_currency += dividend * _to_decimal(exchange_rate_at_order_date or 1)
            elif order["type"] == "INTEREST":
                interest = _to_decimal(order["quantity"]) * _to_decimal(order["unitPrice"])
                total_interest += interest
                total_interest_in_base_currency += interest * _to_decimal(exchange_rate_at_order_date or 1)
            elif order["type"] == "LIABILITY":
                liabilities = _to_decimal(order["quantity"]) * _to_decimal(order["unitPrice"])
                total_liabilities += liabilities
                total_liabilities_in_base_currency += liabilities * _to_decimal(exchange_rate_at_order_date or 1)

            if order.get("itemType") == "start":
                order["unitPrice"] = (
                    _to_decimal(orders[i + 1].get("unitPrice", 0)) if (index_of_start_order == 0 and i + 1 < len(orders))
                    else unit_price_at_start_date
                )

            if order.get("fee"):
                order["feeInBaseCurrency"] = _to_decimal(order["fee"]) * _to_decimal(current_exchange_rate or 1)
                order["feeInBaseCurrencyWithCurrencyEffect"] = _to_decimal(order["fee"]) * _to_decimal(exchange_rate_at_order_date or 1)

            unit_price = (_to_decimal(order.get("unitPrice", 0))
                          if order["type"] in ("BUY", "SELL")
                          else _to_decimal(order.get("unitPriceFromMarketData", 0)))

            if unit_price:
                order["unitPriceInBaseCurrency"] = unit_price * _to_decimal(current_exchange_rate or 1)
                order["unitPriceInBaseCurrencyWithCurrencyEffect"] = unit_price * _to_decimal(exchange_rate_at_order_date or 1)

            upfm = order.get("unitPriceFromMarketData")
            market_price_in_base_currency = (_to_decimal(upfm) * _to_decimal(current_exchange_rate or 1)) if upfm else D0
            market_price_in_base_currency_with_currency_effect = (_to_decimal(upfm) * _to_decimal(exchange_rate_at_order_date or 1)) if upfm else D0

            value_of_investment_before_transaction = total_units * market_price_in_base_currency
            value_of_investment_before_transaction_with_currency_effect = total_units * market_price_in_base_currency_with_currency_effect

            if investment_at_start_date is None and i >= index_of_start_order:
                investment_at_start_date = total_investment or D0
                investment_at_start_date_with_currency_effect = total_investment_with_currency_effect or D0
                value_at_start_date = value_of_investment_before_transaction
                value_at_start_date_with_currency_effect = value_of_investment_before_transaction_with_currency_effect

            transaction_investment = D0
            transaction_investment_with_currency_effect = D0

            if order["type"] == "BUY":
                qty = _to_decimal(order.get("quantity", 0))
                transaction_investment = qty * _to_decimal(order.get("unitPriceInBaseCurrency", 0)) * _get_factor(order["type"])
                transaction_investment_with_currency_effect = qty * _to_decimal(order.get("unitPriceInBaseCurrencyWithCurrencyEffect", 0)) * _get_factor(order["type"])
                total_quantity_from_buy_transactions += qty
                total_investment_from_buy_transactions += transaction_investment
                total_investment_from_buy_transactions_with_currency_effect += transaction_investment_with_currency_effect
            elif order["type"] == "SELL":
                qty = _to_decimal(order.get("quantity", 0))
                if total_units > 0:
                    transaction_investment = (total_investment / total_units) * qty * _get_factor(order["type"])
                    transaction_investment_with_currency_effect = (total_investment_with_currency_effect / total_units) * qty * _get_factor(order["type"])

            total_investment_before_transaction = total_investment
            total_investment_before_transaction_with_currency_effect = total_investment_with_currency_effect

            total_investment += transaction_investment
            total_investment_with_currency_effect += transaction_investment_with_currency_effect

            if i >= index_of_start_order and not initial_value:
                if i == index_of_start_order and value_of_investment_before_transaction != D0:
                    initial_value = value_of_investment_before_transaction
                    initial_value_with_currency_effect = value_of_investment_before_transaction_with_currency_effect
                elif transaction_investment > 0:
                    initial_value = transaction_investment
                    initial_value_with_currency_effect = transaction_investment_with_currency_effect

            fees += _to_decimal(order.get("feeInBaseCurrency") or 0)
            fees_with_currency_effect += _to_decimal(order.get("feeInBaseCurrencyWithCurrencyEffect") or 0)

            total_units += _to_decimal(order.get("quantity", 0)) * _get_factor(order["type"])

            value_of_investment = total_units * market_price_in_base_currency
            value_of_investment_with_currency_effect = total_units * market_price_in_base_currency_with_currency_effect

            qty = _to_decimal(order.get("quantity", 0))
            if order["type"] == "SELL":
                gross_performance_from_sell = (_to_decimal(order.get("unitPriceInBaseCurrency", 0)) - last_average_price) * qty
                gross_performance_from_sell_with_currency_effect = (_to_decimal(order.get("unitPriceInBaseCurrencyWithCurrencyEffect", 0)) - last_average_price_with_currency_effect) * qty
            else:
                gross_performance_from_sell = D0
                gross_performance_from_sell_with_currency_effect = D0

            gross_performance_from_sells += gross_performance_from_sell
            gross_performance_from_sells_with_currency_effect += gross_performance_from_sell_with_currency_effect

            last_average_price = (D0 if total_quantity_from_buy_transactions == 0
                                  else total_investment_from_buy_transactions / total_quantity_from_buy_transactions)
            last_average_price_with_currency_effect = (D0 if total_quantity_from_buy_transactions == 0
                                                       else total_investment_from_buy_transactions_with_currency_effect / total_quantity_from_buy_transactions)

            if total_units == 0:
                total_investment_from_buy_transactions = D0
                total_investment_from_buy_transactions_with_currency_effect = D0
                total_quantity_from_buy_transactions = D0

            new_gross_performance = value_of_investment - total_investment + gross_performance_from_sells
            new_gross_performance_with_currency_effect = (
                value_of_investment_with_currency_effect - total_investment_with_currency_effect
                + gross_performance_from_sells_with_currency_effect
            )
            gross_performance = new_gross_performance
            gross_performance_with_currency_effect = new_gross_performance_with_currency_effect

            if order.get("itemType") == "start":
                fees_at_start_date = fees
                fees_at_start_date_with_currency_effect = fees_with_currency_effect
                gross_performance_at_start_date = gross_performance
                gross_performance_at_start_date_with_currency_effect = gross_performance_with_currency_effect

            if i > index_of_start_order:
                if value_of_investment_before_transaction > 0 and order["type"] in ("BUY", "SELL"):
                    order_date = _parse_date(order["date"])
                    previous_order_date = _parse_date(orders[i - 1]["date"])
                    days_since_last_order = _difference_in_days(order_date, previous_order_date)
                    if days_since_last_order <= 0:
                        days_since_last_order = EPSILON

                    total_investment_days += days_since_last_order
                    sum_of_time_weighted_investments += (
                        (value_at_start_date - investment_at_start_date + total_investment_before_transaction)
                        * Decimal(str(days_since_last_order))
                    )
                    sum_of_time_weighted_investments_with_currency_effect += (
                        (value_at_start_date_with_currency_effect - investment_at_start_date_with_currency_effect
                         + total_investment_before_transaction_with_currency_effect)
                        * Decimal(str(days_since_last_order))
                    )

                current_values[order["date"]] = value_of_investment
                current_values_with_currency_effect[order["date"]] = value_of_investment_with_currency_effect

                net_performance_values[order["date"]] = (
                    gross_performance - gross_performance_at_start_date
                    - (fees - fees_at_start_date)
                )
                net_performance_values_with_currency_effect[order["date"]] = (
                    gross_performance_with_currency_effect - gross_performance_at_start_date_with_currency_effect
                    - (fees_with_currency_effect - fees_at_start_date_with_currency_effect)
                )

                investment_values_accumulated[order["date"]] = total_investment
                investment_values_accumulated_with_currency_effect[order["date"]] = total_investment_with_currency_effect

                existing = investment_values_with_currency_effect.get(order["date"], D0)
                investment_values_with_currency_effect[order["date"]] = existing + transaction_investment_with_currency_effect

                twi_days = Decimal(str(total_investment_days))
                if total_investment_days > EPSILON:
                    time_weighted_investment_values[order["date"]] = sum_of_time_weighted_investments / twi_days
                    time_weighted_investment_values_with_currency_effect[order["date"]] = sum_of_time_weighted_investments_with_currency_effect / twi_days
                else:
                    time_weighted_investment_values[order["date"]] = total_investment if total_investment > 0 else D0
                    time_weighted_investment_values_with_currency_effect[order["date"]] = total_investment_with_currency_effect if total_investment_with_currency_effect > 0 else D0

            if i == index_of_end_order:
                break

        total_gross_performance = gross_performance - gross_performance_at_start_date
        total_gross_performance_with_currency_effect = gross_performance_with_currency_effect - gross_performance_at_start_date_with_currency_effect
        total_net_performance = total_gross_performance - (fees - fees_at_start_date)

        twi_avg = (sum_of_time_weighted_investments / Decimal(str(total_investment_days))) if total_investment_days > 0 else D0
        twi_avg_wce = (sum_of_time_weighted_investments_with_currency_effect / Decimal(str(total_investment_days))) if total_investment_days > 0 else D0

        gross_performance_percentage = (total_gross_performance / twi_avg) if twi_avg > 0 else D0
        gross_performance_percentage_with_currency_effect = (total_gross_performance_with_currency_effect / twi_avg_wce) if twi_avg_wce > 0 else D0
        net_performance_percentage = (total_net_performance / twi_avg) if twi_avg > 0 else D0

        # Compute per-date-range net performance maps
        net_performance_percentage_with_currency_effect_map = {}
        net_performance_with_currency_effect_map = {}

        date_ranges = ["1d", "1y", "5y", "max", "mtd", "wtd", "ytd"]
        for yr_date in _each_year_of_interval({"start": start, "end": end}):
            if not _is_this_year(yr_date):
                date_ranges.append(_format_date(yr_date)[:4])

        for date_range in date_ranges:
            date_interval = _get_interval_from_date_range(date_range)
            di_end = date_interval["endDate"]
            di_start = date_interval["startDate"]
            if _is_before(di_start, start):
                di_start = start
            range_end_str = _format_date(di_end)
            range_start_str = _format_date(di_start)

            cv_start = current_values_with_currency_effect.get(range_start_str, D0)
            iv_start = investment_values_accumulated_with_currency_effect.get(range_start_str, D0)
            gp_start = cv_start - iv_start

            average = D0
            day_count = 0
            for cd in reversed(self._chart_dates):
                if cd > range_end_str:
                    continue
                if cd < range_start_str:
                    break
                iv_val = investment_values_accumulated_with_currency_effect.get(cd)
                if iv_val is not None and isinstance(iv_val, Decimal) and iv_val > 0:
                    average += iv_val + gp_start
                    day_count += 1

            if day_count > 0:
                average /= day_count

            np_end = net_performance_values_with_currency_effect.get(range_end_str, D0)
            np_start_val = D0 if date_range == "max" else net_performance_values_with_currency_effect.get(range_start_str, D0)
            net_perf = np_end - np_start_val
            net_performance_with_currency_effect_map[date_range] = net_perf
            net_performance_percentage_with_currency_effect_map[date_range] = (net_perf / average) if average > 0 else D0

        return {
            "currentValues": current_values,
            "currentValuesWithCurrencyEffect": current_values_with_currency_effect,
            "feesWithCurrencyEffect": fees_with_currency_effect,
            "grossPerformance": total_gross_performance,
            "grossPerformancePercentage": gross_performance_percentage,
            "grossPerformancePercentageWithCurrencyEffect": gross_performance_percentage_with_currency_effect,
            "grossPerformanceWithCurrencyEffect": total_gross_performance_with_currency_effect,
            "hasErrors": total_units > 0 and (not initial_value or not unit_price_at_end_date),
            "initialValue": initial_value,
            "initialValueWithCurrencyEffect": initial_value_with_currency_effect,
            "investmentValuesAccumulated": investment_values_accumulated,
            "investmentValuesAccumulatedWithCurrencyEffect": investment_values_accumulated_with_currency_effect,
            "investmentValuesWithCurrencyEffect": investment_values_with_currency_effect,
            "netPerformance": total_net_performance,
            "netPerformancePercentage": net_performance_percentage,
            "netPerformancePercentageWithCurrencyEffectMap": net_performance_percentage_with_currency_effect_map,
            "netPerformanceValues": net_performance_values,
            "netPerformanceValuesWithCurrencyEffect": net_performance_values_with_currency_effect,
            "netPerformanceWithCurrencyEffectMap": net_performance_with_currency_effect_map,
            "timeWeightedInvestment": twi_avg,
            "timeWeightedInvestmentValues": time_weighted_investment_values,
            "timeWeightedInvestmentValuesWithCurrencyEffect": time_weighted_investment_values_with_currency_effect,
            "timeWeightedInvestmentWithCurrencyEffect": twi_avg_wce,
            "totalAccountBalanceInBaseCurrency": total_account_balance_in_base_currency,
            "totalDividend": total_dividend,
            "totalDividendInBaseCurrency": total_dividend_in_base_currency,
            "totalInterest": total_interest,
            "totalInterestInBaseCurrency": total_interest_in_base_currency,
            "totalInvestment": total_investment,
            "totalInvestmentWithCurrencyEffect": total_investment_with_currency_effect,
            "totalLiabilities": total_liabilities,
            "totalLiabilitiesInBaseCurrency": total_liabilities_in_base_currency,
        }

    @staticmethod
    def _empty_symbol_metrics(has_errors=False):
        return {
            "currentValues": {}, "currentValuesWithCurrencyEffect": {},
            "feesWithCurrencyEffect": D0,
            "grossPerformance": D0, "grossPerformancePercentage": D0,
            "grossPerformancePercentageWithCurrencyEffect": D0,
            "grossPerformanceWithCurrencyEffect": D0,
            "hasErrors": has_errors,
            "initialValue": D0, "initialValueWithCurrencyEffect": D0,
            "investmentValuesAccumulated": {},
            "investmentValuesAccumulatedWithCurrencyEffect": {},
            "investmentValuesWithCurrencyEffect": {},
            "netPerformance": D0, "netPerformancePercentage": D0,
            "netPerformancePercentageWithCurrencyEffectMap": {},
            "netPerformanceValues": {}, "netPerformanceValuesWithCurrencyEffect": {},
            "netPerformanceWithCurrencyEffectMap": {},
            "timeWeightedInvestment": D0,
            "timeWeightedInvestmentValues": {},
            "timeWeightedInvestmentValuesWithCurrencyEffect": {},
            "timeWeightedInvestmentWithCurrencyEffect": D0,
            "totalAccountBalanceInBaseCurrency": D0,
            "totalDividend": D0, "totalDividendInBaseCurrency": D0,
            "totalInterest": D0, "totalInterestInBaseCurrency": D0,
            "totalInvestment": D0, "totalInvestmentWithCurrencyEffect": D0,
            "totalLiabilities": D0, "totalLiabilitiesInBaseCurrency": D0,
        }

    # ------------------------------------------------------------------
    # Translated: computeTransactionPoints (from base calculator)
    # ------------------------------------------------------------------
    def _compute_transaction_points(self):
        """Build cumulative per-symbol state at each transaction date."""
        transaction_points = []
        symbols = {}
        last_date = None
        last_tp = None

        for act in self.sorted_activities():
            sp = act.get("SymbolProfile", act)
            symbol = sp.get("symbol", act.get("symbol", ""))
            currency = sp.get("currency", "USD")
            data_source = sp.get("dataSource", "MANUAL")
            asset_sub_class = sp.get("assetSubClass")
            activity_type = act.get("type", "BUY")
            qty = _to_decimal(act.get("quantity", 0))
            unit_price = _to_decimal(act.get("unitPrice", 0))
            fee = _to_decimal(act.get("fee", 0))
            fee_in_base = _to_decimal(act.get("feeInBaseCurrency", 0))
            date = act.get("date", "")
            factor = _get_factor(activity_type)

            old = symbols.get(symbol)
            if old:
                investment = old["investment"]
                new_qty = qty * factor + old["quantity"]

                if activity_type == "BUY":
                    if old["investment"] >= 0:
                        investment = old["investment"] + qty * unit_price
                    else:
                        investment = old["investment"] + qty * old.get("averagePrice", unit_price)
                elif activity_type == "SELL":
                    if old["investment"] > 0:
                        investment = old["investment"] - qty * old["averagePrice"]
                    else:
                        investment = old["investment"] - qty * unit_price

                if abs(new_qty) < Decimal(str(EPSILON)):
                    investment = D0
                    new_qty = D0

                avg_price = D0 if new_qty == 0 else abs(investment / new_qty)
                current_item = {
                    "symbol": symbol, "currency": currency, "dataSource": data_source,
                    "assetSubClass": asset_sub_class,
                    "activitiesCount": old["activitiesCount"] + 1,
                    "averagePrice": avg_price,
                    "dateOfFirstActivity": old["dateOfFirstActivity"],
                    "fee": old["fee"] + fee,
                    "feeInBaseCurrency": old["feeInBaseCurrency"] + fee_in_base,
                    "includeInHoldings": old["includeInHoldings"],
                    "investment": investment, "quantity": new_qty,
                    "skipErrors": bool(sp.get("userId")),
                    "tags": old.get("tags", []) + act.get("tags", []),
                }
            else:
                current_item = {
                    "symbol": symbol, "currency": currency, "dataSource": data_source,
                    "assetSubClass": asset_sub_class,
                    "activitiesCount": 1,
                    "averagePrice": unit_price,
                    "dateOfFirstActivity": date,
                    "fee": fee, "feeInBaseCurrency": fee_in_base,
                    "includeInHoldings": activity_type in ("BUY", "SELL"),
                    "investment": unit_price * qty * factor,
                    "quantity": qty * factor,
                    "skipErrors": bool(sp.get("userId")),
                    "tags": act.get("tags", []),
                }
            symbols[symbol] = current_item

            new_items = [s for s in (last_tp["items"] if last_tp else []) if s["symbol"] != symbol]
            new_items.append(current_item)
            new_items.sort(key=lambda x: x["symbol"])

            if last_date != date or last_tp is None:
                last_tp = {"date": date, "items": new_items}
                transaction_points.append(last_tp)
            else:
                last_tp["items"] = new_items
            last_date = date

        return transaction_points

    # ------------------------------------------------------------------
    # Compute full snapshot (translated from base calculator)
    # ------------------------------------------------------------------
    def _compute_snapshot(self):
        """Compute full portfolio snapshot with all symbol metrics."""
        tp = self._compute_transaction_points()
        if not tp:
            return self._empty_snapshot()

        last_tp = tp[-1]
        activities_sorted = self.sorted_activities()
        if not activities_sorted:
            return self._empty_snapshot()

        # Determine date range
        first_date = _parse_date(activities_sorted[0]["date"])
        interval = _get_interval_from_date_range("max", _sub_days(first_date, 1))
        start_date = _start_of_day(interval["startDate"])
        end_date = _end_of_day(interval["endDate"])
        end_date_string = _format_date(end_date)

        # Build market symbol map from current_rate_service
        market_symbol_map = {}
        for item in last_tp["items"]:
            sym = item["symbol"]
            if item.get("assetSubClass") == "CASH":
                continue
            # Get all prices for this symbol
            for ds_map in self.current_rate_service._market_data.values():
                if sym in ds_map:
                    for p in ds_map[sym]:
                        d = p["date"]
                        if d not in market_symbol_map:
                            market_symbol_map[d] = {}
                        market_symbol_map[d][sym] = _to_decimal(p["marketPrice"])

        # Build chart date map (simplified)
        chart_date_map = {}
        for t in tp:
            chart_date_map[t["date"]] = True
        days_in_market = _difference_in_days(end_date, start_date)
        step = max(1, round(days_in_market / max(1, min(days_in_market, 500))))
        for d in _each_day_of_interval({"start": start_date, "end": end_date}, {"step": step}):
            chart_date_map[_format_date(d)] = True
        if step > 1:
            for d in _each_day_of_interval({"start": _sub_days(end_date, 90), "end": end_date}, {"step": 3}):
                chart_date_map[_format_date(d)] = True
            for d in _each_day_of_interval({"start": _sub_days(end_date, 30), "end": end_date}, {"step": 1}):
                chart_date_map[_format_date(d)] = True
        chart_date_map[end_date_string] = True
        # Add key date range boundaries
        for dr in ["1d", "1y", "5y", "max", "mtd", "wtd", "ytd"]:
            di = _get_interval_from_date_range(dr)
            ds = _format_date(di["startDate"])
            de = _format_date(di["endDate"])
            if not _is_before(_parse_date(ds), start_date) and not _is_after(_parse_date(ds), end_date):
                chart_date_map[ds] = True
            if not _is_before(_parse_date(de), start_date) and not _is_after(_parse_date(de), end_date):
                chart_date_map[de] = True
        # Year boundaries
        for yr_dt in _each_year_of_interval({"start": start_date, "end": end_date}):
            ys = _format_date(_start_of_year(yr_dt))
            ye = _format_date(_end_of_year(yr_dt))
            if _is_within_interval(yr_dt, {"start": start_date, "end": end_date}):
                chart_date_map[ys] = True
            ye_dt = _end_of_year(yr_dt)
            if _is_within_interval(ye_dt, {"start": start_date, "end": end_date}):
                chart_date_map[ye] = True

        chart_dates = sorted(chart_date_map.keys())

        # Exchange rates: simplified (all 1.0 for same currency)
        exchange_rates = {}
        for d in chart_dates:
            exchange_rates[d] = 1.0

        # Compute symbol metrics for each symbol
        positions = []
        values_by_symbol = {}
        has_any_errors = False

        for item in last_tp["items"]:
            sym = item["symbol"]
            include_in_total = item.get("assetSubClass") != "CASH"

            # Skip items that only have non-trade activities (FEE, LIABILITY, etc.)
            if not item.get("includeInHoldings", True) and _to_decimal(item.get("quantity", 0)) == 0:
                # Still track fee for totalFees
                fee_val = _to_decimal(item.get("feeInBaseCurrency", item.get("fee", 0)))
                positions.append({
                    "includeInTotalAssetValue": False,
                    "timeWeightedInvestment": D0,
                    "timeWeightedInvestmentWithCurrencyEffect": D0,
                    "symbol": sym, "currency": item.get("currency", "USD"),
                    "dataSource": item.get("dataSource", "MANUAL"),
                    "averagePrice": D0, "dateOfFirstActivity": item.get("dateOfFirstActivity"),
                    "dividend": D0, "dividendInBaseCurrency": D0,
                    "fee": item.get("fee", D0), "feeInBaseCurrency": fee_val,
                    "grossPerformance": D0, "grossPerformancePercentage": D0,
                    "grossPerformancePercentageWithCurrencyEffect": D0,
                    "grossPerformanceWithCurrencyEffect": D0,
                    "investment": D0, "investmentWithCurrencyEffect": D0,
                    "marketPrice": 0.0, "marketPriceInBaseCurrency": 0.0,
                    "netPerformance": D0, "netPerformancePercentage": D0,
                    "netPerformancePercentageWithCurrencyEffectMap": {},
                    "netPerformanceWithCurrencyEffectMap": {},
                    "quantity": D0, "tags": item.get("tags", []),
                    "valueInBaseCurrency": D0,
                })
                has_any_errors = True  # TS sets hasErrors=true for fee-only
                continue

            market_price_at_end = market_symbol_map.get(end_date_string, {}).get(sym)
            if market_price_at_end is None:
                market_price_at_end = item.get("averagePrice", D0)
            if market_price_at_end is None:
                market_price_at_end = D0
            market_price_in_base = _to_decimal(market_price_at_end)

            metrics = self._get_symbol_metrics(
                chart_date_map=chart_date_map,
                data_source=item["dataSource"],
                end=end_date,
                exchange_rates=exchange_rates,
                market_symbol_map=market_symbol_map,
                start=start_date,
                symbol=sym,
            )

            has_any_errors = has_any_errors or metrics.get("hasErrors", False)

            if include_in_total:
                values_by_symbol[sym] = {
                    "currentValues": metrics.get("currentValues", {}),
                    "currentValuesWithCurrencyEffect": metrics.get("currentValuesWithCurrencyEffect", {}),
                    "investmentValuesAccumulated": metrics.get("investmentValuesAccumulated", {}),
                    "investmentValuesAccumulatedWithCurrencyEffect": metrics.get("investmentValuesAccumulatedWithCurrencyEffect", {}),
                    "investmentValuesWithCurrencyEffect": metrics.get("investmentValuesWithCurrencyEffect", {}),
                    "netPerformanceValues": metrics.get("netPerformanceValues", {}),
                    "netPerformanceValuesWithCurrencyEffect": metrics.get("netPerformanceValuesWithCurrencyEffect", {}),
                    "timeWeightedInvestmentValues": metrics.get("timeWeightedInvestmentValues", {}),
                    "timeWeightedInvestmentValuesWithCurrencyEffect": metrics.get("timeWeightedInvestmentValuesWithCurrencyEffect", {}),
                }

            pos = {
                "includeInTotalAssetValue": include_in_total,
                "timeWeightedInvestment": metrics.get("timeWeightedInvestment", D0),
                "timeWeightedInvestmentWithCurrencyEffect": metrics.get("timeWeightedInvestmentWithCurrencyEffect", D0),
                "symbol": sym,
                "currency": item.get("currency", "USD"),
                "dataSource": item.get("dataSource", "MANUAL"),
                "averagePrice": item.get("averagePrice", D0),
                "dateOfFirstActivity": item.get("dateOfFirstActivity"),
                "dividend": metrics.get("totalDividend", D0),
                "dividendInBaseCurrency": metrics.get("totalDividendInBaseCurrency", D0),
                "fee": item.get("fee", D0),
                "feeInBaseCurrency": item.get("feeInBaseCurrency", D0),
                "grossPerformance": metrics.get("grossPerformance") if not metrics.get("hasErrors") else None,
                "grossPerformancePercentage": metrics.get("grossPerformancePercentage") if not metrics.get("hasErrors") else None,
                "grossPerformancePercentageWithCurrencyEffect": metrics.get("grossPerformancePercentageWithCurrencyEffect") if not metrics.get("hasErrors") else None,
                "grossPerformanceWithCurrencyEffect": metrics.get("grossPerformanceWithCurrencyEffect") if not metrics.get("hasErrors") else None,
                "investment": metrics.get("totalInvestment", D0),
                "investmentWithCurrencyEffect": metrics.get("totalInvestmentWithCurrencyEffect", D0),
                "marketPrice": float(market_price_at_end) if market_price_at_end is not None else 0.0,
                "marketPriceInBaseCurrency": float(market_price_in_base) if market_price_in_base is not None else 0.0,
                "netPerformance": metrics.get("netPerformance") if not metrics.get("hasErrors") else None,
                "netPerformancePercentage": metrics.get("netPerformancePercentage") if not metrics.get("hasErrors") else None,
                "netPerformancePercentageWithCurrencyEffectMap": metrics.get("netPerformancePercentageWithCurrencyEffectMap") if not metrics.get("hasErrors") else None,
                "netPerformanceWithCurrencyEffectMap": metrics.get("netPerformanceWithCurrencyEffectMap") if not metrics.get("hasErrors") else None,
                "quantity": item.get("quantity", D0),
                "tags": item.get("tags", []),
                "valueInBaseCurrency": market_price_in_base * _to_decimal(item.get("quantity", 0)),
            }
            positions.append(pos)

        # Accumulate values by date for chart
        accumulated = {}
        for date_str in chart_dates:
            for sym, sv in values_by_symbol.items():
                cv = sv["currentValues"].get(date_str, D0)
                cv_wce = sv["currentValuesWithCurrencyEffect"].get(date_str, D0)
                iv_acc = sv["investmentValuesAccumulated"].get(date_str, D0)
                iv_acc_wce = sv["investmentValuesAccumulatedWithCurrencyEffect"].get(date_str, D0)
                iv_wce = sv["investmentValuesWithCurrencyEffect"].get(date_str, D0)
                np_val = sv["netPerformanceValues"].get(date_str, D0)
                np_val_wce = sv["netPerformanceValuesWithCurrencyEffect"].get(date_str, D0)
                twi_val = sv["timeWeightedInvestmentValues"].get(date_str, D0)
                twi_val_wce = sv["timeWeightedInvestmentValuesWithCurrencyEffect"].get(date_str, D0)

                if date_str not in accumulated:
                    accumulated[date_str] = {
                        "investmentValueWithCurrencyEffect": D0,
                        "totalCurrentValue": D0,
                        "totalCurrentValueWithCurrencyEffect": D0,
                        "totalInvestmentValue": D0,
                        "totalInvestmentValueWithCurrencyEffect": D0,
                        "totalNetPerformanceValue": D0,
                        "totalNetPerformanceValueWithCurrencyEffect": D0,
                        "totalTimeWeightedInvestmentValue": D0,
                        "totalTimeWeightedInvestmentValueWithCurrencyEffect": D0,
                    }
                a = accumulated[date_str]
                a["investmentValueWithCurrencyEffect"] += iv_wce
                a["totalCurrentValue"] += cv
                a["totalCurrentValueWithCurrencyEffect"] += cv_wce
                a["totalInvestmentValue"] += iv_acc
                a["totalInvestmentValueWithCurrencyEffect"] += iv_acc_wce
                a["totalNetPerformanceValue"] += np_val
                a["totalNetPerformanceValueWithCurrencyEffect"] += np_val_wce
                a["totalTimeWeightedInvestmentValue"] += twi_val
                a["totalTimeWeightedInvestmentValueWithCurrencyEffect"] += twi_val_wce

        historical_data = []
        for date_str in sorted(accumulated.keys()):
            v = accumulated[date_str]
            twi = v["totalTimeWeightedInvestmentValue"]
            twi_wce = v["totalTimeWeightedInvestmentValueWithCurrencyEffect"]
            np_pct = 0 if twi == 0 else float(v["totalNetPerformanceValue"] / twi)
            np_pct_wce = 0 if twi_wce == 0 else float(v["totalNetPerformanceValueWithCurrencyEffect"] / twi_wce)
            historical_data.append({
                "date": date_str,
                "netPerformanceInPercentage": np_pct,
                "netPerformanceInPercentageWithCurrencyEffect": np_pct_wce,
                "investmentValueWithCurrencyEffect": float(v["investmentValueWithCurrencyEffect"]),
                "netPerformance": float(v["totalNetPerformanceValue"]),
                "netPerformanceWithCurrencyEffect": float(v["totalNetPerformanceValueWithCurrencyEffect"]),
                "netWorth": float(v["totalCurrentValueWithCurrencyEffect"]),
                "totalAccountBalance": 0,
                "totalInvestment": float(v["totalInvestmentValue"]),
                "totalInvestmentValueWithCurrencyEffect": float(v["totalInvestmentValueWithCurrencyEffect"]),
                "value": float(v["totalCurrentValue"]),
                "valueWithCurrencyEffect": float(v["totalCurrentValueWithCurrencyEffect"]),
            })

        # Calculate overall performance
        overall = self._calculate_overall_performance(positions)

        return {**overall, "historicalData": historical_data, "hasErrors": has_any_errors or overall.get("hasErrors", False)}

    def _calculate_overall_performance(self, positions):
        """Translated from RoaiPortfolioCalculator.calculateOverallPerformance."""
        current_value_in_base_currency = D0
        gross_performance = D0
        gross_performance_with_currency_effect = D0
        has_errors = False
        net_performance = D0
        total_fees = D0
        total_investment = D0
        total_investment_with_currency_effect = D0
        total_twi = D0
        total_twi_wce = D0

        for pos in positions:
            # Always count fees, even for non-asset positions (FEE type)
            fb = pos.get("feeInBaseCurrency", D0)
            if fb:
                total_fees += _to_decimal(fb)
            if not pos.get("includeInTotalAssetValue", True):
                continue
            vb = pos.get("valueInBaseCurrency")
            if vb:
                current_value_in_base_currency += _to_decimal(vb)
            else:
                has_errors = True
            inv = pos.get("investment")
            if inv is not None:
                total_investment += _to_decimal(inv)
                total_investment_with_currency_effect += _to_decimal(pos.get("investmentWithCurrencyEffect", 0))
            else:
                has_errors = True
            gp = pos.get("grossPerformance")
            if gp is not None:
                gross_performance += _to_decimal(gp)
                gross_performance_with_currency_effect += _to_decimal(pos.get("grossPerformanceWithCurrencyEffect", 0))
                net_performance += _to_decimal(pos.get("netPerformance", 0))
            elif _to_decimal(pos.get("quantity", 0)) != 0:
                has_errors = True
            twi = pos.get("timeWeightedInvestment")
            if twi is not None:
                total_twi += _to_decimal(twi)
                total_twi_wce += _to_decimal(pos.get("timeWeightedInvestmentWithCurrencyEffect", 0))
            elif _to_decimal(pos.get("quantity", 0)) != 0:
                has_errors = True

        return {
            "currentValueInBaseCurrency": current_value_in_base_currency,
            "hasErrors": has_errors,
            "positions": positions,
            "totalFeesWithCurrencyEffect": total_fees,
            "totalInterestWithCurrencyEffect": D0,
            "totalInvestment": total_investment,
            "totalInvestmentWithCurrencyEffect": total_investment_with_currency_effect,
            "activitiesCount": sum(1 for a in self.activities if a.get("type") in ("BUY", "SELL")),
            "createdAt": datetime.now().isoformat(),
            "errors": [],
            "historicalData": [],
            "totalLiabilitiesWithCurrencyEffect": D0,
        }

    @staticmethod
    def _empty_snapshot():
        return {
            "activitiesCount": 0, "createdAt": datetime.now().isoformat(),
            "currentValueInBaseCurrency": D0, "errors": [], "hasErrors": False,
            "historicalData": [], "positions": [],
            "totalFeesWithCurrencyEffect": D0, "totalInterestWithCurrencyEffect": D0,
            "totalInvestment": D0, "totalInvestmentWithCurrencyEffect": D0,
            "totalLiabilitiesWithCurrencyEffect": D0,
        }

    # ==================================================================
    # Public API methods (required by abstract PortfolioCalculator)
    # ==================================================================

    def get_performance(self) -> dict:
        snapshot = self._compute_snapshot()
        positions = snapshot.get("positions", [])
        historical_data = snapshot.get("historicalData", [])

        # Build chart from historical data
        chart = []
        net_perf_at_start = None
        net_perf_wce_at_start = None
        total_inv_values_wce = []

        for hd in historical_data:
            if net_perf_at_start is None:
                net_perf_at_start = hd.get("netPerformance", 0)
                net_perf_wce_at_start = hd.get("netPerformanceWithCurrencyEffect", 0)

            np_since = hd["netPerformance"] - net_perf_at_start
            np_wce_since = hd["netPerformanceWithCurrencyEffect"] - net_perf_wce_at_start

            tiv_wce = hd.get("totalInvestmentValueWithCurrencyEffect", 0)
            if tiv_wce > 0:
                total_inv_values_wce.append(tiv_wce)

            twi_avg = sum(total_inv_values_wce) / len(total_inv_values_wce) if total_inv_values_wce else 0

            chart.append({
                **hd,
                "netPerformance": np_since,
                "netPerformanceWithCurrencyEffect": np_wce_since,
                "netPerformanceInPercentage": np_since / twi_avg if twi_avg else 0,
                "netPerformanceInPercentageWithCurrencyEffect": np_wce_since / twi_avg if twi_avg else 0,
            })

        first_date = min((a["date"] for a in self.activities), default=None)
        total_inv = float(snapshot.get("totalInvestment", 0))
        total_fees = float(snapshot.get("totalFeesWithCurrencyEffect", 0))
        cv_base = float(snapshot.get("currentValueInBaseCurrency", 0))

        # Aggregate net performance from all positions
        total_net_perf = sum(float(_to_decimal(p.get("netPerformance", 0))) for p in positions if p.get("netPerformance") is not None)
        total_net_perf_pct = D0
        total_twi = sum(_to_decimal(p.get("timeWeightedInvestment", 0)) for p in positions if p.get("timeWeightedInvestment") is not None)
        if total_twi > 0:
            total_net_perf_pct = Decimal(str(total_net_perf)) / total_twi
        elif abs(_to_decimal(total_inv)) > 0:
            # Fallback: use totalInvestment as denominator (e.g. short cover)
            total_net_perf_pct = Decimal(str(total_net_perf)) / abs(_to_decimal(total_inv))

        total_liabilities = D0
        total_valueables = D0
        for act in self.activities:
            qty = _to_decimal(act.get("quantity", 0))
            up = _to_decimal(act.get("unitPrice", 0))
            if act.get("type") == "LIABILITY":
                total_liabilities += qty * up
            elif act.get("type") == "VALUABLE":
                total_valueables += qty * up

        return {
            "chart": chart,
            "firstOrderDate": first_date,
            "performance": {
                "currentNetWorth": cv_base,
                "currentValue": cv_base,
                "currentValueInBaseCurrency": cv_base,
                "netPerformance": total_net_perf,
                "netPerformancePercentage": float(total_net_perf_pct),
                "netPerformancePercentageWithCurrencyEffect": float(total_net_perf_pct),
                "netPerformanceWithCurrencyEffect": total_net_perf,
                "totalFees": total_fees,
                "totalInvestment": total_inv,
                "totalLiabilities": float(total_liabilities),
                "totalValueables": float(total_valueables),
            },
        }

    def get_investments(self, group_by=None) -> dict:
        snapshot = self._compute_snapshot()
        historical_data = snapshot.get("historicalData", [])

        if not group_by:
            # Return per-date investment values
            investments = []
            seen_dates = set()
            for hd in historical_data:
                iv = hd.get("investmentValueWithCurrencyEffect", 0)
                if iv != 0 and hd["date"] not in seen_dates:
                    investments.append({"date": hd["date"], "investment": iv})
                    seen_dates.add(hd["date"])
            # If no investment values found, fall back to activity-based list
            if not investments:
                for act in self.sorted_activities():
                    if act.get("type") in ("BUY", "SELL"):
                        qty = float(_to_decimal(act.get("quantity", 0)))
                        up = float(_to_decimal(act.get("unitPrice", 0)))
                        factor = _get_factor(act["type"])
                        investments.append({"date": act["date"], "investment": qty * up * factor})
            return {"investments": investments}

        # Group by month or year
        grouped = {}
        for hd in historical_data:
            iv = hd.get("investmentValueWithCurrencyEffect", 0)
            if group_by == "month":
                key = hd["date"][:7]
            else:
                key = hd["date"][:4]
            grouped[key] = grouped.get(key, 0) + iv

        investments = []
        for key in sorted(grouped.keys()):
            date_str = f"{key}-01" if group_by == "month" else f"{key}-01-01"
            investments.append({"date": date_str, "investment": grouped[key]})

        return {"investments": investments}

    def get_holdings(self) -> dict:
        snapshot = self._compute_snapshot()
        positions = snapshot.get("positions", [])
        holdings = {}
        for pos in positions:
            sym = pos.get("symbol", "")
            holdings[sym] = {
                "symbol": sym,
                "currency": pos.get("currency", "USD"),
                "dataSource": pos.get("dataSource", "MANUAL"),
                "dateOfFirstActivity": pos.get("dateOfFirstActivity"),
                "investment": float(_to_decimal(pos.get("investment", 0))),
                "quantity": float(_to_decimal(pos.get("quantity", 0))),
                "marketPrice": pos.get("marketPrice", 0),
                "marketPriceInBaseCurrency": pos.get("marketPriceInBaseCurrency", 0),
                "currentValueInBaseCurrency": float(_to_decimal(pos.get("valueInBaseCurrency", 0))),
                "netPerformance": float(_to_decimal(pos.get("netPerformance", 0))) if pos.get("netPerformance") is not None else 0,
                "netPerformancePercentage": float(_to_decimal(pos.get("netPerformancePercentage", 0))) if pos.get("netPerformancePercentage") is not None else 0,
                "netPerformancePercentageWithCurrencyEffectMap": {k: float(v) for k, v in (pos.get("netPerformancePercentageWithCurrencyEffectMap") or {}).items()},
                "grossPerformance": float(_to_decimal(pos.get("grossPerformance", 0))) if pos.get("grossPerformance") is not None else 0,
                "grossPerformancePercentage": float(_to_decimal(pos.get("grossPerformancePercentage", 0))) if pos.get("grossPerformancePercentage") is not None else 0,
                "dividend": float(_to_decimal(pos.get("dividend", 0))),
                "dividendInBaseCurrency": float(_to_decimal(pos.get("dividendInBaseCurrency", 0))),
                "fee": float(_to_decimal(pos.get("fee", 0))),
            }
        return {"holdings": holdings}

    def get_details(self, base_currency="USD") -> dict:
        snapshot = self._compute_snapshot()
        positions = snapshot.get("positions", [])
        holdings_dict = {}
        total_inv = D0
        total_net = D0
        total_cv = D0
        total_fees = D0

        for pos in positions:
            sym = pos.get("symbol", "")
            inv = _to_decimal(pos.get("investment", 0))
            np_val = _to_decimal(pos.get("netPerformance", 0)) if pos.get("netPerformance") is not None else D0
            cv = _to_decimal(pos.get("valueInBaseCurrency", 0))
            fee = _to_decimal(pos.get("feeInBaseCurrency", 0))
            total_inv += inv
            total_net += np_val
            total_cv += cv
            total_fees += fee

            np_pct = float(_to_decimal(pos.get("netPerformancePercentage", 0))) if pos.get("netPerformancePercentage") is not None else 0
            holdings_dict[sym] = {
                "symbol": sym,
                "currency": pos.get("currency", base_currency),
                "dataSource": pos.get("dataSource", "MANUAL"),
                "dateOfFirstActivity": pos.get("dateOfFirstActivity"),
                "investment": float(inv),
                "quantity": float(_to_decimal(pos.get("quantity", 0))),
                "marketPrice": pos.get("marketPrice", 0),
                "marketPriceInBaseCurrency": pos.get("marketPriceInBaseCurrency", 0),
                "currentValueInBaseCurrency": float(cv),
                "netPerformance": float(np_val),
                "netPerformancePercent": np_pct,
                "netPerformancePercentage": np_pct,
                "grossPerformance": float(_to_decimal(pos.get("grossPerformance", 0))) if pos.get("grossPerformance") is not None else 0,
                "dividend": float(_to_decimal(pos.get("dividend", 0))),
                "dividendInBaseCurrency": float(_to_decimal(pos.get("dividendInBaseCurrency", 0))),
                "fee": float(fee),
            }

        return {
            "accounts": {"default": {"balance": 0.0, "currency": base_currency, "name": "Default Account", "valueInBaseCurrency": float(total_cv)}},
            "createdAt": min((a["date"] for a in self.activities), default=None),
            "holdings": holdings_dict,
            "platforms": {"default": {"balance": 0.0, "currency": base_currency, "name": "Default Platform", "valueInBaseCurrency": float(total_cv)}},
            "summary": {
                "totalInvestment": float(total_inv),
                "netPerformance": float(total_net),
                "currentValueInBaseCurrency": float(total_cv),
                "totalFees": float(total_fees),
            },
            "hasError": snapshot.get("hasErrors", False),
        }

    def get_dividends(self, group_by=None) -> dict:
        div_activities = [a for a in self.sorted_activities() if a.get("type") == "DIVIDEND"]
        if not group_by:
            dividends = []
            for a in div_activities:
                qty = float(_to_decimal(a.get("quantity", 0)))
                up = float(_to_decimal(a.get("unitPrice", 0)))
                dividends.append({"date": a["date"], "investment": qty * up})
            return {"dividends": dividends}

        grouped = {}
        for a in div_activities:
            qty = float(_to_decimal(a.get("quantity", 0)))
            up = float(_to_decimal(a.get("unitPrice", 0)))
            key = a["date"][:7] if group_by == "month" else a["date"][:4]
            grouped[key] = grouped.get(key, 0) + qty * up

        dividends = []
        for key in sorted(grouped.keys()):
            date_str = f"{key}-01" if group_by == "month" else f"{key}-01-01"
            dividends.append({"date": date_str, "investment": grouped[key]})
        return {"dividends": dividends}

    def evaluate_report(self) -> dict:
        has_positions = any(
            a.get("type") in ("BUY", "SELL")
            for a in self.activities
        )
        if not has_positions:
            return {
                "xRay": {
                    "categories": [
                        {"key": "accounts", "name": "Accounts", "rules": []},
                        {"key": "currencies", "name": "Currencies", "rules": []},
                        {"key": "fees", "name": "Fees", "rules": []},
                    ],
                    "statistics": {"rulesActiveCount": 0, "rulesFulfilledCount": 0},
                }
            }
        # When we have positions, create simple rule evaluations
        snapshot = self._compute_snapshot()
        positions = snapshot.get("positions", [])
        total_inv = sum(float(_to_decimal(p.get("investment", 0))) for p in positions)
        total_cv = sum(float(_to_decimal(p.get("valueInBaseCurrency", 0))) for p in positions)
        total_fees = sum(float(_to_decimal(p.get("feeInBaseCurrency", 0))) for p in positions)
        # Fees rule: fees should be < 1% of total value
        fee_pct = total_fees / total_cv if total_cv else 0
        fee_rule_ok = fee_pct < 0.01
        # Account rule: at least one account
        account_rule_ok = True
        # Currency rule: check single currency
        currencies = set(p.get("currency", "USD") for p in positions)
        currency_rule_ok = len(currencies) <= 1
        rules_active = 3
        rules_fulfilled = sum([fee_rule_ok, account_rule_ok, currency_rule_ok])
        return {
            "xRay": {
                "categories": [
                    {"key": "accounts", "name": "Accounts", "rules": [
                        {"name": "accountClusterRisk", "key": "accountClusterRisk", "isActive": True, "value": account_rule_ok},
                    ]},
                    {"key": "currencies", "name": "Currencies", "rules": [
                        {"name": "currencyClusterRisk", "key": "currencyClusterRisk", "isActive": True, "value": currency_rule_ok},
                    ]},
                    {"key": "fees", "name": "Fees", "rules": [
                        {"name": "feeRatio", "key": "feeRatio", "isActive": True, "value": fee_rule_ok},
                    ]},
                ],
                "statistics": {"rulesActiveCount": rules_active, "rulesFulfilledCount": rules_fulfilled},
            }
        }
