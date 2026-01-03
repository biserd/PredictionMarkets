"""
Base VenueAdapter interface - venue-agnostic trading interface.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Callable, Awaitable
from decimal import Decimal
import asyncio


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    IOC = "IOC"


class OrderStatus(Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass
class Order:
    order_id: str
    market_id: str
    token_id: str
    side: OrderSide
    order_type: OrderType
    price: Decimal
    size: Decimal
    status: OrderStatus
    filled_size: Decimal = Decimal("0")
    avg_fill_price: Optional[Decimal] = None
    fee: Decimal = Decimal("0")
    created_at: Optional[float] = None
    updated_at: Optional[float] = None


@dataclass
class Fill:
    fill_id: str
    order_id: str
    price: Decimal
    size: Decimal
    fee: Decimal
    timestamp: float


@dataclass
class BookLevel:
    price: Decimal
    size: Decimal


@dataclass
class OrderBookSnapshot:
    market_id: str
    token_id: str
    bids: List[BookLevel]
    asks: List[BookLevel]
    timestamp: float
    sequence: Optional[int] = None


@dataclass
class MarketInfo:
    market_id: str
    condition_id: str
    question: str
    yes_token_id: str
    no_token_id: str
    min_tick_size: Decimal
    active: bool
    end_date: Optional[str] = None


class VenueAdapter(ABC):
    """
    Abstract base class for prediction market venue adapters.
    Implementations must provide WebSocket market data and order execution.
    """

    @abstractmethod
    async def connect_ws(self) -> None:
        """Establish WebSocket connection to the venue."""
        pass

    @abstractmethod
    async def disconnect_ws(self) -> None:
        """Close WebSocket connection."""
        pass

    @abstractmethod
    async def subscribe_markets(self, market_ids: List[str]) -> None:
        """Subscribe to order book updates for specified markets."""
        pass

    @abstractmethod
    async def get_snapshot_rest(self, market_id: str) -> Optional[OrderBookSnapshot]:
        """Fetch current order book snapshot via REST API."""
        pass

    @abstractmethod
    async def get_market_info(self, market_id: str) -> Optional[MarketInfo]:
        """Get market metadata including token IDs."""
        pass

    @abstractmethod
    async def list_markets(self, active_only: bool = True) -> List[MarketInfo]:
        """List available markets."""
        pass

    @abstractmethod
    async def place_order(
        self,
        market_id: str,
        token_id: str,
        side: OrderSide,
        order_type: OrderType,
        price: Decimal,
        size: Decimal,
    ) -> Order:
        """Place an order on the venue."""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order. Returns True if successfully cancelled."""
        pass

    @abstractmethod
    async def get_order_status(self, order_id: str) -> Optional[Order]:
        """Get current status of an order."""
        pass

    @abstractmethod
    def set_book_update_callback(
        self, callback: Callable[[OrderBookSnapshot], Awaitable[None]]
    ) -> None:
        """Set callback for order book updates from WebSocket."""
        pass

    @abstractmethod
    def set_fill_callback(
        self, callback: Callable[[Fill], Awaitable[None]]
    ) -> None:
        """Set callback for fill notifications."""
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if WebSocket is currently connected."""
        pass

    @property
    @abstractmethod
    def venue_name(self) -> str:
        """Name of the venue (e.g., 'polymarket', 'kalshi')."""
        pass

    @property
    @abstractmethod
    def fee_rate(self) -> Decimal:
        """Trading fee rate (e.g., 0.02 for 2%)."""
        pass
