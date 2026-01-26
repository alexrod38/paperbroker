"""

    Uses the supplied positions to estimate the total cumulative margin requirement.

    Uses each basic strategy to calculate the margin of each and adds them up.

"""



from ..assets import Asset, Option, Call, Put
from ..adapters.quotes.QuoteAdapter import QuoteAdapter
from .group_into_basic_strategies import *



def get_maintenance_margin(strategies=None, positions=None, quote_adapter:QuoteAdapter=None):

    if positions is None: positions = list()
    if strategies is None: strategies = group_into_basic_strategies(positions)

    #start the calculation off
    total_margin_requirement = 0.0

    for strategy in strategies:

        if strategy.strategy_type == 'asset' \
                and strategy.direction == 'long':
            # no margin requirements for long anything
            total_margin_requirement += 0

        elif strategy.strategy_type == 'asset' \
                and strategy.asset.asset_type == 'equity' \
                and strategy.direction == 'short':
            # non-option shorts have a margin requirement equal to the cost to repurchase
            q = quote_adapter.get_quote(strategy.asset)
            if q is None or q.price is None:
                raise Exception("Missing price for margin on {}".format(strategy.asset.symbol))
            total_margin_requirement += abs(strategy.quantity) * q.price

        elif strategy.strategy_type == 'covered':
            # no margin requirements for covered strategies
            total_margin_requirement += 0

        elif strategy.strategy_type == 'spread' \
                and strategy.spread_type == 'debit':
            # no margin requirements for debit spreads
            total_margin_requirement += 0

        elif strategy.strategy_type == 'spread' \
                and strategy.spread_type == 'credit' \
                and strategy.option_type=='put':
            # credit put spreads use the width of the strikes
            spread_width = abs(strategy.sell_option.strike - strategy.buy_option.strike)
            credit = abs(quote_adapter.get_quote(strategy.sell_option).price - quote_adapter.get_quote(strategy.buy_option).price)
            
            per_share_margin = spread_width - credit
            total_margin_requirement += per_share_margin * 100

        elif strategy.strategy_type == 'spread' \
                and strategy.spread_type == 'credit' \
                and strategy.option_type == 'call':
            # credit call spreads use the width of the strikes
            total_margin_requirement += (strategy.buy_option.strike - strategy.sell_option.strike) * 100

        elif strategy.strategy_type == 'asset' \
                and strategy.direction=='short' \
                and isinstance(strategy.asset, Put):
            # Naked short put margin
            put_asset = strategy.asset
            contracts = abs(strategy.quantity)

            put_quote = quote_adapter.get_quote(put_asset)
            underlying_quote = quote_adapter.get_quote(put_asset.underlying)

            if put_quote is None or underlying_quote is None \
               or put_quote.price is None or underlying_quote.price is None:
                raise Exception("Cannot compute margin for naked put: missing quote data")

            option_price = abs(put_quote.price)
            underlying_price = underlying_quote.price
            strike = put_asset.strike

            # Amount out of the money for a put: max(0, S - K)
            otm = max(0.0, underlying_price - strike)

            per_share_margin = option_price + max(
                0.20 * underlying_price - otm,
                0.10 * strike
            )

            total_margin_requirement += per_share_margin * 100 * contracts

        elif strategy.strategy_type == 'asset' \
                and strategy.direction=='short' \
                and isinstance(strategy.asset, Call):
            # Naked short call margin
            call_asset = strategy.asset
            contracts = abs(strategy.quantity)

            call_quote = quote_adapter.get_quote(call_asset)
            underlying_quote = quote_adapter.get_quote(call_asset.underlying)

            if call_quote is None or underlying_quote is None \
               or call_quote.price is None or underlying_quote.price is None:
                raise Exception("Cannot compute margin for naked call: missing quote data")

            option_price = abs(call_quote.price)
            underlying_price = underlying_quote.price
            strike = call_asset.strike

            # Amount out of the money for a call: max(0, K - S)
            otm = max(0.0, strike - underlying_price)

            per_share_margin = option_price + max(
                0.20 * underlying_price - otm,
                0.10 * underlying_price
            )

            total_margin_requirement += per_share_margin * 100 * contracts

        else:
            raise Exception('A strategy was provided that we do not know how to calculate the maintenance margin for')

    return total_margin_requirement
