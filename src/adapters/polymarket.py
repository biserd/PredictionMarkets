"""
Polymarket CLOB adapter - WebSocket market data and order execution.
"""
import asyncio
import json
import time
from decimal import Decimal
from typing import Optional, List, Callable, Awaitable, Dict, Any
from datetime import datetime
import logging

import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed

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
from src.config import VenueConfig, WebSocketConfig

logger = logging.getLogger(__name__)


class PolymarketAdapter(VenueAdapter):
    """
    Polymarket CLOB adapter for WebSocket market data and REST order execution.
    """

    def __init__(
        self,
        venue_config: VenueConfig,
        ws_config: WebSocketConfig,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        passphrase: Optional[str] = None,
    ):
        self.venue_config = venue_config
        self.ws_config = ws_config
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase

        self._connected = False
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._book_callback: Optional[Callable[[OrderBookSnapshot], Awaitable[None]]] = None
        self._fill_callback: Optional[Callable[[Fill], Awaitable[None]]] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._subscribed_tokens: List[str] = []
        self._token_to_market: Dict[str, str] = {}
        self._reconnect_delay = ws_config.reconnect_delay_initial

        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            connector = None
            if self.venue_config.proxy_url:
                connector = aiohttp.TCPConnector()
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def connect_ws(self) -> None:
        """Establish WebSocket connection to Polymarket CLOB."""
        self._stop_event.clear()
        self._reconnect_delay = self.ws_config.reconnect_delay_initial

        try:
            self._ws = await websockets.connect(
                self.venue_config.ws_url,
                ping_interval=None,
                ping_timeout=None,
            )
            self._connected = True
            logger.info("Connected to Polymarket WebSocket")

            self._ws_task = asyncio.create_task(self._receive_loop())
            self._ping_task = asyncio.create_task(self._ping_loop())

        except Exception as e:
            logger.error(f"Failed to connect to WebSocket: {e}")
            raise

    async def disconnect_ws(self) -> None:
        """Close WebSocket connection."""
        self._stop_event.set()

        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass

        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass

        if self._ws:
            await self._ws.close()
            self._ws = None

        if self._session and not self._session.closed:
            await self._session.close()

        self._connected = False
        logger.info("Disconnected from Polymarket WebSocket")

    async def _ping_loop(self) -> None:
        """Send periodic pings to keep connection alive."""
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(self.ws_config.heartbeat_interval)
                if self._ws and not self._ws.closed:
                    await self._ws.ping()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Ping failed: {e}")

    async def _receive_loop(self) -> None:
        """Receive and process WebSocket messages."""
        while not self._stop_event.is_set():
            try:
                if not self._ws:
                    break

                message = await self._ws.recv()
                await self._process_message(message)
                self._reconnect_delay = self.ws_config.reconnect_delay_initial

            except ConnectionClosed:
                logger.warning("WebSocket connection closed")
                self._connected = False
                if not self._stop_event.is_set():
                    await self._reconnect()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in receive loop: {e}")
                await asyncio.sleep(1)

    async def _reconnect(self) -> None:
        """Reconnect with exponential backoff."""
        while not self._stop_event.is_set():
            logger.info(f"Reconnecting in {self._reconnect_delay}s...")
            await asyncio.sleep(self._reconnect_delay)

            try:
                self._ws = await websockets.connect(
                    self.venue_config.ws_url,
                    ping_interval=None,
                    ping_timeout=None,
                )
                self._connected = True
                logger.info("Reconnected to Polymarket WebSocket")

                if self._subscribed_tokens:
                    await self._send_subscription(self._subscribed_tokens)

                if self.ws_config.snapshot_on_reconnect:
                    for market_id in set(self._token_to_market.values()):
                        await self.get_snapshot_rest(market_id)

                self._reconnect_delay = self.ws_config.reconnect_delay_initial
                return

            except Exception as e:
                logger.error(f"Reconnection failed: {e}")
                self._reconnect_delay = min(
                    self._reconnect_delay * self.ws_config.reconnect_backoff_factor,
                    self.ws_config.reconnect_delay_max,
                )

    async def _process_message(self, message: str) -> None:
        """Process incoming WebSocket message."""
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON message: {message[:100]}")
            return

        event_type = data.get("event_type")

        if event_type == "book":
            await self._handle_book_event(data)
        elif event_type == "price_change":
            await self._handle_price_change(data)
        elif event_type == "last_trade_price":
            pass
        elif event_type == "tick_size_change":
            pass
        else:
            logger.debug(f"Unknown event type: {event_type}")

    async def _handle_book_event(self, data: Dict[str, Any]) -> None:
        """Handle order book update event."""
        if not self._book_callback:
            return

        token_id = data.get("asset_id")
        if not token_id:
            return

        market_id = self._token_to_market.get(token_id, "")

        bids = []
        for bid in data.get("bids", []):
            if len(bid) >= 2:
                bids.append(BookLevel(
                    price=Decimal(str(bid[0])),
                    size=Decimal(str(bid[1])),
                ))

        asks = []
        for ask in data.get("asks", []):
            if len(ask) >= 2:
                asks.append(BookLevel(
                    price=Decimal(str(ask[0])),
                    size=Decimal(str(ask[1])),
                ))

        snapshot = OrderBookSnapshot(
            market_id=market_id,
            token_id=token_id,
            bids=bids,
            asks=asks,
            timestamp=data.get("timestamp", time.time()),
            sequence=data.get("hash"),
        )

        await self._book_callback(snapshot)

    async def _handle_price_change(self, data: Dict[str, Any]) -> None:
        """Handle price change event (top of book update)."""
        if not self._book_callback:
            return

        for change in data.get("price_changes", []):
            token_id = change.get("asset_id")
            if not token_id:
                continue

            market_id = self._token_to_market.get(token_id, "")

            best_bid = change.get("best_bid")
            best_ask = change.get("best_ask")

            bids = []
            if best_bid:
                bids.append(BookLevel(
                    price=Decimal(str(best_bid)),
                    size=Decimal("0"),
                ))

            asks = []
            if best_ask:
                asks.append(BookLevel(
                    price=Decimal(str(best_ask)),
                    size=Decimal("0"),
                ))

            snapshot = OrderBookSnapshot(
                market_id=market_id,
                token_id=token_id,
                bids=bids,
                asks=asks,
                timestamp=time.time(),
            )

            await self._book_callback(snapshot)

    async def subscribe_markets(self, market_ids: List[str]) -> None:
        """Subscribe to order book updates for specified markets."""
        token_ids = []

        for market_id in market_ids:
            market_info = await self.get_market_info(market_id)
            if market_info:
                token_ids.append(market_info.yes_token_id)
                token_ids.append(market_info.no_token_id)
                self._token_to_market[market_info.yes_token_id] = market_id
                self._token_to_market[market_info.no_token_id] = market_id

        if token_ids:
            self._subscribed_tokens = token_ids
            await self._send_subscription(token_ids)

    async def _send_subscription(self, token_ids: List[str]) -> None:
        """Send subscription message to WebSocket."""
        if not self._ws:
            return

        subscription = {
            "assets_ids": token_ids,
            "type": "market",
        }

        await self._ws.send(json.dumps(subscription))
        logger.info(f"Subscribed to {len(token_ids)} tokens")

    async def get_snapshot_rest(self, market_id: str) -> Optional[OrderBookSnapshot]:
        """Fetch current order book snapshot via REST API."""
        session = await self._get_session()
        url = f"{self.venue_config.api_url}/book"

        try:
            market_info = await self.get_market_info(market_id)
            if not market_info:
                return None

            params = {"token_id": market_info.yes_token_id}
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to get book snapshot: {resp.status}")
                    return None

                data = await resp.json()

                bids = []
                for bid in data.get("bids", []):
                    bids.append(BookLevel(
                        price=Decimal(str(bid.get("price", 0))),
                        size=Decimal(str(bid.get("size", 0))),
                    ))

                asks = []
                for ask in data.get("asks", []):
                    asks.append(BookLevel(
                        price=Decimal(str(ask.get("price", 0))),
                        size=Decimal(str(ask.get("size", 0))),
                    ))

                return OrderBookSnapshot(
                    market_id=market_id,
                    token_id=market_info.yes_token_id,
                    bids=bids,
                    asks=asks,
                    timestamp=time.time(),
                )

        except Exception as e:
            logger.error(f"Error fetching book snapshot: {e}")
            return None

    async def get_market_info(self, market_id: str) -> Optional[MarketInfo]:
        """Get market metadata including token IDs."""
        session = await self._get_session()
        url = f"{self.venue_config.api_url}/markets/{market_id}"

        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None

                data = await resp.json()

                tokens = data.get("tokens", [])
                yes_token = next((t for t in tokens if t.get("outcome") == "Yes"), None)
                no_token = next((t for t in tokens if t.get("outcome") == "No"), None)

                if not yes_token or not no_token:
                    return None

                return MarketInfo(
                    market_id=market_id,
                    condition_id=data.get("condition_id", ""),
                    question=data.get("question", ""),
                    yes_token_id=yes_token.get("token_id", ""),
                    no_token_id=no_token.get("token_id", ""),
                    min_tick_size=Decimal(str(data.get("minimum_tick_size", "0.01"))),
                    active=data.get("active", False),
                    end_date=data.get("end_date_iso"),
                )

        except Exception as e:
            logger.error(f"Error fetching market info: {e}")
            return None

    async def list_markets(self, active_only: bool = True) -> List[MarketInfo]:
        """List available markets."""
        session = await self._get_session()
        url = f"{self.venue_config.api_url}/markets"

        try:
            params = {"active": "true"} if active_only else {}
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return []

                data = await resp.json()
                markets = []

                for m in data:
                    tokens = m.get("tokens", [])
                    yes_token = next((t for t in tokens if t.get("outcome") == "Yes"), None)
                    no_token = next((t for t in tokens if t.get("outcome") == "No"), None)

                    if yes_token and no_token:
                        markets.append(MarketInfo(
                            market_id=m.get("condition_id", ""),
                            condition_id=m.get("condition_id", ""),
                            question=m.get("question", ""),
                            yes_token_id=yes_token.get("token_id", ""),
                            no_token_id=no_token.get("token_id", ""),
                            min_tick_size=Decimal(str(m.get("minimum_tick_size", "0.01"))),
                            active=m.get("active", False),
                        ))

                return markets

        except Exception as e:
            logger.error(f"Error listing markets: {e}")
            return []

    async def place_order(
        self,
        market_id: str,
        token_id: str,
        side: OrderSide,
        order_type: OrderType,
        price: Decimal,
        size: Decimal,
    ) -> Order:
        """Place an order on Polymarket CLOB."""
        raise NotImplementedError(
            "Order placement requires wallet integration. "
            "Use paper mode for testing without real orders."
        )

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        raise NotImplementedError("Order cancellation requires wallet integration.")

    async def get_order_status(self, order_id: str) -> Optional[Order]:
        """Get current status of an order."""
        raise NotImplementedError("Order status requires wallet integration.")

    def set_book_update_callback(
        self, callback: Callable[[OrderBookSnapshot], Awaitable[None]]
    ) -> None:
        """Set callback for order book updates from WebSocket."""
        self._book_callback = callback

    def set_fill_callback(
        self, callback: Callable[[Fill], Awaitable[None]]
    ) -> None:
        """Set callback for fill notifications."""
        self._fill_callback = callback

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is currently connected."""
        return self._connected and self._ws is not None and not self._ws.closed

    @property
    def venue_name(self) -> str:
        """Name of the venue."""
        return "polymarket"

    @property
    def fee_rate(self) -> Decimal:
        """Trading fee rate (2% on Polymarket)."""
        return Decimal("0.02")
