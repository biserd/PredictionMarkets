"""
Signal engine for complete-set arbitrage opportunity detection.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, List
from datetime import datetime
from enum import Enum

from src.marketdata.orderbook_state import MarketBook
from src.config import StrategyConfig


class SignalDecision(Enum):
    TRADE = "TRADE"
    SKIP_NO_QUOTES = "SKIP_NO_QUOTES"
    SKIP_INSUFFICIENT_EDGE = "SKIP_INSUFFICIENT_EDGE"
    SKIP_INSUFFICIENT_DEPTH = "SKIP_INSUFFICIENT_DEPTH"
    SKIP_IN_COOLDOWN = "SKIP_IN_COOLDOWN"
    SKIP_IN_FLIGHT = "SKIP_IN_FLIGHT"
    SKIP_MARKET_INACTIVE = "SKIP_MARKET_INACTIVE"


@dataclass
class TradeSignal:
    market_id: str
    timestamp: float
    decision: SignalDecision
    yes_ask: Optional[Decimal]
    no_ask: Optional[Decimal]
    yes_size: Optional[Decimal]
    no_size: Optional[Decimal]
    sum_cost: Optional[Decimal]
    edge: Optional[Decimal]
    cost_buffer: Decimal
    reason: str

    @property
    def is_tradeable(self) -> bool:
        return self.decision == SignalDecision.TRADE


class SignalEngine:
    """
    Detects complete-set arbitrage opportunities.
    
    A complete-set arb exists when:
    - YES_ask + NO_ask + fees < $1.00
    - Both sides have sufficient depth
    - Market is not in cooldown or has in-flight orders
    """

    def __init__(self, config: StrategyConfig, fee_rate: Decimal = Decimal("0.02")):
        self.config = config
        self.fee_rate = fee_rate
        self._cooldowns: dict[str, float] = {}
        self._in_flight: set[str] = set()

    def evaluate(self, market: MarketBook) -> TradeSignal:
        """
        Evaluate a market for arbitrage opportunity.
        Returns a TradeSignal indicating whether to trade and why.
        """
        now = datetime.now().timestamp()

        if not market.active:
            return TradeSignal(
                market_id=market.market_id,
                timestamp=now,
                decision=SignalDecision.SKIP_MARKET_INACTIVE,
                yes_ask=None,
                no_ask=None,
                yes_size=None,
                no_size=None,
                sum_cost=None,
                edge=None,
                cost_buffer=self.config.cost_buffer,
                reason="Market is inactive",
            )

        if not market.has_valid_quotes:
            return TradeSignal(
                market_id=market.market_id,
                timestamp=now,
                decision=SignalDecision.SKIP_NO_QUOTES,
                yes_ask=market.yes_token.best_ask_price,
                no_ask=market.no_token.best_ask_price,
                yes_size=market.yes_token.best_ask_size,
                no_size=market.no_token.best_ask_size,
                sum_cost=None,
                edge=None,
                cost_buffer=self.config.cost_buffer,
                reason="Missing quotes for one or both tokens",
            )

        if market.market_id in self._in_flight:
            return TradeSignal(
                market_id=market.market_id,
                timestamp=now,
                decision=SignalDecision.SKIP_IN_FLIGHT,
                yes_ask=market.yes_token.best_ask_price,
                no_ask=market.no_token.best_ask_price,
                yes_size=market.yes_token.best_ask_size,
                no_size=market.no_token.best_ask_size,
                sum_cost=market.sum_ask_cost,
                edge=None,
                cost_buffer=self.config.cost_buffer,
                reason="Orders currently in flight",
            )

        cooldown_until = self._cooldowns.get(market.market_id, 0)
        if now < cooldown_until:
            return TradeSignal(
                market_id=market.market_id,
                timestamp=now,
                decision=SignalDecision.SKIP_IN_COOLDOWN,
                yes_ask=market.yes_token.best_ask_price,
                no_ask=market.no_token.best_ask_price,
                yes_size=market.yes_token.best_ask_size,
                no_size=market.no_token.best_ask_size,
                sum_cost=market.sum_ask_cost,
                edge=None,
                cost_buffer=self.config.cost_buffer,
                reason=f"In cooldown until {datetime.fromtimestamp(cooldown_until).isoformat()}",
            )

        sum_cost = market.sum_ask_cost
        total_fee = sum_cost * self.fee_rate
        edge = Decimal("1.00") - sum_cost - total_fee - self.config.cost_buffer

        if edge < self.config.min_edge:
            return TradeSignal(
                market_id=market.market_id,
                timestamp=now,
                decision=SignalDecision.SKIP_INSUFFICIENT_EDGE,
                yes_ask=market.yes_token.best_ask_price,
                no_ask=market.no_token.best_ask_price,
                yes_size=market.yes_token.best_ask_size,
                no_size=market.no_token.best_ask_size,
                sum_cost=sum_cost,
                edge=edge,
                cost_buffer=self.config.cost_buffer,
                reason=f"Edge {edge:.4f} < min_edge {self.config.min_edge}",
            )

        min_size = market.min_available_size
        if min_size < self.config.min_depth:
            return TradeSignal(
                market_id=market.market_id,
                timestamp=now,
                decision=SignalDecision.SKIP_INSUFFICIENT_DEPTH,
                yes_ask=market.yes_token.best_ask_price,
                no_ask=market.no_token.best_ask_price,
                yes_size=market.yes_token.best_ask_size,
                no_size=market.no_token.best_ask_size,
                sum_cost=sum_cost,
                edge=edge,
                cost_buffer=self.config.cost_buffer,
                reason=f"Min depth {min_size:.2f} < required {self.config.min_depth}",
            )

        return TradeSignal(
            market_id=market.market_id,
            timestamp=now,
            decision=SignalDecision.TRADE,
            yes_ask=market.yes_token.best_ask_price,
            no_ask=market.no_token.best_ask_price,
            yes_size=market.yes_token.best_ask_size,
            no_size=market.no_token.best_ask_size,
            sum_cost=sum_cost,
            edge=edge,
            cost_buffer=self.config.cost_buffer,
            reason=f"Opportunity detected: edge={edge:.4f}, depth={min_size:.2f}",
        )

    def set_in_flight(self, market_id: str) -> None:
        """Mark a market as having in-flight orders."""
        self._in_flight.add(market_id)

    def clear_in_flight(self, market_id: str) -> None:
        """Clear in-flight status for a market."""
        self._in_flight.discard(market_id)

    def set_cooldown(self, market_id: str, duration_seconds: float) -> None:
        """Set a cooldown period for a market."""
        self._cooldowns[market_id] = datetime.now().timestamp() + duration_seconds

    def clear_cooldown(self, market_id: str) -> None:
        """Clear cooldown for a market."""
        self._cooldowns.pop(market_id, None)

    def get_in_flight_markets(self) -> List[str]:
        """Get list of markets with in-flight orders."""
        return list(self._in_flight)
