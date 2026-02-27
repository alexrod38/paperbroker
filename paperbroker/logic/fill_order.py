"""

    Order fill logic. Feels good but could use a through code review.

"""


from datetime import datetime   # for fallback timestamps
from ..orders import Order
from ..accounts import Account
from ..ledger import LedgerEntry, record_ledger_entry
from ..assets import Option
from ..positions import Position
from ..adapters.quotes import QuoteAdapter
from ..estimators import Estimator
from math import copysign
from .maintenance_margin import get_maintenance_margin

def _cash_delta_for_leg(cost_basis: float, quantity: int, is_option: bool) -> float:
    """
    Returns cash delta (positive increases cash, negative spends cash).
    cost_basis is signed-per-unit in your current fill_order (sell legs negative, buy legs positive). :contentReference[oaicite:3]{index=3}
    """
    mult = 100.0 if is_option else 1.0
    # replicate your existing cash-impact sign convention :contentReference[oaicite:4]{index=4}
    return -abs(cost_basis * quantity) * copysign(1, quantity) * mult

def fill_order(account: Account = None, order: Order = None, quote_adapter:QuoteAdapter=None, estimator:Estimator=None):
    if account is None:
        raise Exception("logic.fill_order: must provide an account.")

    if order is None or len(order.legs) == 0:
        raise Exception("logic.fill_order: Orders must have one or more than one leg.")

    if quote_adapter is None:
        raise Exception("logic.fill_order: must provide a quote_adapter")

    if estimator is None:
        estimator = Estimator()

    # figure out the best expected price the order would fill at
    leg_prices = {}
    order_price = 0.0
    filled = False

    for leg in order.legs:
        # signed per-unit price (sell legs negative, buy legs positive)
        px = estimator.estimate(quote_adapter.get_quote(leg.asset), quantity=leg.quantity)
        px = px * copysign(1, leg.quantity)
        leg_prices[leg] = px
        order_price += px * abs(leg.quantity)   #cost of order: how much this order would cost now in the market
        
    if order.condition == 'trailing_stop':
        order.trail_best = order_price if order.trail_best is None else min(order.trail_best, order_price)
        if order.trail_is_percent:
            trail_amt = abs(order.trail_best) * (order.trail / 100.0)
        else:
            trail_amt = abs(order.trail)
        order.price = order.trail_best + trail_amt
                
        # order.price is the limit/stop price of the order
    if order.condition == 'market' or (order.condition == 'limit' and order.price is not None and order_price <= order.price) or (order.condition == 'stop' and order.price is not None and order_price >= order.price) or (order.condition == 'trailing_stop' and order.price is not None and order_price >= order.price):
        
        # --- NEW: defer fill until next quote/message ---
        # We use quote.quote_date (if available) as the "message time".
        submit_ts = getattr(order, "_pb_submit_ts", None)

        # compute "current quote time" as max quote_date over legs
        now_ts = None
        for leg in order.legs:
            q = quote_adapter.get_quote(leg.asset)
            ts = getattr(q, "quote_date", None)
            if ts is not None and (now_ts is None or ts > now_ts):
                now_ts = ts

        if submit_ts is None:
            # first time we *could* fill -> mark submit time and wait for next message
            setattr(order, "_pb_submit_ts", now_ts or datetime.utcnow())
            return account

        # only fill once we've seen a strictly newer message
        if now_ts is not None and now_ts <= submit_ts:
            return account
        
        # --- NEW: insufficient funds check BEFORE any mutation ---
        projected_delta = 0.0
        for leg in order.legs:
            cost_basis = leg_prices[leg]
            projected_delta += _cash_delta_for_leg(
                cost_basis=cost_basis,
                quantity=leg.quantity,
                is_option=isinstance(leg.asset, Option),
            )

        cash_before_all = float(getattr(account, "cash", 0.0))
        cash_after_all = cash_before_all + projected_delta

        if cash_after_all < 0:
            order.status = "rejected"
            # optional: attach reason for debugging
            setattr(order, "reject_reason", f"insufficient_funds cash={cash_before_all:.2f} delta={projected_delta:.2f}")
            return account

        for leg in order.legs:
            
            # Pre-fill state for ledger
            cash_before = account.cash
            # position_qty_before = sum of matching positions
            position_qty_before = sum(p.quantity for p in account.positions if p.asset == leg.asset)
            # Snapshot quote once (for both pricing and ledger)
            quote = quote_adapter.get_quote(leg.asset)

            cost_basis = leg_prices[leg]

            if leg.order_type[0].lower() == 'b' and (leg.quantity < 0 or cost_basis < 0):
                raise Exception(
                    "logic.fill_order: BTO or BTC legs must be positive quantity and positive price")

            if leg.order_type[0].lower() == 's' and (leg.quantity > 0 or cost_basis > 0):
                raise Exception(
                    "logic.fill_order: STO or STC legs must be negative quantity and negative price")
            
            # Cash impact
            if isinstance(leg.asset, Option):
                account.cash -= abs(cost_basis * leg.quantity) * copysign(1, leg.quantity) * 100
                multiplier = 100
            else:
                account.cash -= abs(cost_basis * leg.quantity) * copysign(1, leg.quantity)
                multiplier = 1
            
            # ---- Fees / commissions (modeled per asset type)
            # Example: options commission $0.65 per contract; equities $0.00
            commission = 0.0
            fees = 0.0
            if isinstance(leg.asset, Option):
                commission = 0.65 * abs(leg.quantity)
                fees = 0.01 * abs(leg.quantity)
            
            cash_after_trade = account.cash  # after execution cash impact, before fees
            fees_total = float(commission) + float(fees)
            
            # Fees always reduce cash, regardless of buy/sell direction
            if fees_total:
                account.cash -= fees_total

            # if the leg is opening, then create a position for each leg
            if leg.order_type.lower() in ['bto', 'sto']:

                account.positions.append(Position(leg.asset, leg.quantity, cost_basis, quote=quote_adapter.get_quote(leg.asset)))
                # Opening trades do not realize P&L
                realized_pnl_for_this_leg = None

            elif leg.order_type.lower() in ['btc', 'stc']:

                closable_positions = [position for position in account.positions if
                                      position.asset == leg.asset and copysign(1, position.quantity) == (copysign(1, leg.quantity) * -1)]

                if len(closable_positions) == 0:
                    raise Exception("logic.fill_order: There are no available positions to close.")

                # add up the quantities available
                quantity_available_to_close = sum([position.quantity for position in closable_positions])

                if abs(quantity_available_to_close) < abs(leg.quantity):
                    raise Exception("logic.fill_order: There are not enough open positions to close.")

                # iterate through the positions and reduce the quantity by the leg quantity
                quantity_to_close_remaining = abs(leg.quantity)
                for position in closable_positions:
                    if quantity_to_close_remaining > 0:
                        quantity_can_close = abs(position.quantity)
                        quantity_to_close = min(quantity_to_close_remaining, quantity_can_close)
                        position.quantity += copysign(1, position.quantity) * -1 * quantity_to_close
                        quantity_to_close_remaining -= quantity_to_close
                realized_pnl_for_this_leg = None  # TODO: compute later if desired
            
            cash_after = account.cash
            trade_cash = cash_after_trade - cash_before
            net_cash = cash_after - cash_before
            position_qty_after = sum(p.quantity for p in account.positions if p.asset == leg.asset)
            gross_cash = net_cash
            
            # Timestamp from quote or fallback
            quote = quote_adapter.get_quote(leg.asset)
            timestamp = quote.quote_date if quote and hasattr(quote, "quote_date") else datetime.utcnow()
            
            entry = LedgerEntry(
                timestamp = timestamp,
                account_id = account.account_id,
                order_id = order.order_id,
                symbol = leg.asset.symbol,
                asset_type = getattr(leg.asset, "asset_type", None),
                underlying_symbol = getattr(getattr(leg.asset, "underlying", None), "symbol", None),
                quote_price = getattr(quote, "price", None) if quote else None,
                quote_bid   = getattr(quote, "bid", None) if quote else None,
                quote_ask   = getattr(quote, "ask", None) if quote else None,
                side = leg.order_type.lower(),
                quantity = leg.quantity,
                multiplier = multiplier,
                fill_price = abs(cost_basis),
                commission  = float(commission),
                fees        = float(fees),
                fees_total  = float(fees_total),
                trade_cash  = float(trade_cash),
                net_cash    = float(net_cash),
                gross_cash = gross_cash,
                realized_pnl = realized_pnl_for_this_leg,
                position_qty_before = position_qty_before,
                position_qty_after = position_qty_after,
            )
            
            record_ledger_entry(account, entry)
        filled = True

    # filter out any positions that are completely closed
    
    account.positions = [position for position in account.positions if position.quantity != 0]
    account.maintenance_margin = get_maintenance_margin(positions=account.positions, quote_adapter=quote_adapter)
    
    if filled:
        order.status = 'filled'

    return account

