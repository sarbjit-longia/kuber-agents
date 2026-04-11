"""
Execution Simulation (TP-014)

Realistic fill simulation including slippage and commission models.
Used by BacktestEngine to convert signal prices into realistic trade prices.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SlippageModel:
    """
    Slippage model for realistic fill simulation.

    model types:
        "fixed"  — fixed dollar amount per share (e.g. $0.01)
        "pct"    — percentage of price (e.g. 0.001 = 0.1%)
        "spread" — half-spread applied to market orders (same as pct internally)
    """
    model: str = "fixed"
    value: float = 0.01

    def apply(self, price: float, action: str) -> float:
        """
        Return the fill price after slippage.

        Buys pay more; sells receive less.
        """
        if self.model == "fixed":
            slippage = self.value
        elif self.model in ("pct", "spread"):
            slippage = price * self.value
        else:
            slippage = 0.0

        if action in ("BUY", "buy"):
            return price + slippage
        return max(0.0, price - slippage)


@dataclass
class CommissionModel:
    """
    Commission model.

    model types:
        "per_share" — fixed cost per share (e.g. $0.005)
        "flat"      — flat cost per order regardless of size
        "pct"       — percentage of notional value
    """
    model: str = "per_share"
    value: float = 0.005

    def calculate(self, price: float, size: float) -> float:
        """Return total commission for this fill."""
        if self.model == "per_share":
            return abs(size) * self.value
        elif self.model == "flat":
            return self.value
        elif self.model == "pct":
            return abs(price * size) * self.value
        return 0.0


class ExecutionSimulator:
    """
    Combines slippage + commission into a single execution simulator.

    Used by BacktestEngine to price entries and exits realistically.
    """

    def __init__(self, slippage: SlippageModel, commission: CommissionModel):
        self.slippage   = slippage
        self.commission = commission

    def apply_slippage(self, price: float, action: str) -> float:
        """Apply slippage to a limit/stop price to get a realistic fill price."""
        return self.slippage.apply(price, action)

    def total_cost(self, entry_price: float, size: float, action: str) -> float:
        """Entry slippage already reflected in entry_price; returns just commission."""
        return self.commission.calculate(entry_price, size)
