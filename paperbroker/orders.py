"""

    Just a few ordering classes. Again, minimal logic.

"""

from math import copysign
from .assets import Asset, asset_factory
from .quotes import Quote
import itertools

_order_counter = itertools.count(1)

class Leg(object):
    def __init__(self, asset: Asset, quantity: int, order_type: str, price: float = None):

        # automatically correct the signs of the quantity and price
        if not order_type:
            raise Exception("Leg: order_type is required")
        
        asset = asset_factory(asset)
        if asset is None:
            raise Exception("Leg: asset is required")
            
        if order_type[0] == 's':
            quantity = abs(quantity) * -1
            price = (abs(price) * -1) if price is not None else None
        else:
            quantity = abs(quantity) * 1
            price = (abs(price) * 1) if price is not None else None

        self.asset = asset
        self.quantity = quantity
        self.order_type = order_type
        self.price = price


class Order(object):
    def __init__(self, legs = None, price=None, condition='market', trail = 0.0, trail_is_percent = False, trail_best=None, status='open', time_in_force='day'):
        self.order_id = f"PB-{next(_order_counter)}"
        self.legs = legs if legs is not None else []
        self.status = 'open'
        self.price = float(price) if price is not None else None
        self.condition = condition
        if condition == 'trailing_stop':
            if trail <= 0:
                raise ValueError("Order Rejected: if using condition = 'trailing_stop', then trail must be positve non-zero.")
            self.trail = trail
            self.trail_is_percent = trail_is_percent
            self.trail_best = trail_best
        else:
            self.trail = 0
            self.trail_is_percent = False
            self.trail_best = status
            self.time_in_force = time_in_force
        

    def duplicate(self, times=1):
        if self.price is not None:
            self.price *= times
        for leg in self.legs:
            leg.quantity *= times
        return self

    def buy_to_open(self, asset = None, quantity: int = None, price: float = None):
        return self.add_leg(asset=asset, quantity=quantity, price=price, order_type='bto')
    def sell_to_open(self, asset = None, quantity: int = None, price: float = None):
        return self.add_leg(asset=asset, quantity=quantity, price=price, order_type='sto')
    def buy_to_close(self, asset = None, quantity: int = None, price: float = None):
        return self.add_leg(asset=asset, quantity=quantity, price=price, order_type='btc')
    def sell_to_close(self, asset = None, quantity: int = None, price: float = None):
        return self.add_leg(asset=asset, quantity=quantity, price=price, order_type='stc')


    def add_leg(self, leg: Leg = None, asset=None, quantity: int = None, order_type: str = None, price: float = None):
        if leg is None:
            if quantity is None or int(quantity) == 0:
                raise ValueError("Order Rejected: quantity cannot be None or 0")
    
            # if asset is a list-like object, then take the first element in the list
            if asset and hasattr(asset, '__iter__') and not isinstance(asset, str):
                asset = asset[0] if len(asset) > 0 else None
    
            # if asset is a quote, replace it with the actual asset
            if asset and isinstance(asset, Quote):
                asset = asset.asset
    
            asset = asset_factory(asset)
            if asset is None:
                raise Exception("Order.add_leg: an asset is required")
    
            if len([_.asset.symbol for _ in self.legs if _.asset == asset]) > 0:
                raise Exception("Order.addLeg symbol {} already exists within this order".format(asset.symbol))
    
            quantity = int(quantity)
            self.legs.append(Leg(asset=asset, quantity=quantity, order_type=order_type, price=price))
            self.price = self.price + price * abs(quantity) if self.price is not None and price is not None else None
            added_qty = quantity
    
        else:
            if len([_.asset.symbol for _ in self.legs if _.asset == leg.asset]) > 0:
                raise Exception("Order.add_leg symbol {} already exists within this order".format(leg.asset.symbol))
            self.legs.append(leg)
            self.price = self.price + leg.price * abs(leg.quantity) if self.price is not None and leg.price is not None else None
            added_qty = leg.quantity
    
        if self.condition == 'trailing_stop' and (not self.trail_is_percent):
            if not getattr(self, "trail_is_batched", False):
                self.trail = abs(self.trail) * abs(added_qty)
                self.trail_is_batched = True
    
        return self
