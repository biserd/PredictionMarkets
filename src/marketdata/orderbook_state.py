"""
Order book state management - tracks best bid/ask for YES and NO tokens.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Optional, List
from datetime import datetime
import asyncio

from src.adapters.base import OrderBookSnapshot, BookLevel


@dataclass
class TokenBook:
    token_id: str
    best_bid_price: Optional[Decimal] = None
    best_bid_size: Optional[Decimal] = None
    best_ask_price: Optional[Decimal] = None
    best_ask_size: Optional[Decimal] = None
    last_update: Optional[float] = None
    sequence: Optional[int] = None


@dataclass
class MarketBook:
    market_id: str
    question: str
    yes_token: TokenBook
    no_token: TokenBook
    active: bool = True

    @property
    def has_valid_quotes(self) -> bool:
        """Check if both YES and NO have valid ask quotes."""
        return (
            self.yes_token.best_ask_price is not None
            and self.yes_token.best_ask_size is not None
            and self.no_token.best_ask_price is not None
            and self.no_token.best_ask_size is not None
        )

    @property
    def sum_ask_cost(self) -> Optional[Decimal]:
        """Sum of YES ask + NO ask (cost to buy complete set)."""
        if not self.has_valid_quotes:
            return None
        return self.yes_token.best_ask_price + self.no_token.best_ask_price

    @property
    def min_available_size(self) -> Optional[Decimal]:
        """Minimum size available across both sides."""
        if not self.has_valid_quotes:
            return None
        return min(self.yes_token.best_ask_size, self.no_token.best_ask_size)

    @property
    def last_update_time(self) -> Optional[float]:
        """Most recent update timestamp from either side."""
        yes_time = self.yes_token.last_update or 0
        no_time = self.no_token.last_update or 0
        if yes_time == 0 and no_time == 0:
            return None
        return max(yes_time, no_time)


class OrderBookState:
    """
    Manages order book state for multiple markets.
    Thread-safe updates via asyncio locks.
    """

    def __init__(self):
        self._markets: Dict[str, MarketBook] = {}
        self._token_to_market: Dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def register_market(
        self,
        market_id: str,
        question: str,
        yes_token_id: str,
        no_token_id: str,
    ) -> None:
        """Register a new market to track."""
        async with self._lock:
            self._markets[market_id] = MarketBook(
                market_id=market_id,
                question=question,
                yes_token=TokenBook(token_id=yes_token_id),
                no_token=TokenBook(token_id=no_token_id),
            )
            self._token_to_market[yes_token_id] = market_id
            self._token_to_market[no_token_id] = market_id

    async def update_from_snapshot(self, snapshot: OrderBookSnapshot) -> Optional[str]:
        """
        Update order book state from a snapshot.
        Returns the market_id if update was successful, None otherwise.
        """
        async with self._lock:
            market_id = self._token_to_market.get(snapshot.token_id)
            if market_id is None:
                return None

            market = self._markets.get(market_id)
            if market is None:
                return None

            if snapshot.token_id == market.yes_token.token_id:
                token = market.yes_token
            elif snapshot.token_id == market.no_token.token_id:
                token = market.no_token
            else:
                return None

            if snapshot.asks:
                best_ask = snapshot.asks[0]
                token.best_ask_price = best_ask.price
                token.best_ask_size = best_ask.size
            else:
                token.best_ask_price = None
                token.best_ask_size = None

            if snapshot.bids:
                best_bid = snapshot.bids[0]
                token.best_bid_price = best_bid.price
                token.best_bid_size = best_bid.size
            else:
                token.best_bid_price = None
                token.best_bid_size = None

            token.last_update = snapshot.timestamp
            token.sequence = snapshot.sequence

            return market_id

    async def get_market(self, market_id: str) -> Optional[MarketBook]:
        """Get current state of a market."""
        async with self._lock:
            market = self._markets.get(market_id)
            if market is None:
                return None
            return MarketBook(
                market_id=market.market_id,
                question=market.question,
                yes_token=TokenBook(
                    token_id=market.yes_token.token_id,
                    best_bid_price=market.yes_token.best_bid_price,
                    best_bid_size=market.yes_token.best_bid_size,
                    best_ask_price=market.yes_token.best_ask_price,
                    best_ask_size=market.yes_token.best_ask_size,
                    last_update=market.yes_token.last_update,
                    sequence=market.yes_token.sequence,
                ),
                no_token=TokenBook(
                    token_id=market.no_token.token_id,
                    best_bid_price=market.no_token.best_bid_price,
                    best_bid_size=market.no_token.best_bid_size,
                    best_ask_price=market.no_token.best_ask_price,
                    best_ask_size=market.no_token.best_ask_size,
                    last_update=market.no_token.last_update,
                    sequence=market.no_token.sequence,
                ),
                active=market.active,
            )

    async def get_all_markets(self) -> List[MarketBook]:
        """Get current state of all markets."""
        async with self._lock:
            return [
                MarketBook(
                    market_id=m.market_id,
                    question=m.question,
                    yes_token=TokenBook(
                        token_id=m.yes_token.token_id,
                        best_bid_price=m.yes_token.best_bid_price,
                        best_bid_size=m.yes_token.best_bid_size,
                        best_ask_price=m.yes_token.best_ask_price,
                        best_ask_size=m.yes_token.best_ask_size,
                        last_update=m.yes_token.last_update,
                        sequence=m.yes_token.sequence,
                    ),
                    no_token=TokenBook(
                        token_id=m.no_token.token_id,
                        best_bid_price=m.no_token.best_bid_price,
                        best_bid_size=m.no_token.best_bid_size,
                        best_ask_price=m.no_token.best_ask_price,
                        best_ask_size=m.no_token.best_ask_size,
                        last_update=m.no_token.last_update,
                        sequence=m.no_token.sequence,
                    ),
                    active=m.active,
                )
                for m in self._markets.values()
            ]

    async def get_token_ids(self) -> List[str]:
        """Get all tracked token IDs for WebSocket subscription."""
        async with self._lock:
            return list(self._token_to_market.keys())

    @property
    def market_count(self) -> int:
        """Number of markets being tracked."""
        return len(self._markets)
