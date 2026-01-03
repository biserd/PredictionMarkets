"""
Project Alpha - Whale Watchdog Module
Monitors whale wallet addresses for large trades on Polymarket
"""

import asyncio
import json
import websockets
from typing import List, Dict, Callable, Optional
from datetime import datetime
import config
import database


class WhaleWatcher:
    """WebSocket-based whale trade monitor for Polymarket."""
    
    def __init__(self, addresses: List[str] = None, on_trade_callback: Callable = None):
        self.addresses = [addr.lower() for addr in (addresses or config.WHALE_ADDRESSES)]
        self.on_trade_callback = on_trade_callback
        self.ws = None
        self.running = False
        self.reconnect_delay = 5
        self.max_reconnect_delay = 60
    
    async def connect(self):
        """Connect to Polymarket WebSocket."""
        try:
            self.ws = await websockets.connect(
                config.POLYMARKET_CLOB_WS,
                ping_interval=30,
                ping_timeout=10,
            )
            print(f"Connected to Polymarket WebSocket")
            self.reconnect_delay = 5
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False
    
    async def subscribe(self):
        """Subscribe to trade events for monitored addresses."""
        if not self.ws:
            return False
        
        try:
            subscribe_msg = {
                "type": "subscribe",
                "channel": "user",
                "markets": [],
            }
            await self.ws.send(json.dumps(subscribe_msg))
            print(f"Subscribed to trade events for {len(self.addresses)} addresses")
            return True
        except Exception as e:
            print(f"Subscription failed: {e}")
            return False
    
    def parse_trade_event(self, message: Dict) -> Optional[Dict]:
        """Parse a WebSocket message and extract trade info if relevant."""
        try:
            event_type = message.get("type", "")
            
            if event_type not in ["trade", "order_fill", "fill"]:
                return None
            
            maker = message.get("maker", "").lower()
            taker = message.get("taker", "").lower()
            trader = message.get("trader", "").lower()
            
            matching_address = None
            for addr in self.addresses:
                if addr in [maker, taker, trader]:
                    matching_address = addr
                    break
            
            if not matching_address:
                return None
            
            amount = float(message.get("size", 0)) * float(message.get("price", 0))
            if amount < config.MIN_TRADE_SIZE:
                return None
            
            trade_info = {
                "whale_address": matching_address,
                "market_id": message.get("market", message.get("asset_id", "unknown")),
                "market_title": message.get("market_title", "Unknown Market"),
                "outcome": message.get("outcome", message.get("side", "Unknown")),
                "side": message.get("side", "buy"),
                "amount_usdc": amount,
                "price": float(message.get("price", 0)),
                "timestamp": datetime.now().isoformat(),
            }
            
            return trade_info
            
        except (ValueError, KeyError, TypeError) as e:
            print(f"Error parsing trade event: {e}")
            return None
    
    async def handle_message(self, message: str):
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)
            
            if isinstance(data, list):
                for item in data:
                    await self._process_single_message(item)
            else:
                await self._process_single_message(data)
                
        except json.JSONDecodeError as e:
            print(f"Invalid JSON received: {e}")
    
    async def _process_single_message(self, data: Dict):
        """Process a single message."""
        trade_info = self.parse_trade_event(data)
        
        if trade_info:
            print(f"\n{'='*50}")
            print(f"WHALE TRADE DETECTED!")
            print(f"Address: {trade_info['whale_address'][:10]}...")
            print(f"Market: {trade_info['market_title']}")
            print(f"Side: {trade_info['side'].upper()} {trade_info['outcome']}")
            print(f"Amount: ${trade_info['amount_usdc']:,.2f}")
            print(f"Price: {trade_info['price']:.2f}")
            print(f"{'='*50}\n")
            
            database.log_whale_trade(
                trade_info['whale_address'],
                trade_info['market_id'],
                trade_info['market_title'],
                trade_info['outcome'],
                trade_info['side'],
                trade_info['amount_usdc'],
                trade_info['price']
            )
            
            if self.on_trade_callback:
                await self.on_trade_callback(trade_info)
    
    async def listen(self):
        """Main listening loop."""
        self.running = True
        
        while self.running:
            try:
                if not await self.connect():
                    print(f"Reconnecting in {self.reconnect_delay} seconds...")
                    await asyncio.sleep(self.reconnect_delay)
                    self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)
                    continue
                
                await self.subscribe()
                
                async for message in self.ws:
                    if not self.running:
                        break
                    await self.handle_message(message)
                    
            except websockets.ConnectionClosed as e:
                print(f"Connection closed: {e}. Reconnecting...")
                await asyncio.sleep(self.reconnect_delay)
            except Exception as e:
                print(f"Error in listener: {e}")
                await asyncio.sleep(self.reconnect_delay)
    
    async def stop(self):
        """Stop the watcher."""
        self.running = False
        if self.ws:
            await self.ws.close()
    
    def add_address(self, address: str):
        """Add a new address to monitor."""
        addr_lower = address.lower()
        if addr_lower not in self.addresses:
            self.addresses.append(addr_lower)
            database.add_whale_address(address)
            print(f"Added address: {address}")
    
    def remove_address(self, address: str):
        """Remove an address from monitoring."""
        addr_lower = address.lower()
        if addr_lower in self.addresses:
            self.addresses.remove(addr_lower)
            database.remove_whale_address(address)
            print(f"Removed address: {address}")


def get_demo_whale_trades() -> List[Dict]:
    """Generate demo whale trade data for testing."""
    return [
        {
            "whale_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f43127",
            "market_id": "POLY_BTC_100K",
            "market_title": "Bitcoin > $100,000 by Dec 2025",
            "outcome": "YES",
            "side": "buy",
            "amount_usdc": 15000,
            "price": 0.42,
            "timestamp": "2026-01-03T10:15:00",
        },
        {
            "whale_address": "0x8ba1f109551bD432803012645Ac136ddd64DBA72",
            "market_id": "POLY_FED_RATE",
            "market_title": "Fed cuts rates in Q1 2026",
            "outcome": "NO",
            "side": "buy",
            "amount_usdc": 25000,
            "price": 0.65,
            "timestamp": "2026-01-03T09:45:00",
        },
        {
            "whale_address": "0xAb5801a7D398351b8bE11C439e05C5B3259aec9B",
            "market_id": "POLY_SUPERBOWL",
            "market_title": "Chiefs win Super Bowl 2026",
            "outcome": "YES",
            "side": "buy",
            "amount_usdc": 50000,
            "price": 0.35,
            "timestamp": "2026-01-03T08:30:00",
        },
    ]


async def main():
    """Main entry point for standalone whale watcher."""
    print("Starting Whale Watcher...")
    print(f"Monitoring {len(config.WHALE_ADDRESSES)} addresses")
    
    async def on_trade(trade_info: Dict):
        """Callback for detected trades."""
        print(f"Trade callback triggered: {trade_info}")
    
    watcher = WhaleWatcher(on_trade_callback=on_trade)
    
    try:
        await watcher.listen()
    except KeyboardInterrupt:
        print("\nShutting down...")
        await watcher.stop()


if __name__ == "__main__":
    asyncio.run(main())
