"""Translated from TypeScript by tt — tree-sitter AST pipeline."""
from __future__ import annotations
from .runtime_helpers import *
from app.wrapper.portfolio.calculator.portfolio_calculator import PortfolioCalculator

class _TxBase:

    def __init__(self, activities=None, current_rate_service=None, **_kw):
        _init_calculator(self, activities, current_rate_service, **_kw)

    def compute_snapshot(self):
        last_transaction_point = self.transaction_points[(-1)]
        transaction_points = [_x for _x in self.transaction_points if (lambda date: _is_before(_parse_date(date), self.end_date))(_x)]
        if (not len(transaction_points)):
            return {'activitiesCount': 0, 'createdAt': datetime.now(), 'currentValueInBaseCurrency': Decimal('0'), 'errors': [], 'hasErrors': False, 'historicalData': [], 'positions': [], 'totalFeesWithCurrencyEffect': Decimal('0'), 'totalInterestWithCurrencyEffect': Decimal('0'), 'totalInvestment': Decimal('0'), 'totalInvestmentWithCurrencyEffect': Decimal('0'), 'totalLiabilitiesWithCurrencyEffect': Decimal('0')}
        currencies = {}
        data_gathering_items = []
        first_index = len(transaction_points)
        first_transaction_point = None
        total_interest_with_currency_effect = Decimal('0')
        total_liabilities_with_currency_effect = Decimal('0')
        for asset_sub_class, currency, data_source, symbol in transaction_points[(first_index - 1)].items:
            # Gather data for all assets except CASH
            if (asset_sub_class != 'CASH'):
                data_gathering_items.append({'dataSource': data_source, 'symbol': symbol})
            currencies[symbol] = currency
        for i in range(len(transaction_points)):
            if ((not _is_before(_parse_date(transaction_points[i].date), self.start_date)) and (first_transaction_point == None)):
                first_transaction_point = transaction_points[i]
                first_index = i
        exchange_rates_by_currency = self.exchange_rate_data_service.get_exchange_rates_by_currency({'currencies': list(set(list(currencies.values()))), 'endDate': self.end_date, 'startDate': self.start_date, 'targetCurrency': self.currency})
        data_provider_infos = self.current_rate_service.get_values({'dataGatheringItems': data_gathering_items, 'dateQuery': {'gte': self.start_date, 'lt': self.end_date}})['dataProviderInfos']
        current_rate_errors = self.current_rate_service.get_values({'dataGatheringItems': data_gathering_items, 'dateQuery': {'gte': self.start_date, 'lt': self.end_date}})['currentRateErrors']
        market_symbols = self.current_rate_service.get_values({'dataGatheringItems': data_gathering_items, 'dateQuery': {'gte': self.start_date, 'lt': self.end_date}})['marketSymbols']
        self.data_provider_infos = data_provider_infos
        market_symbol_map = {}
        for market_symbol in market_symbols:
            date = _format_date(market_symbol.date, DATE_FORMAT)
            if (not market_symbol_map[date]):
                market_symbol_map[date] = {}
            if (market_symbol.get('marketPrice') if isinstance(market_symbol, dict) else market_symbol.market_price):
                market_symbol_map[date][market_symbol.symbol] = Decimal(str((market_symbol.get('marketPrice') if isinstance(market_symbol, dict) else market_symbol.market_price)))
        end_date_string = _format_date(self.end_date, DATE_FORMAT)
        days_in_market = _difference_in_days(self.end_date, self.start_date)
        chart_date_map = self.get_chart_date_map({'endDate': self.end_date, 'startDate': self.start_date, 'step': round((days_in_market / min(days_in_market, self.configuration_service.get('MAX_CHART_ITEMS'))))})
        for account_balance_item in self.account_balance_items:
            chart_date_map[account_balance_item.date] = True
        chart_dates = sorted(list(chart_date_map.keys()), key=lambda chart_date: chart_date)
        if (first_index > 0):
            first_index -= 1
        errors = []
        has_any_symbol_metrics_errors = False
        positions = []
        accumulated_values_by_date = {}
        values_by_symbol = {}
        for item in last_transaction_point.items:
            market_price_in_base_currency = ((((market_symbol_map[end_date_string][item.symbol] if market_symbol_map[end_date_string] is not None else None) if (market_symbol_map[end_date_string][item.symbol] if market_symbol_map[end_date_string] is not None else None) is not None else (item.get('averagePrice') if isinstance(item, dict) else item.average_price))) * ((exchange_rates_by_currency[f"{item.currency}{self.currency}"][end_date_string] if exchange_rates_by_currency[f"{item.currency}{self.currency}"] is not None else None) if (exchange_rates_by_currency[f"{item.currency}{self.currency}"][end_date_string] if exchange_rates_by_currency[f"{item.currency}{self.currency}"] is not None else None) is not None else 1))
            current_values = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['currentValues']
            current_values_with_currency_effect = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['currentValuesWithCurrencyEffect']
            gross_performance = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['grossPerformance']
            gross_performance_percentage = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['grossPerformancePercentage']
            gross_performance_percentage_with_currency_effect = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['grossPerformancePercentageWithCurrencyEffect']
            gross_performance_with_currency_effect = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['grossPerformanceWithCurrencyEffect']
            has_errors = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['hasErrors']
            investment_values_accumulated = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['investmentValuesAccumulated']
            investment_values_accumulated_with_currency_effect = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['investmentValuesAccumulatedWithCurrencyEffect']
            investment_values_with_currency_effect = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['investmentValuesWithCurrencyEffect']
            net_performance = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['netPerformance']
            net_performance_percentage = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['netPerformancePercentage']
            net_performance_percentage_with_currency_effect_map = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['netPerformancePercentageWithCurrencyEffectMap']
            net_performance_values = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['netPerformanceValues']
            net_performance_values_with_currency_effect = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['netPerformanceValuesWithCurrencyEffect']
            net_performance_with_currency_effect_map = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['netPerformanceWithCurrencyEffectMap']
            time_weighted_investment = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['timeWeightedInvestment']
            time_weighted_investment_values = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['timeWeightedInvestmentValues']
            time_weighted_investment_values_with_currency_effect = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['timeWeightedInvestmentValuesWithCurrencyEffect']
            time_weighted_investment_with_currency_effect = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['timeWeightedInvestmentWithCurrencyEffect']
            total_dividend = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['totalDividend']
            total_dividend_in_base_currency = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['totalDividendInBaseCurrency']
            total_interest_in_base_currency = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['totalInterestInBaseCurrency']
            total_investment = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['totalInvestment']
            total_investment_with_currency_effect = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['totalInvestmentWithCurrencyEffect']
            total_liabilities_in_base_currency = self.get_symbol_metrics({'chartDateMap': chart_date_map, 'marketSymbolMap': market_symbol_map, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'end': self.end_date, 'exchangeRates': exchange_rates_by_currency[f"{item.currency}{self.currency}"], 'start': self.start_date, 'symbol': item.symbol})['totalLiabilitiesInBaseCurrency']
            has_any_symbol_metrics_errors = (has_any_symbol_metrics_errors or has_errors)
            include_in_total_asset_value = ((item.get('assetSubClass') if isinstance(item, dict) else item.asset_sub_class) != asset_sub_class.CASH)
            if include_in_total_asset_value:
                values_by_symbol[item.symbol] = {'currentValues': current_values, 'currentValuesWithCurrencyEffect': current_values_with_currency_effect, 'investmentValuesAccumulated': investment_values_accumulated, 'investmentValuesAccumulatedWithCurrencyEffect': investment_values_accumulated_with_currency_effect, 'investmentValuesWithCurrencyEffect': investment_values_with_currency_effect, 'netPerformanceValues': net_performance_values, 'netPerformanceValuesWithCurrencyEffect': net_performance_values_with_currency_effect, 'timeWeightedInvestmentValues': time_weighted_investment_values, 'timeWeightedInvestmentValuesWithCurrencyEffect': time_weighted_investment_values_with_currency_effect}
            positions.append({'includeInTotalAssetValue': include_in_total_asset_value, 'timeWeightedInvestment': time_weighted_investment, 'timeWeightedInvestmentWithCurrencyEffect': time_weighted_investment_with_currency_effect, 'activitiesCount': (item.get('activitiesCount') if isinstance(item, dict) else item.activities_count), 'averagePrice': (item.get('averagePrice') if isinstance(item, dict) else item.average_price), 'currency': item.currency, 'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'dateOfFirstActivity': (item.get('dateOfFirstActivity') if isinstance(item, dict) else item.date_of_first_activity), 'dividend': total_dividend, 'dividendInBaseCurrency': total_dividend_in_base_currency, 'fee': item.fee, 'feeInBaseCurrency': (item.get('feeInBaseCurrency') if isinstance(item, dict) else item.fee_in_base_currency), 'grossPerformance': (((gross_performance if gross_performance is not None else None)) if (not has_errors) else None), 'grossPerformancePercentage': (((gross_performance_percentage if gross_performance_percentage is not None else None)) if (not has_errors) else None), 'grossPerformancePercentageWithCurrencyEffect': (((gross_performance_percentage_with_currency_effect if gross_performance_percentage_with_currency_effect is not None else None)) if (not has_errors) else None), 'grossPerformanceWithCurrencyEffect': (((gross_performance_with_currency_effect if gross_performance_with_currency_effect is not None else None)) if (not has_errors) else None), 'includeInHoldings': (item.get('includeInHoldings') if isinstance(item, dict) else item.include_in_holdings), 'investment': total_investment, 'investmentWithCurrencyEffect': total_investment_with_currency_effect, 'marketPrice': (float((market_symbol_map[end_date_string][item.symbol] if market_symbol_map[end_date_string] is not None else None)) if float((market_symbol_map[end_date_string][item.symbol] if market_symbol_map[end_date_string] is not None else None)) is not None else 1), 'marketPriceInBaseCurrency': (float(market_price_in_base_currency) if float(market_price_in_base_currency) is not None else 1), 'netPerformance': (((net_performance if net_performance is not None else None)) if (not has_errors) else None), 'netPerformancePercentage': (((net_performance_percentage if net_performance_percentage is not None else None)) if (not has_errors) else None), 'netPerformancePercentageWithCurrencyEffectMap': (((net_performance_percentage_with_currency_effect_map if net_performance_percentage_with_currency_effect_map is not None else None)) if (not has_errors) else None), 'netPerformanceWithCurrencyEffectMap': (((net_performance_with_currency_effect_map if net_performance_with_currency_effect_map is not None else None)) if (not has_errors) else None), 'quantity': item.quantity, 'symbol': item.symbol, 'tags': item.tags, 'valueInBaseCurrency': (Decimal(str(market_price_in_base_currency)) * item.quantity)})
            total_interest_with_currency_effect = (total_interest_with_currency_effect + total_interest_in_base_currency)
            total_liabilities_with_currency_effect = (total_liabilities_with_currency_effect + total_liabilities_in_base_currency)
            if ((((has_errors or next((_x for _x in current_rate_errors if (lambda data_source, symbol: ((data_source == (item.get('dataSource') if isinstance(item, dict) else item.data_source)) and (symbol == item.symbol)))(_x)), None))) and (item.investment > 0)) and ((item.get('skipErrors') if isinstance(item, dict) else item.skip_errors) == False)):
                errors.append({'dataSource': (item.get('dataSource') if isinstance(item, dict) else item.data_source), 'symbol': item.symbol})
        account_balance_items_map = _reduce(self.account_balance_items, lambda map, date, value: None, {})
        account_balance_map = {}
        last_known_balance = Decimal('0')
        for date_string in chart_dates:
            if (account_balance_items_map[date_string] != None):
                # If there's an exact balance for this date, update lastKnownBalance
                last_known_balance = account_balance_items_map[date_string]
            # Add the most recent balance to the accountBalanceMap
            account_balance_map[date_string] = last_known_balance
            for symbol in list(values_by_symbol.keys()):
                symbol_values = values_by_symbol[symbol]
                current_value = (((symbol_values.get('currentValues') if isinstance(symbol_values, dict) else symbol_values.current_values)[date_string] if (symbol_values.get('currentValues') if isinstance(symbol_values, dict) else symbol_values.current_values) is not None else None) if ((symbol_values.get('currentValues') if isinstance(symbol_values, dict) else symbol_values.current_values)[date_string] if (symbol_values.get('currentValues') if isinstance(symbol_values, dict) else symbol_values.current_values) is not None else None) is not None else Decimal('0'))
                current_value_with_currency_effect = (((symbol_values.get('currentValuesWithCurrencyEffect') if isinstance(symbol_values, dict) else symbol_values.current_values_with_currency_effect)[date_string] if (symbol_values.get('currentValuesWithCurrencyEffect') if isinstance(symbol_values, dict) else symbol_values.current_values_with_currency_effect) is not None else None) if ((symbol_values.get('currentValuesWithCurrencyEffect') if isinstance(symbol_values, dict) else symbol_values.current_values_with_currency_effect)[date_string] if (symbol_values.get('currentValuesWithCurrencyEffect') if isinstance(symbol_values, dict) else symbol_values.current_values_with_currency_effect) is not None else None) is not None else Decimal('0'))
                investment_value_accumulated = (((symbol_values.get('investmentValuesAccumulated') if isinstance(symbol_values, dict) else symbol_values.investment_values_accumulated)[date_string] if (symbol_values.get('investmentValuesAccumulated') if isinstance(symbol_values, dict) else symbol_values.investment_values_accumulated) is not None else None) if ((symbol_values.get('investmentValuesAccumulated') if isinstance(symbol_values, dict) else symbol_values.investment_values_accumulated)[date_string] if (symbol_values.get('investmentValuesAccumulated') if isinstance(symbol_values, dict) else symbol_values.investment_values_accumulated) is not None else None) is not None else Decimal('0'))
                investment_value_accumulated_with_currency_effect = (((symbol_values.get('investmentValuesAccumulatedWithCurrencyEffect') if isinstance(symbol_values, dict) else symbol_values.investment_values_accumulated_with_currency_effect)[date_string] if (symbol_values.get('investmentValuesAccumulatedWithCurrencyEffect') if isinstance(symbol_values, dict) else symbol_values.investment_values_accumulated_with_currency_effect) is not None else None) if ((symbol_values.get('investmentValuesAccumulatedWithCurrencyEffect') if isinstance(symbol_values, dict) else symbol_values.investment_values_accumulated_with_currency_effect)[date_string] if (symbol_values.get('investmentValuesAccumulatedWithCurrencyEffect') if isinstance(symbol_values, dict) else symbol_values.investment_values_accumulated_with_currency_effect) is not None else None) is not None else Decimal('0'))
                investment_value_with_currency_effect = (((symbol_values.get('investmentValuesWithCurrencyEffect') if isinstance(symbol_values, dict) else symbol_values.investment_values_with_currency_effect)[date_string] if (symbol_values.get('investmentValuesWithCurrencyEffect') if isinstance(symbol_values, dict) else symbol_values.investment_values_with_currency_effect) is not None else None) if ((symbol_values.get('investmentValuesWithCurrencyEffect') if isinstance(symbol_values, dict) else symbol_values.investment_values_with_currency_effect)[date_string] if (symbol_values.get('investmentValuesWithCurrencyEffect') if isinstance(symbol_values, dict) else symbol_values.investment_values_with_currency_effect) is not None else None) is not None else Decimal('0'))
                net_performance_value = (((symbol_values.get('netPerformanceValues') if isinstance(symbol_values, dict) else symbol_values.net_performance_values)[date_string] if (symbol_values.get('netPerformanceValues') if isinstance(symbol_values, dict) else symbol_values.net_performance_values) is not None else None) if ((symbol_values.get('netPerformanceValues') if isinstance(symbol_values, dict) else symbol_values.net_performance_values)[date_string] if (symbol_values.get('netPerformanceValues') if isinstance(symbol_values, dict) else symbol_values.net_performance_values) is not None else None) is not None else Decimal('0'))
                net_performance_value_with_currency_effect = (((symbol_values.get('netPerformanceValuesWithCurrencyEffect') if isinstance(symbol_values, dict) else symbol_values.net_performance_values_with_currency_effect)[date_string] if (symbol_values.get('netPerformanceValuesWithCurrencyEffect') if isinstance(symbol_values, dict) else symbol_values.net_performance_values_with_currency_effect) is not None else None) if ((symbol_values.get('netPerformanceValuesWithCurrencyEffect') if isinstance(symbol_values, dict) else symbol_values.net_performance_values_with_currency_effect)[date_string] if (symbol_values.get('netPerformanceValuesWithCurrencyEffect') if isinstance(symbol_values, dict) else symbol_values.net_performance_values_with_currency_effect) is not None else None) is not None else Decimal('0'))
                time_weighted_investment_value = (((symbol_values.get('timeWeightedInvestmentValues') if isinstance(symbol_values, dict) else symbol_values.time_weighted_investment_values)[date_string] if (symbol_values.get('timeWeightedInvestmentValues') if isinstance(symbol_values, dict) else symbol_values.time_weighted_investment_values) is not None else None) if ((symbol_values.get('timeWeightedInvestmentValues') if isinstance(symbol_values, dict) else symbol_values.time_weighted_investment_values)[date_string] if (symbol_values.get('timeWeightedInvestmentValues') if isinstance(symbol_values, dict) else symbol_values.time_weighted_investment_values) is not None else None) is not None else Decimal('0'))
                time_weighted_investment_value_with_currency_effect = (((symbol_values.get('timeWeightedInvestmentValuesWithCurrencyEffect') if isinstance(symbol_values, dict) else symbol_values.time_weighted_investment_values_with_currency_effect)[date_string] if (symbol_values.get('timeWeightedInvestmentValuesWithCurrencyEffect') if isinstance(symbol_values, dict) else symbol_values.time_weighted_investment_values_with_currency_effect) is not None else None) if ((symbol_values.get('timeWeightedInvestmentValuesWithCurrencyEffect') if isinstance(symbol_values, dict) else symbol_values.time_weighted_investment_values_with_currency_effect)[date_string] if (symbol_values.get('timeWeightedInvestmentValuesWithCurrencyEffect') if isinstance(symbol_values, dict) else symbol_values.time_weighted_investment_values_with_currency_effect) is not None else None) is not None else Decimal('0'))
                accumulated_values_by_date[date_string] = {'investmentValueWithCurrencyEffect': ((((accumulated_values_by_date[date_string].get('investmentValueWithCurrencyEffect') if isinstance(accumulated_values_by_date[date_string], dict) else getattr(accumulated_values_by_date[date_string], 'investment_value_with_currency_effect', None)) if (accumulated_values_by_date[date_string].get('investmentValueWithCurrencyEffect') if isinstance(accumulated_values_by_date[date_string], dict) else getattr(accumulated_values_by_date[date_string], 'investment_value_with_currency_effect', None)) is not None else Decimal('0'))) + investment_value_with_currency_effect), 'totalAccountBalanceWithCurrencyEffect': account_balance_map[date_string], 'totalCurrentValue': ((((accumulated_values_by_date[date_string].get('totalCurrentValue') if isinstance(accumulated_values_by_date[date_string], dict) else getattr(accumulated_values_by_date[date_string], 'total_current_value', None)) if (accumulated_values_by_date[date_string].get('totalCurrentValue') if isinstance(accumulated_values_by_date[date_string], dict) else getattr(accumulated_values_by_date[date_string], 'total_current_value', None)) is not None else Decimal('0'))) + current_value), 'totalCurrentValueWithCurrencyEffect': ((((accumulated_values_by_date[date_string].get('totalCurrentValueWithCurrencyEffect') if isinstance(accumulated_values_by_date[date_string], dict) else getattr(accumulated_values_by_date[date_string], 'total_current_value_with_currency_effect', None)) if (accumulated_values_by_date[date_string].get('totalCurrentValueWithCurrencyEffect') if isinstance(accumulated_values_by_date[date_string], dict) else getattr(accumulated_values_by_date[date_string], 'total_current_value_with_currency_effect', None)) is not None else Decimal('0'))) + current_value_with_currency_effect), 'totalInvestmentValue': ((((accumulated_values_by_date[date_string].get('totalInvestmentValue') if isinstance(accumulated_values_by_date[date_string], dict) else getattr(accumulated_values_by_date[date_string], 'total_investment_value', None)) if (accumulated_values_by_date[date_string].get('totalInvestmentValue') if isinstance(accumulated_values_by_date[date_string], dict) else getattr(accumulated_values_by_date[date_string], 'total_investment_value', None)) is not None else Decimal('0'))) + investment_value_accumulated), 'totalInvestmentValueWithCurrencyEffect': ((((accumulated_values_by_date[date_string].get('totalInvestmentValueWithCurrencyEffect') if isinstance(accumulated_values_by_date[date_string], dict) else getattr(accumulated_values_by_date[date_string], 'total_investment_value_with_currency_effect', None)) if (accumulated_values_by_date[date_string].get('totalInvestmentValueWithCurrencyEffect') if isinstance(accumulated_values_by_date[date_string], dict) else getattr(accumulated_values_by_date[date_string], 'total_investment_value_with_currency_effect', None)) is not None else Decimal('0'))) + investment_value_accumulated_with_currency_effect), 'totalNetPerformanceValue': ((((accumulated_values_by_date[date_string].get('totalNetPerformanceValue') if isinstance(accumulated_values_by_date[date_string], dict) else getattr(accumulated_values_by_date[date_string], 'total_net_performance_value', None)) if (accumulated_values_by_date[date_string].get('totalNetPerformanceValue') if isinstance(accumulated_values_by_date[date_string], dict) else getattr(accumulated_values_by_date[date_string], 'total_net_performance_value', None)) is not None else Decimal('0'))) + net_performance_value), 'totalNetPerformanceValueWithCurrencyEffect': ((((accumulated_values_by_date[date_string].get('totalNetPerformanceValueWithCurrencyEffect') if isinstance(accumulated_values_by_date[date_string], dict) else getattr(accumulated_values_by_date[date_string], 'total_net_performance_value_with_currency_effect', None)) if (accumulated_values_by_date[date_string].get('totalNetPerformanceValueWithCurrencyEffect') if isinstance(accumulated_values_by_date[date_string], dict) else getattr(accumulated_values_by_date[date_string], 'total_net_performance_value_with_currency_effect', None)) is not None else Decimal('0'))) + net_performance_value_with_currency_effect), 'totalTimeWeightedInvestmentValue': ((((accumulated_values_by_date[date_string].get('totalTimeWeightedInvestmentValue') if isinstance(accumulated_values_by_date[date_string], dict) else getattr(accumulated_values_by_date[date_string], 'total_time_weighted_investment_value', None)) if (accumulated_values_by_date[date_string].get('totalTimeWeightedInvestmentValue') if isinstance(accumulated_values_by_date[date_string], dict) else getattr(accumulated_values_by_date[date_string], 'total_time_weighted_investment_value', None)) is not None else Decimal('0'))) + time_weighted_investment_value), 'totalTimeWeightedInvestmentValueWithCurrencyEffect': ((((accumulated_values_by_date[date_string].get('totalTimeWeightedInvestmentValueWithCurrencyEffect') if isinstance(accumulated_values_by_date[date_string], dict) else getattr(accumulated_values_by_date[date_string], 'total_time_weighted_investment_value_with_currency_effect', None)) if (accumulated_values_by_date[date_string].get('totalTimeWeightedInvestmentValueWithCurrencyEffect') if isinstance(accumulated_values_by_date[date_string], dict) else getattr(accumulated_values_by_date[date_string], 'total_time_weighted_investment_value_with_currency_effect', None)) is not None else Decimal('0'))) + time_weighted_investment_value_with_currency_effect)}
        historical_data = [(lambda _arr: None)(_x) for _x in list(accumulated_values_by_date.items())]
        overall = self.calculate_overall_performance(positions)
        positions_included_in_holdings = [(lambda include_in_holdings, **rest: rest)(_x) for _x in [_x for _x in positions if (lambda include_in_holdings: include_in_holdings)(_x)]]
        return {**overall, 'errors': errors, 'historicalData': historical_data, 'totalInterestWithCurrencyEffect': total_interest_with_currency_effect, 'totalLiabilitiesWithCurrencyEffect': total_liabilities_with_currency_effect, 'hasErrors': (has_any_symbol_metrics_errors or (overall.get('hasErrors') if isinstance(overall, dict) else overall.has_errors)), 'positions': positions_included_in_holdings}

    def get_data_provider_infos(self):
        return self.data_provider_infos

    def get_dividend_in_base_currency(self):
        self.snapshot_promise
        return sum([(lambda dividend_in_base_currency: dividend_in_base_currency)(_x) for _x in self.snapshot.positions])

    def get_fees_in_base_currency(self):
        self.snapshot_promise
        return (self.snapshot.get('totalFeesWithCurrencyEffect') if isinstance(self.snapshot, dict) else self.snapshot.total_fees_with_currency_effect)

    def get_interest_in_base_currency(self):
        self.snapshot_promise
        return (self.snapshot.get('totalInterestWithCurrencyEffect') if isinstance(self.snapshot, dict) else self.snapshot.total_interest_with_currency_effect)

    def get_investments(self):
        if (len(self.transaction_points) == 0):
            return []
        return [(lambda transaction_point: {'date': transaction_point.date, 'investment': _reduce(transaction_point.items, lambda investment, transaction_point_symbol: (investment + transaction_point_symbol.investment), Decimal('0'))})(_x) for _x in self.transaction_points]

    def get_investments_by_group(self, data, group_by):
        grouped_data = {}
        for date, investment_value_with_currency_effect in data:
            date_group = (date[0:7] if (group_by == 'month') else date[0:4])
            grouped_data[date_group] = (((grouped_data[date_group] if grouped_data[date_group] is not None else Decimal('0'))) + investment_value_with_currency_effect)
        return [(lambda date_group: ({'date': (f"{date_group}-01" if (group_by == 'month') else f"{date_group}-01-01"), 'investment': float(grouped_data[date_group])}))(_x) for _x in list(grouped_data.keys())]

    def get_liabilities_in_base_currency(self):
        self.snapshot_promise
        return (self.snapshot.get('totalLiabilitiesWithCurrencyEffect') if isinstance(self.snapshot, dict) else self.snapshot.total_liabilities_with_currency_effect)

    def get_performance(self, end, start):
        self.snapshot_promise
        historical_data = self.snapshot['historicalData']
        chart = []
        net_performance_at_start_date = None
        net_performance_with_currency_effect_at_start_date = None
        total_investment_values_with_currency_effect = []
        for historical_data_item in historical_data:
            date = _reset_hours(_parse_date(historical_data_item.date))
            if ((not _is_before(date, start)) and (not _is_after(date, end))):
                if (not isinstance(net_performance_at_start_date, (int, float, Decimal))):
                    net_performance_at_start_date = (historical_data_item.get('netPerformance') if isinstance(historical_data_item, dict) else historical_data_item.net_performance)
                    net_performance_with_currency_effect_at_start_date = (historical_data_item.get('netPerformanceWithCurrencyEffect') if isinstance(historical_data_item, dict) else historical_data_item.net_performance_with_currency_effect)
                net_performance_since_start_date = ((historical_data_item.get('netPerformance') if isinstance(historical_data_item, dict) else historical_data_item.net_performance) - net_performance_at_start_date)
                net_performance_with_currency_effect_since_start_date = ((historical_data_item.get('netPerformanceWithCurrencyEffect') if isinstance(historical_data_item, dict) else historical_data_item.net_performance_with_currency_effect) - net_performance_with_currency_effect_at_start_date)
                if ((historical_data_item.get('totalInvestmentValueWithCurrencyEffect') if isinstance(historical_data_item, dict) else historical_data_item.total_investment_value_with_currency_effect) > 0):
                    total_investment_values_with_currency_effect.append((historical_data_item.get('totalInvestmentValueWithCurrencyEffect') if isinstance(historical_data_item, dict) else historical_data_item.total_investment_value_with_currency_effect))
                time_weighted_investment_value = ((sum(total_investment_values_with_currency_effect) / len(total_investment_values_with_currency_effect)) if (len(total_investment_values_with_currency_effect) > 0) else 0)
                chart.append({**historical_data_item, 'netPerformance': ((historical_data_item.get('netPerformance') if isinstance(historical_data_item, dict) else historical_data_item.net_performance) - net_performance_at_start_date), 'netPerformanceWithCurrencyEffect': net_performance_with_currency_effect_since_start_date, 'netPerformanceInPercentage': (0 if (time_weighted_investment_value == 0) else (net_performance_since_start_date / time_weighted_investment_value)), 'netPerformanceInPercentageWithCurrencyEffect': (0 if (time_weighted_investment_value == 0) else (net_performance_with_currency_effect_since_start_date / time_weighted_investment_value))})
        return {'chart': chart}

    def get_snapshot(self):
        self.snapshot_promise
        return self.snapshot

    def get_start_date(self):
        first_account_balance_date = None
        first_activity_date = None
        try:
            first_account_balance_date_string = (getattr(self.account_balance_items[0], 'date', None) if self.account_balance_items[0] is not None else None)
            first_account_balance_date = (_parse_date(first_account_balance_date_string) if first_account_balance_date_string else datetime.now())
        except Exception as error:
            first_account_balance_date = datetime.now()
        try:
            first_activity_date_string = self.transaction_points[0].date
            first_activity_date = (_parse_date(first_activity_date_string) if first_activity_date_string else datetime.now())
        except Exception as error:
            first_activity_date = datetime.now()
        return min([first_account_balance_date, first_activity_date])

    def get_transaction_points(self):
        return self.transaction_points

    def get_chart_date_map(self, end_date, start_date, step):
        # Create a map of all relevant chart dates:
        # 1. Add transaction point dates
        chart_date_map = _reduce(self.transaction_points, lambda result, date: None, {})
        # 2. Add dates between transactions respecting the specified step size
        for date in _each_day_of_interval({'end': end_date, 'start': start_date}, {'step': step}):
            chart_date_map[_format_date(date, DATE_FORMAT)] = True
        if (step > 1):
            # Reduce the step size of last 90 days
            for date in _each_day_of_interval({'end': end_date, 'start': _sub_days(end_date, 90)}, {'step': 3}):
                chart_date_map[_format_date(date, DATE_FORMAT)] = True
            # Reduce the step size of last 30 days
            for date in _each_day_of_interval({'end': end_date, 'start': _sub_days(end_date, 30)}, {'step': 1}):
                chart_date_map[_format_date(date, DATE_FORMAT)] = True
        # Make sure the end date is present
        chart_date_map[_format_date(end_date, DATE_FORMAT)] = True
        # Make sure some key dates are present
        for date_range in ['1d', '1y', '5y', 'max', 'mtd', 'wtd', 'ytd']:
            date_range_end = _get_interval_from_date_range(date_range)['dateRangeEnd']
            date_range_start = _get_interval_from_date_range(date_range)['dateRangeStart']
            if ((not _is_before(date_range_start, start_date)) and (not _is_after(date_range_start, end_date))):
                chart_date_map[_format_date(date_range_start, DATE_FORMAT)] = True
            if ((not _is_before(date_range_end, start_date)) and (not _is_after(date_range_end, end_date))):
                chart_date_map[_format_date(date_range_end, DATE_FORMAT)] = True
        # Make sure the first and last date of each calendar year is present
        interval = {'start': start_date, 'end': end_date}
        for date in _each_year_of_interval(interval):
            year_start = _start_of_year(date)
            year_end = _end_of_year(date)
            if _is_within_interval(year_start, interval):
                # Add start of year (YYYY-01-01)
                chart_date_map[_format_date(year_start, DATE_FORMAT)] = True
            if _is_within_interval(year_end, interval):
                # Add end of year (YYYY-12-31)
                chart_date_map[_format_date(year_end, DATE_FORMAT)] = True
        return chart_date_map

    def compute_transaction_points(self):
        self.transaction_points = []
        symbols = {}
        last_date = None
        last_transaction_point = None
        for date, fee, fee_in_base_currency, quantity, symbol_profile, tags, type, unit_price in self.activities:
            current_transaction_point_item = None
            asset_sub_class = (symbol_profile.get('assetSubClass') if isinstance(symbol_profile, dict) else symbol_profile.asset_sub_class)
            currency = symbol_profile.currency
            data_source = (symbol_profile.get('dataSource') if isinstance(symbol_profile, dict) else symbol_profile.data_source)
            factor = _get_factor(type)
            skip_errors = (not (not (symbol_profile.get('userId') if isinstance(symbol_profile, dict) else symbol_profile.user_id)))
            # Skip errors for custom asset profiles
            symbol = symbol_profile.symbol
            old_accumulated_symbol = symbols[symbol]
            if old_accumulated_symbol:
                investment = old_accumulated_symbol.investment
                new_quantity = ((quantity * factor) + old_accumulated_symbol.quantity)
                if (type == 'BUY'):
                    if (old_accumulated_symbol.investment >= 0):
                        investment = (old_accumulated_symbol.investment + (quantity * unit_price))
                    else:
                        investment = (old_accumulated_symbol.investment + (quantity * (old_accumulated_symbol.get('averagePrice') if isinstance(old_accumulated_symbol, dict) else old_accumulated_symbol.average_price)))
                elif (type == 'SELL'):
                    if (old_accumulated_symbol.investment > 0):
                        investment = (old_accumulated_symbol.investment - (quantity * (old_accumulated_symbol.get('averagePrice') if isinstance(old_accumulated_symbol, dict) else old_accumulated_symbol.average_price)))
                    else:
                        investment = (old_accumulated_symbol.investment - (quantity * unit_price))
                if (abs(new_quantity) < EPSILON):
                    # Reset to zero if quantity is (almost) zero to avoid rounding issues
                    investment = Decimal('0')
                    new_quantity = Decimal('0')
                current_transaction_point_item = {'assetSubClass': asset_sub_class, 'currency': currency, 'dataSource': data_source, 'investment': investment, 'skipErrors': skip_errors, 'symbol': symbol, 'activitiesCount': ((old_accumulated_symbol.get('activitiesCount') if isinstance(old_accumulated_symbol, dict) else old_accumulated_symbol.activities_count) + 1), 'averagePrice': (Decimal('0') if (new_quantity == 0) else abs((investment / new_quantity))), 'dateOfFirstActivity': (old_accumulated_symbol.get('dateOfFirstActivity') if isinstance(old_accumulated_symbol, dict) else old_accumulated_symbol.date_of_first_activity), 'dividend': Decimal('0'), 'fee': (old_accumulated_symbol.fee + fee), 'feeInBaseCurrency': ((old_accumulated_symbol.get('feeInBaseCurrency') if isinstance(old_accumulated_symbol, dict) else old_accumulated_symbol.fee_in_base_currency) + fee_in_base_currency), 'includeInHoldings': (old_accumulated_symbol.get('includeInHoldings') if isinstance(old_accumulated_symbol, dict) else old_accumulated_symbol.include_in_holdings), 'quantity': new_quantity, 'tags': (old_accumulated_symbol.tags + tags)}
            else:
                current_transaction_point_item = {'assetSubClass': asset_sub_class, 'currency': currency, 'dataSource': data_source, 'fee': fee, 'feeInBaseCurrency': fee_in_base_currency, 'skipErrors': skip_errors, 'symbol': symbol, 'tags': tags, 'activitiesCount': 1, 'averagePrice': unit_price, 'dateOfFirstActivity': date, 'dividend': Decimal('0'), 'includeInHoldings': (type in INVESTMENT_ACTIVITY_TYPES), 'investment': ((unit_price * quantity) * factor), 'quantity': (quantity * factor)}
            current_transaction_point_item.tags = _uniq_by(current_transaction_point_item.tags, 'id')
            symbols[symbol_profile.symbol] = current_transaction_point_item
            items = ((getattr(last_transaction_point, 'items', None) if last_transaction_point is not None else None) if (getattr(last_transaction_point, 'items', None) if last_transaction_point is not None else None) is not None else [])
            new_items = [_x for _x in items if (lambda symbol: (symbol != symbol_profile.symbol))(_x)]
            new_items.append(current_transaction_point_item)
            sorted(new_items, key=lambda a, b: ((a.symbol > b.symbol) - (a.symbol < b.symbol)))
            fees = Decimal('0')
            if (type == 'FEE'):
                fees = fee
            interest = Decimal('0')
            if (type == 'INTEREST'):
                interest = (quantity * unit_price)
            liabilities = Decimal('0')
            if (type == 'LIABILITY'):
                liabilities = (quantity * unit_price)
            if ((last_date != date) or (last_transaction_point == None)):
                last_transaction_point = {'date': date, 'fees': fees, 'interest': interest, 'liabilities': liabilities, 'items': new_items}
                self.transaction_points.append(last_transaction_point)
            else:
                last_transaction_point.fees = (last_transaction_point.fees + fees)
                last_transaction_point.interest = (last_transaction_point.interest + interest)
                last_transaction_point.items = new_items
                last_transaction_point.liabilities = (last_transaction_point.liabilities + liabilities)
            last_date = date

    def initialize(self):
        start_time_total = performance.now()
        cached_portfolio_snapshot = None
        is_cached_portfolio_snapshot_expired = False
        job_id = self.user_id
        try:
            cached_portfolio_snapshot_value = self.redis_cache_service.get(self.redis_cache_service.get_portfolio_snapshot_key({'filters': self.filters, 'userId': self.user_id}))
            expiration = json.loads(cached_portfolio_snapshot_value)['expiration']
            portfolio_snapshot = json.loads(cached_portfolio_snapshot_value)['portfolioSnapshot']
            cached_portfolio_snapshot = portfolio_snapshot
            if _is_after(datetime.now(), _parse_date(expiration)):
                is_cached_portfolio_snapshot_expired = True
        except Exception:
            pass
        if cached_portfolio_snapshot:
            self.snapshot = cached_portfolio_snapshot
            if is_cached_portfolio_snapshot_expired:
                # Compute in the background
                self.portfolio_snapshot_service.add_job_to_queue({'data': {'calculationType': self.get_performance_calculation_type(), 'filters': self.filters, 'userCurrency': self.currency, 'userId': self.user_id}, 'name': PORTFOLIO_SNAPSHOT_PROCESS_JOB_NAME, 'opts': {**PORTFOLIO_SNAPSHOT_PROCESS_JOB_OPTIONS, 'jobId': job_id, 'priority': PORTFOLIO_SNAPSHOT_COMPUTATION_QUEUE_PRIORITY_LOW}})
        else:
            # Wait for computation
            self.portfolio_snapshot_service.add_job_to_queue({'data': {'calculationType': self.get_performance_calculation_type(), 'filters': self.filters, 'userCurrency': self.currency, 'userId': self.user_id}, 'name': PORTFOLIO_SNAPSHOT_PROCESS_JOB_NAME, 'opts': {**PORTFOLIO_SNAPSHOT_PROCESS_JOB_OPTIONS, 'jobId': job_id, 'priority': PORTFOLIO_SNAPSHOT_COMPUTATION_QUEUE_PRIORITY_HIGH}})
            job = self.portfolio_snapshot_service.get_job(job_id)
            if job:
                job.finished()
            self.initialize()


class RoaiPortfolioCalculator(_CalculatorMixin, _TxBase, PortfolioCalculator):

    def calculate_overall_performance(self, positions):
        current_value_in_base_currency = Decimal('0')
        gross_performance = Decimal('0')
        gross_performance_with_currency_effect = Decimal('0')
        has_errors = False
        net_performance = Decimal('0')
        total_fees_with_currency_effect = Decimal('0')
        total_interest_with_currency_effect = Decimal('0')
        total_investment = Decimal('0')
        total_investment_with_currency_effect = Decimal('0')
        total_time_weighted_investment = Decimal('0')
        total_time_weighted_investment_with_currency_effect = Decimal('0')
        for current_position in [_x for _x in positions if (lambda include_in_total_asset_value: include_in_total_asset_value)(_x)]:
            if (current_position.get('feeInBaseCurrency') if isinstance(current_position, dict) else current_position.fee_in_base_currency):
                total_fees_with_currency_effect = (total_fees_with_currency_effect + (current_position.get('feeInBaseCurrency') if isinstance(current_position, dict) else current_position.fee_in_base_currency))
            if (current_position.get('valueInBaseCurrency') if isinstance(current_position, dict) else current_position.value_in_base_currency):
                current_value_in_base_currency = (current_value_in_base_currency + (current_position.get('valueInBaseCurrency') if isinstance(current_position, dict) else current_position.value_in_base_currency))
            else:
                has_errors = True
            if current_position.investment:
                total_investment = (total_investment + current_position.investment)
                total_investment_with_currency_effect = (total_investment_with_currency_effect + (current_position.get('investmentWithCurrencyEffect') if isinstance(current_position, dict) else current_position.investment_with_currency_effect))
            else:
                has_errors = True
            if (current_position.get('grossPerformance') if isinstance(current_position, dict) else current_position.gross_performance):
                gross_performance = (gross_performance + (current_position.get('grossPerformance') if isinstance(current_position, dict) else current_position.gross_performance))
                gross_performance_with_currency_effect = (gross_performance_with_currency_effect + (current_position.get('grossPerformanceWithCurrencyEffect') if isinstance(current_position, dict) else current_position.gross_performance_with_currency_effect))
                net_performance = (net_performance + (current_position.get('netPerformance') if isinstance(current_position, dict) else current_position.net_performance))
            elif (not (current_position.quantity == 0)):
                has_errors = True
            if (current_position.get('timeWeightedInvestment') if isinstance(current_position, dict) else current_position.time_weighted_investment):
                total_time_weighted_investment = (total_time_weighted_investment + (current_position.get('timeWeightedInvestment') if isinstance(current_position, dict) else current_position.time_weighted_investment))
                total_time_weighted_investment_with_currency_effect = (total_time_weighted_investment_with_currency_effect + (current_position.get('timeWeightedInvestmentWithCurrencyEffect') if isinstance(current_position, dict) else current_position.time_weighted_investment_with_currency_effect))
            elif (not (current_position.quantity == 0)):
                has_errors = True
        return {'currentValueInBaseCurrency': current_value_in_base_currency, 'hasErrors': has_errors, 'positions': positions, 'totalFeesWithCurrencyEffect': total_fees_with_currency_effect, 'totalInterestWithCurrencyEffect': total_interest_with_currency_effect, 'totalInvestment': total_investment, 'totalInvestmentWithCurrencyEffect': total_investment_with_currency_effect, 'activitiesCount': len([_x for _x in self.activities if (lambda type: (type in ['BUY', 'SELL']))(_x)]), 'createdAt': datetime.now(), 'errors': [], 'historicalData': [], 'totalLiabilitiesWithCurrencyEffect': Decimal('0')}

    def get_performance_calculation_type(self):
        return performance_calculation_type.ROAI

    def get_symbol_metrics(self, chart_date_map, data_source, end, exchange_rates, market_symbol_map, start, symbol):
        current_exchange_rate = exchange_rates[_format_date(datetime.now(), DATE_FORMAT)]
        current_values = {}
        current_values_with_currency_effect = {}
        fees = Decimal('0')
        fees_at_start_date = Decimal('0')
        fees_at_start_date_with_currency_effect = Decimal('0')
        fees_with_currency_effect = Decimal('0')
        gross_performance = Decimal('0')
        gross_performance_with_currency_effect = Decimal('0')
        gross_performance_at_start_date = Decimal('0')
        gross_performance_at_start_date_with_currency_effect = Decimal('0')
        gross_performance_from_sells = Decimal('0')
        gross_performance_from_sells_with_currency_effect = Decimal('0')
        initial_value = None
        initial_value_with_currency_effect = None
        investment_at_start_date = None
        investment_at_start_date_with_currency_effect = None
        investment_values_accumulated = {}
        investment_values_accumulated_with_currency_effect = {}
        investment_values_with_currency_effect = {}
        last_average_price = Decimal('0')
        last_average_price_with_currency_effect = Decimal('0')
        net_performance_values = {}
        net_performance_values_with_currency_effect = {}
        time_weighted_investment_values = {}
        time_weighted_investment_values_with_currency_effect = {}
        total_account_balance_in_base_currency = Decimal('0')
        total_dividend = Decimal('0')
        total_dividend_in_base_currency = Decimal('0')
        total_interest = Decimal('0')
        total_interest_in_base_currency = Decimal('0')
        total_investment = Decimal('0')
        total_investment_from_buy_transactions = Decimal('0')
        total_investment_from_buy_transactions_with_currency_effect = Decimal('0')
        total_investment_with_currency_effect = Decimal('0')
        total_liabilities = Decimal('0')
        total_liabilities_in_base_currency = Decimal('0')
        total_quantity_from_buy_transactions = Decimal('0')
        total_units = Decimal('0')
        value_at_start_date = None
        value_at_start_date_with_currency_effect = None
        # Clone orders to keep the original values in this.orders
        orders = deepcopy([_x for _x in self.activities if (lambda symbol_profile: (symbol_profile.symbol == symbol))(_x)])
        is_cash = (((getattr(orders[0], 'symbol_profile', None) if orders[0] is not None else None).get('assetSubClass') if isinstance((getattr(orders[0], 'symbol_profile', None) if orders[0] is not None else None), dict) else getattr((getattr(orders[0], 'symbol_profile', None) if orders[0] is not None else None), 'asset_sub_class', None)) == 'CASH')
        if (len(orders) <= 0):
            return {'currentValues': {}, 'currentValuesWithCurrencyEffect': {}, 'feesWithCurrencyEffect': Decimal('0'), 'grossPerformance': Decimal('0'), 'grossPerformancePercentage': Decimal('0'), 'grossPerformancePercentageWithCurrencyEffect': Decimal('0'), 'grossPerformanceWithCurrencyEffect': Decimal('0'), 'hasErrors': False, 'initialValue': Decimal('0'), 'initialValueWithCurrencyEffect': Decimal('0'), 'investmentValuesAccumulated': {}, 'investmentValuesAccumulatedWithCurrencyEffect': {}, 'investmentValuesWithCurrencyEffect': {}, 'netPerformance': Decimal('0'), 'netPerformancePercentage': Decimal('0'), 'netPerformancePercentageWithCurrencyEffectMap': {}, 'netPerformanceValues': {}, 'netPerformanceValuesWithCurrencyEffect': {}, 'netPerformanceWithCurrencyEffectMap': {}, 'timeWeightedInvestment': Decimal('0'), 'timeWeightedInvestmentValues': {}, 'timeWeightedInvestmentValuesWithCurrencyEffect': {}, 'timeWeightedInvestmentWithCurrencyEffect': Decimal('0'), 'totalAccountBalanceInBaseCurrency': Decimal('0'), 'totalDividend': Decimal('0'), 'totalDividendInBaseCurrency': Decimal('0'), 'totalInterest': Decimal('0'), 'totalInterestInBaseCurrency': Decimal('0'), 'totalInvestment': Decimal('0'), 'totalInvestmentWithCurrencyEffect': Decimal('0'), 'totalLiabilities': Decimal('0'), 'totalLiabilitiesInBaseCurrency': Decimal('0')}
        date_of_first_transaction = _parse_date(orders[0].date)
        end_date_string = _format_date(end, DATE_FORMAT)
        start_date_string = _format_date(start, DATE_FORMAT)
        unit_price_at_start_date = (market_symbol_map[start_date_string][symbol] if market_symbol_map[start_date_string] is not None else None)
        unit_price_at_end_date = (market_symbol_map[end_date_string][symbol] if market_symbol_map[end_date_string] is not None else None)
        latest_activity = orders[(-1)]
        if ((((data_source == 'MANUAL') and ((getattr(latest_activity, 'type', None) if latest_activity is not None else None) in ['BUY', 'SELL'])) and (latest_activity.get('unitPrice') if isinstance(latest_activity, dict) else getattr(latest_activity, 'unit_price', None))) and (not unit_price_at_end_date)):
            # For BUY / SELL activities with a MANUAL data source where no historical market price is available,
            # the calculation should fall back to using the activity’s unit price.
            unit_price_at_end_date = (latest_activity.get('unitPrice') if isinstance(latest_activity, dict) else latest_activity.unit_price)
        elif is_cash:
            unit_price_at_end_date = Decimal('1')
        if ((not unit_price_at_end_date) or (((not unit_price_at_start_date) and _is_before(date_of_first_transaction, start)))):
            return {'currentValues': {}, 'currentValuesWithCurrencyEffect': {}, 'feesWithCurrencyEffect': Decimal('0'), 'grossPerformance': Decimal('0'), 'grossPerformancePercentage': Decimal('0'), 'grossPerformancePercentageWithCurrencyEffect': Decimal('0'), 'grossPerformanceWithCurrencyEffect': Decimal('0'), 'hasErrors': True, 'initialValue': Decimal('0'), 'initialValueWithCurrencyEffect': Decimal('0'), 'investmentValuesAccumulated': {}, 'investmentValuesAccumulatedWithCurrencyEffect': {}, 'investmentValuesWithCurrencyEffect': {}, 'netPerformance': Decimal('0'), 'netPerformancePercentage': Decimal('0'), 'netPerformancePercentageWithCurrencyEffectMap': {}, 'netPerformanceWithCurrencyEffectMap': {}, 'netPerformanceValues': {}, 'netPerformanceValuesWithCurrencyEffect': {}, 'timeWeightedInvestment': Decimal('0'), 'timeWeightedInvestmentValues': {}, 'timeWeightedInvestmentValuesWithCurrencyEffect': {}, 'timeWeightedInvestmentWithCurrencyEffect': Decimal('0'), 'totalAccountBalanceInBaseCurrency': Decimal('0'), 'totalDividend': Decimal('0'), 'totalDividendInBaseCurrency': Decimal('0'), 'totalInterest': Decimal('0'), 'totalInterestInBaseCurrency': Decimal('0'), 'totalInvestment': Decimal('0'), 'totalInvestmentWithCurrencyEffect': Decimal('0'), 'totalLiabilities': Decimal('0'), 'totalLiabilitiesInBaseCurrency': Decimal('0')}
        # Add a synthetic order at the start and the end date
        orders.append({'date': start_date_string, 'fee': Decimal('0'), 'feeInBaseCurrency': Decimal('0'), 'itemType': 'start', 'quantity': Decimal('0'), 'SymbolProfile': {'dataSource': data_source, 'symbol': symbol, 'assetSubClass': ('CASH' if is_cash else None)}, 'type': 'BUY', 'unitPrice': unit_price_at_start_date})
        orders.append({'date': end_date_string, 'fee': Decimal('0'), 'feeInBaseCurrency': Decimal('0'), 'itemType': 'end', 'SymbolProfile': {'dataSource': data_source, 'symbol': symbol, 'assetSubClass': ('CASH' if is_cash else None)}, 'quantity': Decimal('0'), 'type': 'BUY', 'unitPrice': unit_price_at_end_date})
        last_unit_price = None
        orders_by_date = {}
        for order in orders:
            orders_by_date[order.date] = (orders_by_date[order.date] if orders_by_date[order.date] is not None else [])
            orders_by_date[order.date].append(order)
        if (not self.chart_dates):
            self.chart_dates = sorted(list(chart_date_map.keys()))
        for date_string in self.chart_dates:
            if (date_string < start_date_string):
                continue
            elif (date_string > end_date_string):
                break
            if (len(orders_by_date[date_string]) > 0):
                for order in orders_by_date[date_string]:
                    order.unit_price_from_market_data = ((market_symbol_map[date_string][symbol] if market_symbol_map[date_string] is not None else None) if (market_symbol_map[date_string][symbol] if market_symbol_map[date_string] is not None else None) is not None else last_unit_price)
            else:
                orders.append({'date': date_string, 'fee': Decimal('0'), 'feeInBaseCurrency': Decimal('0'), 'quantity': Decimal('0'), 'SymbolProfile': {'dataSource': data_source, 'symbol': symbol, 'assetSubClass': ('CASH' if is_cash else None)}, 'type': 'BUY', 'unitPrice': ((market_symbol_map[date_string][symbol] if market_symbol_map[date_string] is not None else None) if (market_symbol_map[date_string][symbol] if market_symbol_map[date_string] is not None else None) is not None else last_unit_price), 'unitPriceFromMarketData': ((market_symbol_map[date_string][symbol] if market_symbol_map[date_string] is not None else None) if (market_symbol_map[date_string][symbol] if market_symbol_map[date_string] is not None else None) is not None else last_unit_price)})
            latest_activity = orders[(-1)]
            last_unit_price = ((latest_activity.get('unitPriceFromMarketData') if isinstance(latest_activity, dict) else latest_activity.unit_price_from_market_data) if (latest_activity.get('unitPriceFromMarketData') if isinstance(latest_activity, dict) else latest_activity.unit_price_from_market_data) is not None else (latest_activity.get('unitPrice') if isinstance(latest_activity, dict) else latest_activity.unit_price))
        # Sort orders so that the start and end placeholder order are at the correct
        # position
        orders = sorted(orders, key=lambda date, item_type: None)
        index_of_start_order = next((_i for _i, _x in enumerate(orders) if (lambda item_type: (item_type == 'start'))(_x)), -1)
        index_of_end_order = next((_i for _i, _x in enumerate(orders) if (lambda item_type: (item_type == 'end'))(_x)), -1)
        total_investment_days = 0
        sum_of_time_weighted_investments = Decimal('0')
        sum_of_time_weighted_investments_with_currency_effect = Decimal('0')
        for i in range(len(orders)):
            order = orders[i]

            exchange_rate_at_order_date = exchange_rates[order.date]
            if (order.type == 'DIVIDEND'):
                dividend = (order.quantity * (order.get('unitPrice') if isinstance(order, dict) else order.unit_price))
                total_dividend = (total_dividend + dividend)
                total_dividend_in_base_currency = (total_dividend_in_base_currency + (dividend * (exchange_rate_at_order_date if exchange_rate_at_order_date is not None else 1)))
            elif (order.type == 'INTEREST'):
                interest = (order.quantity * (order.get('unitPrice') if isinstance(order, dict) else order.unit_price))
                total_interest = (total_interest + interest)
                total_interest_in_base_currency = (total_interest_in_base_currency + (interest * (exchange_rate_at_order_date if exchange_rate_at_order_date is not None else 1)))
            elif (order.type == 'LIABILITY'):
                liabilities = (order.quantity * (order.get('unitPrice') if isinstance(order, dict) else order.unit_price))
                total_liabilities = (total_liabilities + liabilities)
                total_liabilities_in_base_currency = (total_liabilities_in_base_currency + (liabilities * (exchange_rate_at_order_date if exchange_rate_at_order_date is not None else 1)))
            if ((order.get('itemType') if isinstance(order, dict) else order.item_type) == 'start'):
                # Take the unit price of the order as the market price if there are no
                # orders of this symbol before the start date
                order.unit_price = ((orders[(i + 1)].get('unitPrice') if isinstance(orders[(i + 1)], dict) else getattr(orders[(i + 1)], 'unit_price', None)) if (index_of_start_order == 0) else unit_price_at_start_date)
            if order.fee:
                order.fee_in_base_currency = (order.fee * (current_exchange_rate if current_exchange_rate is not None else 1))
                order.fee_in_base_currency_with_currency_effect = (order.fee * (exchange_rate_at_order_date if exchange_rate_at_order_date is not None else 1))
            unit_price = ((order.get('unitPrice') if isinstance(order, dict) else order.unit_price) if (order.type in ['BUY', 'SELL']) else (order.get('unitPriceFromMarketData') if isinstance(order, dict) else order.unit_price_from_market_data))
            if unit_price:
                order.unit_price_in_base_currency = (unit_price * (current_exchange_rate if current_exchange_rate is not None else 1))
                order.unit_price_in_base_currency_with_currency_effect = (unit_price * (exchange_rate_at_order_date if exchange_rate_at_order_date is not None else 1))
            market_price_in_base_currency = (((order.get('unitPriceFromMarketData') if isinstance(order, dict) else order.unit_price_from_market_data) * (current_exchange_rate if current_exchange_rate is not None else 1)) if ((order.get('unitPriceFromMarketData') if isinstance(order, dict) else order.unit_price_from_market_data) * (current_exchange_rate if current_exchange_rate is not None else 1)) is not None else Decimal('0'))
            market_price_in_base_currency_with_currency_effect = (((order.get('unitPriceFromMarketData') if isinstance(order, dict) else order.unit_price_from_market_data) * (exchange_rate_at_order_date if exchange_rate_at_order_date is not None else 1)) if ((order.get('unitPriceFromMarketData') if isinstance(order, dict) else order.unit_price_from_market_data) * (exchange_rate_at_order_date if exchange_rate_at_order_date is not None else 1)) is not None else Decimal('0'))
            value_of_investment_before_transaction = (total_units * market_price_in_base_currency)
            value_of_investment_before_transaction_with_currency_effect = (total_units * market_price_in_base_currency_with_currency_effect)
            if ((not investment_at_start_date) and (i >= index_of_start_order)):
                investment_at_start_date = (total_investment if total_investment is not None else Decimal('0'))
                investment_at_start_date_with_currency_effect = (total_investment_with_currency_effect if total_investment_with_currency_effect is not None else Decimal('0'))
                value_at_start_date = value_of_investment_before_transaction
                value_at_start_date_with_currency_effect = value_of_investment_before_transaction_with_currency_effect
            transaction_investment = Decimal('0')
            transaction_investment_with_currency_effect = Decimal('0')
            if (order.type == 'BUY'):
                transaction_investment = ((order.quantity * (order.get('unitPriceInBaseCurrency') if isinstance(order, dict) else order.unit_price_in_base_currency)) * _get_factor(order.type))
                transaction_investment_with_currency_effect = ((order.quantity * (order.get('unitPriceInBaseCurrencyWithCurrencyEffect') if isinstance(order, dict) else order.unit_price_in_base_currency_with_currency_effect)) * _get_factor(order.type))
                total_quantity_from_buy_transactions = (total_quantity_from_buy_transactions + order.quantity)
                total_investment_from_buy_transactions = (total_investment_from_buy_transactions + transaction_investment)
                total_investment_from_buy_transactions_with_currency_effect = (total_investment_from_buy_transactions_with_currency_effect + transaction_investment_with_currency_effect)
            elif (order.type == 'SELL'):
                if (total_units > 0):
                    transaction_investment = (((total_investment / total_units) * order.quantity) * _get_factor(order.type))
                    transaction_investment_with_currency_effect = (((total_investment_with_currency_effect / total_units) * order.quantity) * _get_factor(order.type))

            total_investment_before_transaction = total_investment
            total_investment_before_transaction_with_currency_effect = total_investment_with_currency_effect
            total_investment = (total_investment + transaction_investment)
            total_investment_with_currency_effect = (total_investment_with_currency_effect + transaction_investment_with_currency_effect)
            if ((i >= index_of_start_order) and (not initial_value)):
                if ((i == index_of_start_order) and (not (value_of_investment_before_transaction == 0))):
                    initial_value = value_of_investment_before_transaction
                    initial_value_with_currency_effect = value_of_investment_before_transaction_with_currency_effect
                elif (transaction_investment > 0):
                    initial_value = transaction_investment
                    initial_value_with_currency_effect = transaction_investment_with_currency_effect
            fees = (fees + ((order.get('feeInBaseCurrency') if isinstance(order, dict) else order.fee_in_base_currency) if (order.get('feeInBaseCurrency') if isinstance(order, dict) else order.fee_in_base_currency) is not None else 0))
            fees_with_currency_effect = (fees_with_currency_effect + ((order.get('feeInBaseCurrencyWithCurrencyEffect') if isinstance(order, dict) else order.fee_in_base_currency_with_currency_effect) if (order.get('feeInBaseCurrencyWithCurrencyEffect') if isinstance(order, dict) else order.fee_in_base_currency_with_currency_effect) is not None else 0))
            total_units = (total_units + (order.quantity * _get_factor(order.type)))
            value_of_investment = (total_units * market_price_in_base_currency)
            value_of_investment_with_currency_effect = (total_units * market_price_in_base_currency_with_currency_effect)
            gross_performance_from_sell = ((((order.get('unitPriceInBaseCurrency') if isinstance(order, dict) else order.unit_price_in_base_currency) - last_average_price) * order.quantity) if (order.type == 'SELL') else Decimal('0'))
            gross_performance_from_sell_with_currency_effect = ((((order.get('unitPriceInBaseCurrencyWithCurrencyEffect') if isinstance(order, dict) else order.unit_price_in_base_currency_with_currency_effect) - last_average_price_with_currency_effect) * order.quantity) if (order.type == 'SELL') else Decimal('0'))
            gross_performance_from_sells = (gross_performance_from_sells + gross_performance_from_sell)
            gross_performance_from_sells_with_currency_effect = (gross_performance_from_sells_with_currency_effect + gross_performance_from_sell_with_currency_effect)
            last_average_price = (Decimal('0') if (total_quantity_from_buy_transactions == 0) else (total_investment_from_buy_transactions / total_quantity_from_buy_transactions))
            last_average_price_with_currency_effect = (Decimal('0') if (total_quantity_from_buy_transactions == 0) else (total_investment_from_buy_transactions_with_currency_effect / total_quantity_from_buy_transactions))
            if (total_units == 0):
                # Reset tracking variables when position is fully closed
                total_investment_from_buy_transactions = Decimal('0')
                total_investment_from_buy_transactions_with_currency_effect = Decimal('0')
                total_quantity_from_buy_transactions = Decimal('0')

            new_gross_performance = ((value_of_investment - total_investment) + gross_performance_from_sells)
            new_gross_performance_with_currency_effect = ((value_of_investment_with_currency_effect - total_investment_with_currency_effect) + gross_performance_from_sells_with_currency_effect)
            gross_performance = new_gross_performance
            gross_performance_with_currency_effect = new_gross_performance_with_currency_effect
            if ((order.get('itemType') if isinstance(order, dict) else order.item_type) == 'start'):
                fees_at_start_date = fees
                fees_at_start_date_with_currency_effect = fees_with_currency_effect
                gross_performance_at_start_date = gross_performance
                gross_performance_at_start_date_with_currency_effect = gross_performance_with_currency_effect
            if (i > index_of_start_order):
                # Only consider periods with an investment for the calculation of
                # the time weighted investment
                if ((value_of_investment_before_transaction > 0) and (order.type in ['BUY', 'SELL'])):
                    # Calculate the number of days since the previous order
                    order_date = _parse_date(order.date)
                    previous_order_date = _parse_date(orders[(i - 1)].date)
                    days_since_last_order = _difference_in_days(order_date, previous_order_date)
                    if (days_since_last_order <= 0):
                        # The time between two activities on the same day is unknown
                        # -> Set it to the smallest floating point number greater than 0
                        days_since_last_order = EPSILON
                    # Sum up the total investment days since the start date to calculate
                    # the time weighted investment
                    total_investment_days += days_since_last_order
                    sum_of_time_weighted_investments = (sum_of_time_weighted_investments + (((value_at_start_date - investment_at_start_date) + total_investment_before_transaction) * days_since_last_order))
                    sum_of_time_weighted_investments_with_currency_effect = (sum_of_time_weighted_investments_with_currency_effect + (((value_at_start_date_with_currency_effect - investment_at_start_date_with_currency_effect) + total_investment_before_transaction_with_currency_effect) * days_since_last_order))
                current_values[order.date] = value_of_investment
                current_values_with_currency_effect[order.date] = value_of_investment_with_currency_effect
                net_performance_values[order.date] = ((gross_performance - gross_performance_at_start_date) - (fees - fees_at_start_date))
                net_performance_values_with_currency_effect[order.date] = ((gross_performance_with_currency_effect - gross_performance_at_start_date_with_currency_effect) - (fees_with_currency_effect - fees_at_start_date_with_currency_effect))
                investment_values_accumulated[order.date] = total_investment
                investment_values_accumulated_with_currency_effect[order.date] = total_investment_with_currency_effect
                investment_values_with_currency_effect[order.date] = (((investment_values_with_currency_effect[order.date] if investment_values_with_currency_effect[order.date] is not None else Decimal('0'))) + transaction_investment_with_currency_effect)
                # If duration is effectively zero (first day), use the actual investment as the base.
                # Otherwise, use the calculated time-weighted average.
                time_weighted_investment_values[order.date] = ((sum_of_time_weighted_investments / total_investment_days) if (total_investment_days > EPSILON) else (total_investment if (total_investment > 0) else Decimal('0')))
                time_weighted_investment_values_with_currency_effect[order.date] = ((sum_of_time_weighted_investments_with_currency_effect / total_investment_days) if (total_investment_days > EPSILON) else (total_investment_with_currency_effect if (total_investment_with_currency_effect > 0) else Decimal('0')))

            if (i == index_of_end_order):
                break
        total_gross_performance = (gross_performance - gross_performance_at_start_date)
        total_gross_performance_with_currency_effect = (gross_performance_with_currency_effect - gross_performance_at_start_date_with_currency_effect)
        total_net_performance = ((gross_performance - gross_performance_at_start_date) - (fees - fees_at_start_date))
        time_weighted_average_investment_between_start_and_end_date = ((sum_of_time_weighted_investments / total_investment_days) if (total_investment_days > 0) else Decimal('0'))
        time_weighted_average_investment_between_start_and_end_date_with_currency_effect = ((sum_of_time_weighted_investments_with_currency_effect / total_investment_days) if (total_investment_days > 0) else Decimal('0'))
        gross_performance_percentage = ((total_gross_performance / time_weighted_average_investment_between_start_and_end_date) if (time_weighted_average_investment_between_start_and_end_date > 0) else Decimal('0'))
        gross_performance_percentage_with_currency_effect = ((total_gross_performance_with_currency_effect / time_weighted_average_investment_between_start_and_end_date_with_currency_effect) if (time_weighted_average_investment_between_start_and_end_date_with_currency_effect > 0) else Decimal('0'))
        fees_per_unit = (((fees - fees_at_start_date) / total_units) if (total_units > 0) else Decimal('0'))
        fees_per_unit_with_currency_effect = (((fees_with_currency_effect - fees_at_start_date_with_currency_effect) / total_units) if (total_units > 0) else Decimal('0'))
        net_performance_percentage = ((total_net_performance / time_weighted_average_investment_between_start_and_end_date) if (time_weighted_average_investment_between_start_and_end_date > 0) else Decimal('0'))
        net_performance_percentage_with_currency_effect_map = {}
        net_performance_with_currency_effect_map = {}
        for date_range in ['1d', '1y', '5y', 'max', 'mtd', 'wtd', 'ytd', *[(lambda date: _format_date(date, 'yyyy'))(_x) for _x in [_x for _x in _each_year_of_interval({'end': end, 'start': start}) if (lambda date: (not _is_this_year(date)))(_x)]]]:
            date_interval = _get_interval_from_date_range(date_range)
            end_date = (date_interval.get('endDate') if isinstance(date_interval, dict) else date_interval.end_date)
            start_date = (date_interval.get('startDate') if isinstance(date_interval, dict) else date_interval.start_date)
            if _is_before(start_date, start):
                start_date = start
            range_end_date_string = _format_date(end_date, DATE_FORMAT)
            range_start_date_string = _format_date(start_date, DATE_FORMAT)
            current_values_at_date_range_start_with_currency_effect = (current_values_with_currency_effect[range_start_date_string] if current_values_with_currency_effect[range_start_date_string] is not None else Decimal('0'))
            investment_values_accumulated_at_start_date_with_currency_effect = (investment_values_accumulated_with_currency_effect[range_start_date_string] if investment_values_accumulated_with_currency_effect[range_start_date_string] is not None else Decimal('0'))
            gross_performance_at_date_range_start_with_currency_effect = (current_values_at_date_range_start_with_currency_effect - investment_values_accumulated_at_start_date_with_currency_effect)
            average = Decimal('0')
            day_count = 0
            i = (len(self.chart_dates) - 1)
            while i >= 0:
                date = self.chart_dates[i]
                if (date > range_end_date_string):
                    continue
                elif (date < range_start_date_string):
                    break
                if (isinstance(investment_values_accumulated_with_currency_effect[date], Decimal) and (investment_values_accumulated_with_currency_effect[date] > 0)):
                    average = (average + (investment_values_accumulated_with_currency_effect[date] + gross_performance_at_date_range_start_with_currency_effect))
                    day_count += 1
                i -= 1
            if (day_count > 0):
                average = (average / day_count)
            net_performance_with_currency_effect_map[date_range] = ((net_performance_values_with_currency_effect[range_end_date_string] - (Decimal('0') if (date_range == 'max') else ((net_performance_values_with_currency_effect[range_start_date_string] if net_performance_values_with_currency_effect[range_start_date_string] is not None else Decimal('0'))))) if (net_performance_values_with_currency_effect[range_end_date_string] - (Decimal('0') if (date_range == 'max') else ((net_performance_values_with_currency_effect[range_start_date_string] if net_performance_values_with_currency_effect[range_start_date_string] is not None else Decimal('0'))))) is not None else Decimal('0'))
            net_performance_percentage_with_currency_effect_map[date_range] = ((net_performance_with_currency_effect_map[date_range] / average) if (average > 0) else Decimal('0'))

        return {'currentValues': current_values, 'currentValuesWithCurrencyEffect': current_values_with_currency_effect, 'feesWithCurrencyEffect': fees_with_currency_effect, 'grossPerformancePercentage': gross_performance_percentage, 'grossPerformancePercentageWithCurrencyEffect': gross_performance_percentage_with_currency_effect, 'initialValue': initial_value, 'initialValueWithCurrencyEffect': initial_value_with_currency_effect, 'investmentValuesAccumulated': investment_values_accumulated, 'investmentValuesAccumulatedWithCurrencyEffect': investment_values_accumulated_with_currency_effect, 'investmentValuesWithCurrencyEffect': investment_values_with_currency_effect, 'netPerformancePercentage': net_performance_percentage, 'netPerformancePercentageWithCurrencyEffectMap': net_performance_percentage_with_currency_effect_map, 'netPerformanceValues': net_performance_values, 'netPerformanceValuesWithCurrencyEffect': net_performance_values_with_currency_effect, 'netPerformanceWithCurrencyEffectMap': net_performance_with_currency_effect_map, 'timeWeightedInvestmentValues': time_weighted_investment_values, 'timeWeightedInvestmentValuesWithCurrencyEffect': time_weighted_investment_values_with_currency_effect, 'totalAccountBalanceInBaseCurrency': total_account_balance_in_base_currency, 'totalDividend': total_dividend, 'totalDividendInBaseCurrency': total_dividend_in_base_currency, 'totalInterest': total_interest, 'totalInterestInBaseCurrency': total_interest_in_base_currency, 'totalInvestment': total_investment, 'totalInvestmentWithCurrencyEffect': total_investment_with_currency_effect, 'totalLiabilities': total_liabilities, 'totalLiabilitiesInBaseCurrency': total_liabilities_in_base_currency, 'grossPerformance': total_gross_performance, 'grossPerformanceWithCurrencyEffect': total_gross_performance_with_currency_effect, 'hasErrors': ((total_units > 0) and (((not initial_value) or (not unit_price_at_end_date)))), 'netPerformance': total_net_performance, 'timeWeightedInvestment': time_weighted_average_investment_between_start_and_end_date, 'timeWeightedInvestmentWithCurrencyEffect': time_weighted_average_investment_between_start_and_end_date_with_currency_effect}
