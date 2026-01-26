"""

    Objects representing quotes. Simple right now.

"""
import arrow
import math
from .assets import asset_factory, Option
from .logic.ivolat3_option_greeks import get_option_greeks


def quote_factory(quote_date, asset, price=None, bid=0.0, ask=0.0, bid_size=0, ask_size=0, underlying_price=None):
    asset = asset_factory(asset)
    if isinstance(asset, Option):
        return OptionQuote(quote_date, asset, price=price, bid=bid, ask=ask, bid_size=bid_size, ask_size=ask_size, underlying_price=underlying_price)
    else:
        return Quote(quote_date, asset, price=price, bid=bid, ask=ask, bid_size=bid_size, ask_size=ask_size)

def quote_factory_from_service(
    service: str,
    quote_date,
    symbol,
    price=None, bid=0.0, ask=0.0, bid_size=0, ask_size=0,
    underlying_price=None,
    # option extras if present
    delta=None, iv=None, gamma=None, vega=None, theta=None, rho=None,
    days_to_exp=None, intrensic=None, strike=None, contract_type=None,
):
    svc = (service or "").upper()
    
    if svc == "LEVELONE_EQUITIES":
        asset = asset_factory(symbol=symbol, service=svc)
        return EquityQuote(quote_date, asset, price=price, bid=bid, ask=ask, bid_size=bid_size, ask_size=ask_size)
    
    if svc in ("LEVELONE_OPTIONS", "LEVELONE_FUTURE_OPTIONS"):
        asset = asset_factory(symbol=symbol, service=svc)   # still creates the instrument object, but no longer decides “option vs not”
        return OptionQuote(
            quote_date, asset,
            price=price, bid=bid, ask=ask, bid_size=bid_size, ask_size=ask_size,
            underlying_price=underlying_price,
            delta=delta, iv=iv, gamma=gamma, vega=vega, theta=theta, rho=rho,
            days_to_exp=days_to_exp, intrensic=intrensic, strike=strike,
            contract_type=contract_type,
        )

    # equities/futures/forex: for now all map to Quote
    # (later you can make FuturesQuote/ForexQuote subclasses if you want)
    asset = asset_factory(symbol=symbol, service=svc)
    return Quote(quote_date, asset, price=price, bid=bid, ask=ask, bid_size=bid_size, ask_size=ask_size)


class Quote(object):

    def __init__(self, quote_date, asset, price=None, bid=0.0, ask=0.0, bid_size=0, ask_size=0):
        self.asset = asset_factory(asset)
        self.quote_date = quote_date
        self.bid = float(bid) if bid is not None else 0.0
        self.ask = float(ask) if ask is not None else 0.0
        self.bid_size = float(bid_size) if bid_size is not None else 0
        self.ask_size = float(ask_size) if ask_size is not None else 0
        self.price = float(price) if price is not None else None

        if self.price is None and self.bid + self.ask != 0.0:
            self.price = ((self.bid + self.ask) / 2)

        self.delta = 1.0

    def is_priceable(self):
        return self.price is not None


class EquityQuote(Quote):
    quote_type = "equity"


class OptionQuote(Quote):
    def __init__(self, quote_date, asset, price = None, bid = 0.0, ask = 0.0, bid_size = 0, ask_size = 0, delta = None, iv = None, gamma = None, vega = None, theta = None, rho = None, underlying_price = None, days_to_exp = None, intrensic = None, strike = None, contract_type = None):
        super(OptionQuote, self).__init__(quote_date=quote_date, asset=asset, price=price, bid=bid, ask=ask, bid_size=bid_size, ask_size=ask_size)
        if not isinstance(self.asset, Option):
            raise Exception("OptionQuote(Quote): Must pass an option to create an option quote");
        self.quote_type = 'option'
        self.days_to_expiration = days_to_exp if days_to_exp is not None else self.asset.get_days_to_expiration(quote_date)
        self.underlying_price = underlying_price
        self.strike = strike if strike is not None else self.asset.strike
        
        self.delta = delta
        self.iv = iv
        self.gamma = gamma
        self.vega = vega
        self.theta = theta
        self.rho = rho
        self.intrensic = intrensic
        self.c_type = contract_type if contract_type is not None else self.asset.option_type
        
        def _safe(x):
            if x is None:
                return None
            try:
                x = float(x)
            except Exception:
                return None
            return None if math.isnan(x) else x
        
        needs_compute = any(x is None for x in (self.delta, self.iv, self.gamma, self.vega, self.theta, self.rho)
)
        
        if needs_compute and self.is_priceable() and self.underlying_price is not None:
            greeks = get_option_greeks(self.asset.option_type, self.strike, self.underlying_price,
                                       self.days_to_expiration, self.price, dividend=0.0)
        
            g = _safe(greeks.get("delta"))
            if self.delta is None and g is not None:
                self.delta = g * 100
        
            g = _safe(greeks.get("iv"))
            if self.iv is None and g is not None:
                self.iv = g * 100
        
            g = _safe(greeks.get("gamma"))
            if self.gamma is None and g is not None:
                self.gamma = g * 100
        
            g = _safe(greeks.get("vega"))
            if self.vega is None and g is not None:
                self.vega = g * 100
        
            g = _safe(greeks.get("theta"))
            if self.theta is None and g is not None:
                self.theta = g * 100
        
            g = _safe(greeks.get("rho"))
            if self.rho is None and g is not None:
                self.rho = g * 100

    def has_greeks(self):
        return self.iv is not None

    def get_intrinsic_value(self, underlying_price=None):
        if self.intrensic is not None:
            return self.intrensic
        up = underlying_price if underlying_price is not None else self.underlying_price
        return self.asset.get_intrinsic_value(underlying_price=up)

    def get_extrinsic_value(self, underlying_price=None):
        if self.intrensic is not None and self.price is not None:
            return self.price - self.intrensic
        up = underlying_price if underlying_price is not None else self.underlying_price
        return self.asset.get_extrinsic_value(underlying_price=up, price=self.price)

    @property
    def expiration_date(self):
        return self.asset.expiration_date
