"""
Mock venue adapter for testing and paper trading.
Simulates market data and order execution without real API calls.
"""
import asyncio
import random
import uuid
from decimal import Decimal
from typing import Optional, List, Callable, Awaitable, Dict
from datetime import datetime

from src.adapters.base import (
    VenueAdapter,
    Order,
    Fill,
    OrderSide,
    OrderType,
    OrderStatus,
    OrderBookSnapshot,
    BookLevel,
    MarketInfo,
)


class MockVenueAdapter(VenueAdapter):
    """
    Mock adapter for testing the arbitrage bot without real API connections.
    Generates synthetic market data and simulates order fills.
    """

    def __init__(self):
        self._connected = False
        self._markets: Dict[str, MarketInfo] = {}
        self._subscribed_tokens: List[str] = []
        self._book_callback: Optional[Callable[[OrderBookSnapshot], Awaitable[None]]] = None
        self._fill_callback: Optional[Callable[[Fill], Awaitable[None]]] = None
        self._orders: Dict[str, Order] = {}
        self._ws_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

        self._setup_mock_markets()

    def _setup_mock_markets(self) -> None:
        """Create some mock markets for testing."""
        mock_markets = [
            ("mock-market-1", "Will BTC reach $100k in 2025?"),
            ("mock-market-2", "Will ETH flip BTC market cap in 2025?"),
            ("mock-market-3", "Will SpaceX land humans on Mars by 2030?"),
        ]

        for i, (market_id, question) in enumerate(mock_markets):
            yes_token = f"yes-token-{i}"
            no_token = f"no-token-{i}"
            self._markets[market_id] = MarketInfo(
                market_id=market_id,
                condition_id=f"condition-{i}",
                question=question,
                yes_token_id=yes_token,
                no_token_id=no_token,
                min_tick_size=Decimal("0.01"),
                active=True,
            )

    async def connect_ws(self) -> None:
        """Simulate WebSocket connection."""
        await asyncio.sleep(0.1)
        self._connected = True
        self._stop_event.clear()

    async def disconnect_ws(self) -> None:
        """Simulate WebSocket disconnection."""
        self._stop_event.set()
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        self._connected = False

    async def subscribe_markets(self, market_ids: List[str]) -> None:
        """Subscribe to mock markets and start generating data."""
        for market_id in market_ids:
            if market_id in self._markets:
                market = self._markets[market_id]
                self._subscribed_tokens.append(market.yes_token_id)
                self._subscribed_tokens.append(market.no_token_id)

        if self._book_callback:
            self._ws_task = asyncio.create_task(self._generate_book_updates())

    async def _generate_book_updates(self) -> None:
        """Generate synthetic order book updates."""
        while not self._stop_event.is_set():
            await asyncio.sleep(random.uniform(0.5, 2.0))

            for market in self._markets.values():
                if market.yes_token_id in self._subscribed_tokens:
                    yes_mid = Decimal(str(random.uniform(0.3, 0.7)))
                    no_mid = Decimal("1.0") - yes_mid

                    slippage = Decimal(str(random.uniform(-0.03, 0.05)))
                    yes_ask = yes_mid + Decimal("0.01") + slippage
                    no_ask = no_mid + Decimal("0.01") + slippage

                    yes_ask = max(Decimal("0.01"), min(Decimal("0.99"), yes_ask))
                    no_ask = max(Decimal("0.01"), min(Decimal("0.99"), no_ask))

                    now = datetime.now().timestamp()

                    yes_snapshot = OrderBookSnapshot(
                        market_id=market.market_id,
                        token_id=market.yes_token_id,
                        bids=[BookLevel(yes_ask - Decimal("0.02"), Decimal(str(random.randint(50, 500))))],
                        asks=[BookLevel(yes_ask, Decimal(str(random.randint(50, 500))))],
                        timestamp=now,
                    )

                    no_snapshot = OrderBookSnapshot(
                        market_id=market.market_id,
                        token_id=market.no_token_id,
                        bids=[BookLevel(no_ask - Decimal("0.02"), Decimal(str(random.randint(50, 500))))],
                        asks=[BookLevel(no_ask, Decimal(str(random.randint(50, 500))))],
                        timestamp=now,
                    )

                    if self._book_callback:
                        await self._book_callback(yes_snapshot)
                        await self._book_callback(no_snapshot)

    async def get_snapshot_rest(self, market_id: str) -> Optional[OrderBookSnapshot]:
        """Get a mock snapshot for a market."""
        market = self._markets.get(market_id)
        if not market:
            return None

        yes_ask = Decimal(str(random.uniform(0.4, 0.6)))
        return OrderBookSnapshot(
            market_id=market_id,
            token_id=market.yes_token_id,
            bids=[BookLevel(yes_ask - Decimal("0.02"), Decimal("100"))],
            asks=[BookLevel(yes_ask, Decimal("100"))],
            timestamp=datetime.now().timestamp(),
        )

    async def get_market_info(self, market_id: str) -> Optional[MarketInfo]:
        """Get mock market info."""
        return self._markets.get(market_id)

    async def list_markets(self, active_only: bool = True) -> List[MarketInfo]:
        """List all mock markets."""
        if active_only:
            return [m for m in self._markets.values() if m.active]
        return list(self._markets.values())

    async def place_order(
        self,
        market_id: str,
        token_id: str,
        side: OrderSide,
        order_type: OrderType,
        price: Decimal,
        size: Decimal,
    ) -> Order:
        """Simulate order placement with random fill behavior."""
        order_id = f"mock-order-{uuid.uuid4().hex[:8]}"
        now = datetime.now().timestamp()

        order = Order(
            order_id=order_id,
            market_id=market_id,
            token_id=token_id,
            side=side,
            order_type=order_type,
            price=price,
            size=size,
            status=OrderStatus.PENDING,
            created_at=now,
            updated_at=now,
        )

        self._orders[order_id] = order

        await asyncio.sleep(random.uniform(0.05, 0.2))

        fill_chance = random.random()
        if fill_chance > 0.1:
            order.status = OrderStatus.FILLED
            order.filled_size = size
            order.avg_fill_price = price
            order.fee = size * price * Decimal("0.02")

            if self._fill_callback:
                fill = Fill(
                    fill_id=f"fill-{uuid.uuid4().hex[:8]}",
                    order_id=order_id,
                    price=price,
                    size=size,
                    fee=order.fee,
                    timestamp=datetime.now().timestamp(),
                )
                await self._fill_callback(fill)
        elif fill_chance > 0.05:
            partial_size = size * Decimal(str(random.uniform(0.3, 0.7)))
            order.status = OrderStatus.PARTIALLY_FILLED
            order.filled_size = partial_size
            order.avg_fill_price = price
            order.fee = partial_size * price * Decimal("0.02")
        else:
            order.status = OrderStatus.REJECTED

        order.updated_at = datetime.now().timestamp()
        return order

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a mock order."""
        order = self._orders.get(order_id)
        if order and order.status in [OrderStatus.PENDING, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]:
            order.status = OrderStatus.CANCELLED
            order.updated_at = datetime.now().timestamp()
            return True
        return False

    async def get_order_status(self, order_id: str) -> Optional[Order]:
        """Get status of a mock order."""
        return self._orders.get(order_id)

    def set_book_update_callback(
        self, callback: Callable[[OrderBookSnapshot], Awaitable[None]]
    ) -> None:
        """Set callback for order book updates."""
        self._book_callback = callback

    def set_fill_callback(
        self, callback: Callable[[Fill], Awaitable[None]]
    ) -> None:
        """Set callback for fill notifications."""
        self._fill_callback = callback

    @property
    def is_connected(self) -> bool:
        """Check if mock WebSocket is connected."""
        return self._connected

    @property
    def venue_name(self) -> str:
        """Return venue name."""
        return "mock"

    @property
    def fee_rate(self) -> Decimal:
        """Return fee rate (2%)."""
        return Decimal("0.02")
