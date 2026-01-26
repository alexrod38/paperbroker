# -*- coding: utf-8 -*-
#file_name.py
#Python 3.10
"""
Author: Alex Rodriguez
Created: %(date)s
Modified: %(dates)s

Discription
------------
"""
import numpy as np
import matplotlib.pyplot as plt
import scipy as sci

from dataclasses import dataclass
from typing import List, Optional
from .orders import Order
from .logic.fill_order import fill_order  # adjust import to match your layout

@dataclass
class OCOGroup:
    orders: List[Order]
    oco_id: Optional[str] = None
    is_active: bool = True

    def evaluate(self, account, quote_adapter, estimator=None):
        """
        Try to fill one of the OCO child orders.
        If one fills, cancel the rest.
        Returns True if the group is finished (filled or canceled), else False.
        """
        if not self.is_active:
            return True

        for o in self.orders:
            if o.status != "open":
                continue

            # Use your existing fill_order logic
            fill_order(account=account, order=o, quote_adapter=quote_adapter, estimator=estimator)

            if o.status == "filled":
                # cancel all other open siblings
                for other in self.orders:
                    if other is not o and other.status == "open":
                        other.status = "canceled"
                self.is_active = False
                return True

        # still active (none filled yet)
        return False

