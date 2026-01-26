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
# paperbroker/logic/ledger.py

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional, Any, List, TYPE_CHECKING

if TYPE_CHECKING:
    # Only for type hints; avoids import cycles at runtime
    from .accounts import Account


@dataclass
class LedgerEntry:
    """
    One execution record (typically one filled leg of an order).

    This is intentionally generic and denormalized so you can:
      - group by account_id to simulate strategy performance (one account per strategy)
      - group by symbol / side / etc. for stats
    """
    # Meta
    timestamp: Optional[Any]       # usually a datetime or arrow object from Quote.quote_date
    account_id: Optional[str]
    order_id: Optional[str]

    # Instrument
    symbol: str                    # e.g. 'AAPL' or OCC option symbol
    asset_type: Optional[str]      # 'equity', 'call', 'put', etc.
    underlying_symbol: Optional[str]  # for options; None for pure equities

    # Trade info
    side: str                      # 'bto', 'sto', 'stc', 'btc', etc.
    quantity: float                # contracts or shares (signed or unsigned – your choice)
    multiplier: int                # 1 for stock, 100 for standard equity options
    fill_price: float              # per-share or per-contract price (you decide signed/unsigned)

    # Cash / P&L
    gross_cash: float              # change in account.cash due to this leg
    realized_pnl: Optional[float]  # realized P&L for this leg (closing trades), else None

    # Position context (optional but handy)
    position_qty_before: Optional[float]
    position_qty_after: Optional[float]

    def to_dict(self) -> dict:
        """Convenience for turning entries into dicts (for DataFrames, CSV, etc.)."""
        return asdict(self)


def ensure_ledger(account: Account) -> None:
    """
    Make sure the account has a .ledger list. This is defensive in case older
    pickled accounts don't have the attribute yet.
    """
    if not hasattr(account, "ledger") or account.ledger is None:
        account.ledger = []  # type: ignore[attr-defined]


def record_ledger_entry(account: Account, entry: LedgerEntry) -> None:
    """
    Append a ledger entry to the account's ledger.
    """
    ensure_ledger(account)
    account.ledger.append(entry)  # type: ignore[attr-defined]


def export_ledger_to_csv(account: Account, filepath: str) -> None:
    """
    Export the account's ledger to a CSV file (simple flat format).
    """
    import csv

    ensure_ledger(account)
    rows: List[dict] = [e.to_dict() for e in account.ledger]  # type: ignore[attr-defined]
    if not rows:
        # Nothing to write; create an empty file with just a header
        fieldnames = [f.name for f in LedgerEntry.__dataclass_fields__.values()]
        with open(filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
        return

    fieldnames = list(rows[0].keys())
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def ledger_to_dicts(account: Account) -> List[dict]:
    """
    Returns the ledger as a list of dicts (useful for Pandas, JSON, etc.).
    """
    ensure_ledger(account)
    return [e.to_dict() for e in account.ledger]  # type: ignore[attr-defined]

