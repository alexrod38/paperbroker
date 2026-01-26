"""

    Specialized classes for assets. Anything that can be represented by a symbol.
    Overrides the == to make it easier
    Use asset_factory() if you don't know if an object is a string or an asset
    Logic within the asset classes is kept to a minimum to make it easier
      to learn from the code. Most is in /paperbroker/logic/

"""
import arrow
import re
from typing import Optional


def _norm_symbol(symbol: str) -> str:
    return re.sub(r"\s+", "", str(symbol).strip().upper())

def asset_factory(symbol=None, service: Optional[str] = None):
    """
    Create the appropriate asset based on symbol, and optionally stream service.
    - If service is provided, it takes precedence for asset class.
    - If service is None, fall back to original symbol-based logic (options vs Asset).
    """
    if symbol is None:
        return None

    if isinstance(symbol, Asset):
        return symbol

    sym = _norm_symbol(symbol)
    svc = (service or "").upper()

    # --- Service-aware routing (authoritative when present) ---
    if svc:
        if svc == "LEVELONE_EQUITIES":
            return Equity(sym)

        if svc in ("LEVELONE_OPTIONS", "LEVELONE_FUTURE_OPTIONS"):
            # Let symbol parsing determine Call/Put/Option details
            # (works for PaperBroker symbols; OCC support lives in Option parsing/normalization)
            return _option_from_symbol(sym)

#        if svc == "LEVELONE_FUTURES":
#            return Futures(sym)  # if you add it; otherwise return Asset(sym)
#
#        if svc == "LEVELONE_FOREX":
#            return Forex(sym)    # if you add it; otherwise return Asset(sym)

        # unknown service -> conservative fallback
        # don't guess; preserve old behavior:
        # (options vs asset)
        return _original_symbol_logic(sym)

    # --- Backward-compatible fallback (old behavior) ---
    return _original_symbol_logic(sym)


def _option_from_symbol(sym: str):
    if "P0" in sym:
        return Put(sym)
    if "C0" in sym:
        return Call(sym)
    return Option(sym)

def _original_symbol_logic(sym: str):
    if len(sym) > 8:
        return _option_from_symbol(sym)
    return Asset(sym)

"""
Asset: Assets are always identified by a symbol which uniquely identifies the asset and a type.
"""
class Asset():

    def __init__(self, symbol: str=None, asset_type: str=None):
        self.symbol = symbol.upper()
        self.asset_type = asset_type or 'asset'
        return

    def __eq__(self, other):
        """Override the default Equals behavior"""
        if isinstance(other, self.__class__):
            return self.symbol == other.symbol
        if isinstance(other, str):
            return self.symbol == other.upper()
        return False

    def __ne__(self, other):
        """Define a non-equality test"""
        return not self.__eq__(other)

"""
    Base class for any equities
"""
class Equity(Asset):
    def __init__(self, symbol: str):
        super().__init__(symbol, asset_type="equity")

"""
    Base class for any option derivative
"""
class Option(Asset):

    def __init__(self, symbol:str = None, underlying=None, option_type:str = None, strike:float = None, expiration_date = None):

        if symbol is not None:
            symbol = re.sub(r"\s+", "", str(symbol).strip().upper())

            # if a symbol is provided, then we create the asset based on the symbol

            r = symbol[::-1]

            self.strike = float(r[0:8][::-1]) / 1000
            self.option_type = 'call' if r[8] == 'C' else 'put'
            self.expiration_date = arrow.get(r[9:15][::-1], 'YYMMDD').format('YYYY-MM-DD')
            self.underlying = asset_factory(r[15:][::-1])

        else:

            # if not then we piece it together with the data we have

            underlying = asset_factory(underlying)

            if underlying is None:
                raise Exception('Option(Asset): An underlying is required')

            if option_type is None or option_type not in ['call', 'put']:
                raise Exception('Option(Asset): option_type is required and must be `call` or `put`')

            if strike is None or strike <= 0.0:
                raise Exception('Option(Asset): strike is required and must be > 0.0')

            if expiration_date is None:
                raise Exception('Option(Asset): expiration_date is required')

            # parse the date real quick to check on it
            try:
                expiration_date = arrow.get(expiration_date).format('YYMMDD')
            except Exception as e:
                raise Exception('Option(Asset): expiration_date is invalid')

            # build the symbol
            symbol = (underlying.symbol + expiration_date + option_type[0] + str(int(round(strike, 2) * 1000)).zfill(8)).upper()

            self.underlying = underlying
            self.option_type = option_type
            self.strike = float(strike)
            self.expiration_date = arrow.get(expiration_date, 'YYMMDD').format('YYYY-MM-DD')

        super(Option, self).__init__(symbol, self.option_type)

    def get_extrinsic_value(self, underlying_price=None, price=None):
        return (abs(price) - self.get_intrinsic_value(underlying_price=underlying_price)) if price is not None else None

    def get_intrinsic_value(self, underlying_price=None):

        if self.strike is None:
            return None

        if underlying_price is None:
            return None

        if self.option_type == 'call':
            return max(underlying_price - self.strike, 0)
        if self.option_type == 'put':
            return max(self.strike - underlying_price, 0)

        return None

    def get_days_to_expiration(self, as_of_date):
        return (arrow.get(self.expiration_date) - arrow.get(as_of_date)).days


class Put(Option):
    def __init__(self, symbol: str = None, underlying = None,
                 underlying_symbol: str = None, strike: float = None, expiration_date=None):
        super(Put, self).__init__(symbol=symbol, option_type='put', underlying = underlying, strike=strike, expiration_date=expiration_date)

class Call(Option):
    def __init__(self, symbol: str = None, underlying = None,
                 underlying_symbol: str = None, strike: float = None, expiration_date=None):
        super(Call, self).__init__(symbol=symbol, option_type='call', underlying = underlying, strike=strike, expiration_date=expiration_date)
