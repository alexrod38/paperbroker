# -*- coding: utf-8 -*-
"""Schwab stream-backed QuoteAdapter (callback-fed cache).

Option B integration:
- API_streamer + StreamManager own stream lifecycle and message parsing.
- Service handlers call `on_market_data(data)` with translated dict keys.
- PaperBroker pulls prices via `get_quote()`.

Expected callback payload (from API_streamer.StreamHandler):
  {
    "service": "...",
    "symbol": "...",
    "timestamp": ...,
    "Bid Price": ...,
    "Ask Price": ...,
    "Last Price": ...,
    # optional:
    "Mark": ...,
    "Mark Price": ...,
    "Bid Size": ...,
    "Ask Size": ...,
    "Underlying Price": ...
  }

NOTE: assets.py parsing is enhanced (see assets_patched.py) to normalize OCC option symbols
with padded spaces like "AAPL  250119C00150000".
"""

import threading
import arrow

from .QuoteAdapter import QuoteAdapter
from ...assets import asset_factory
from ...quotes import quote_factory_from_service


class SchwabCallbackQuoteAdapter(QuoteAdapter):
    """
    Pull-based QuoteAdapter for PaperBroker + push-based callback receiver for Schwab stream.

    - No start/stop/subscribe logic (StreamManager owns that).
    - StreamHandler calls .on_market_data(translated_dict).
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        self._equity_quotes = {}   # symbol -> Quote
        self._option_quotes = {}   # normalized option symbol -> OptionQuote
        self._other_quotes = {}    # other quotes
        self._last_ts = {}         # symbol -> timestamp (as provided)

    def on_market_data(self, data: dict):
        service = (data.get("service") or "").upper()
        raw_symbol = data.get("symbol")
        if not raw_symbol or not service:
            return
        
        # 🚫 Ignore chart and non-quote services
        if not service.startswith("LEVELONE"):
            return
        
        def _num(x):
            try:
                return float(x) if x is not None else None
            except Exception:
                return None
    
        bid = _num(data.get("Bid Price") or data.get("Bid"))
        ask = _num(data.get("Ask Price") or data.get("Ask"))
        last = _num(data.get("Last Price") or data.get("Last"))
        mark = _num(data.get("Mark Price") or data.get("Mark"))
    
        price = mark if mark is not None else last
    
        bid_size = data.get("Bid Size")
        ask_size = data.get("Ask Size")
        try: bid_size = int(bid_size) if bid_size is not None else 0
        except Exception: bid_size = 0
        try: ask_size = int(ask_size) if ask_size is not None else 0
        except Exception: ask_size = 0
    
        underlying_price = _num(
            data.get("Underlying Price") or data.get("Underlying") or data.get("UnderlyingPrice")
        )
    
        # option extras (API-first; your OptionQuote handles compute fallback)
        delta = _num(data.get("Delta"))
        iv    = _num(data.get("Volatility") or data.get("IV") or data.get("Implied Volatility"))
        gamma = _num(data.get("Gamma"))
        vega  = _num(data.get("Vega"))
        theta = _num(data.get("Theta"))
        rho   = _num(data.get("Rho"))
        days_to_exp = _num(data.get("Days To Expiration") or data.get("Days to Expiration"))
        intrensic = _num(data.get("Money Intrinsic Value") or data.get("Intrinsic Value"))
        strike = _num(data.get("Strike Price") or data.get("Strike"))
        contract_type = data.get("Contract Type")  # if present
    
        quote_date = arrow.get(data["timestamp"]).format("YYYY-MM-DD")
    
        q = quote_factory_from_service(
            service=service,
            quote_date=quote_date,
            symbol=raw_symbol,
            price=price, bid=bid, ask=ask,
            bid_size=bid_size, ask_size=ask_size,
            underlying_price=underlying_price,
            delta=delta, iv=iv, gamma=gamma, vega=vega, theta=theta, rho=rho,
            days_to_exp=days_to_exp, intrensic=intrensic, strike=strike,
            contract_type=contract_type,
        )
    
        sym = q.asset.symbol.upper()  # canonical normalized symbol from asset_factory(service=...)
        with self._lock:
            qt = getattr(q, "quote_type", None)
            if qt == "option":
                self._option_quotes[sym] = q
            elif qt == "equity":
                self._equity_quotes[sym] = q
            else:
                self._other_quotes[sym] = q
            
            self._last_ts[sym] = data.get("timestamp")

    # --- QuoteAdapter contract ---

    def get_quote(self, asset):
        sym = asset_factory(asset).symbol.upper()
        with self._lock:
            return self._option_quotes.get(sym) or self._equity_quotes.get(sym) or self._other_quotes.get(sym)

    def get_options(self, underlying_asset=None, expiration_date=None):
        with self._lock:
            opts = list(self._option_quotes.values())

        if underlying_asset is None and expiration_date is None:
            return opts

        underlying = asset_factory(underlying_asset).symbol.upper() if underlying_asset else None
        exp = arrow.get(expiration_date).format("YYYY-MM-DD") if expiration_date else None

        out = []
        for oq in opts:
            try:
                opt = oq.asset
                if underlying and opt.underlying.symbol.upper() != underlying:
                    continue
                if exp and opt.expiration_date != exp:
                    continue
                out.append(oq)
            except Exception:
                continue
        return out

    def get_expiration_dates(self, underlying_asset=None):
        exps = set()
        for oq in self.get_options(underlying_asset=underlying_asset):
            try:
                exps.add(oq.asset.expiration_date)
            except Exception:
                pass
        return sorted(exps)
