"""
Main entry point for the arbitrage bot.
"""
import asyncio
import logging
import signal
from typing import Optional

from src.config import Config
from src.adapters.base import VenueAdapter, OrderBookSnapshot
from src.adapters.mock import MockVenueAdapter
from src.adapters.polymarket import PolymarketAdapter
from src.marketdata.orderbook_state import OrderBookState
from src.strategy.signal_engine import SignalEngine
from src.execution.executor import ExecutionEngine
from src.execution.risk import KillSwitch
from src.storage.ledger import Ledger

logger = logging.getLogger(__name__)


class ArbBot:
    """
    Main arbitrage bot orchestrator.
    
    Coordinates market data ingestion, signal detection, and execution.
    """

    def __init__(self, config: Config):
        self.config = config
        self.adapter: Optional[VenueAdapter] = None
        self.order_book = OrderBookState()
        self.signal_engine = SignalEngine(config.strategy)
        self.ledger = Ledger(config.data.sqlite_path)
        self.executor: Optional[ExecutionEngine] = None
        self.kill_switch: Optional[KillSwitch] = None
        self._running = False
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Initialize and start the bot."""
        logger.info(f"Starting ArbBot in {'PAPER' if self.config.paper_mode else 'LIVE'} mode")

        self.ledger.connect()

        if self.config.venue.name == "mock":
            self.adapter = MockVenueAdapter()
        elif self.config.venue.name == "polymarket":
            self.adapter = PolymarketAdapter(
                venue_config=self.config.venue,
                ws_config=self.config.websocket,
            )
        else:
            raise ValueError(f"Unknown venue: {self.config.venue.name}")

        self.signal_engine = SignalEngine(
            self.config.strategy,
            fee_rate=self.adapter.fee_rate,
        )

        self.executor = ExecutionEngine(
            adapter=self.adapter,
            signal_engine=self.signal_engine,
            ledger=self.ledger,
            execution_config=self.config.execution,
            risk_config=self.config.risk,
            paper_mode=self.config.paper_mode,
        )

        self.kill_switch = KillSwitch(
            ledger=self.ledger,
            risk_config=self.config.risk,
            halt_callback=self.executor.halt,
        )

        self.adapter.set_book_update_callback(self._on_book_update)

        await self.adapter.connect_ws()
        logger.info("WebSocket connected")

        if self.config.markets:
            for market_id in self.config.markets:
                market_info = await self.adapter.get_market_info(market_id)
                if market_info:
                    await self.order_book.register_market(
                        market_id=market_info.market_id,
                        question=market_info.question,
                        yes_token_id=market_info.yes_token_id,
                        no_token_id=market_info.no_token_id,
                    )
                    logger.info(f"Registered market: {market_info.question[:50]}...")
                else:
                    logger.warning(f"Could not find market: {market_id}")

            await self.adapter.subscribe_markets(self.config.markets)
        else:
            markets = await self.adapter.list_markets(active_only=True)
            for market_info in markets[:10]:
                await self.order_book.register_market(
                    market_id=market_info.market_id,
                    question=market_info.question,
                    yes_token_id=market_info.yes_token_id,
                    no_token_id=market_info.no_token_id,
                )
            await self.adapter.subscribe_markets([m.market_id for m in markets[:10]])
            logger.info(f"Auto-subscribed to {len(markets[:10])} markets")

        self._running = True
        logger.info("Bot started successfully")

    async def stop(self) -> None:
        """Stop the bot gracefully."""
        logger.info("Stopping bot...")
        self._running = False
        self._shutdown_event.set()

        if self.adapter:
            await self.adapter.disconnect_ws()

        if self.ledger:
            self.ledger.close()

        logger.info("Bot stopped")

    async def _on_book_update(self, snapshot: OrderBookSnapshot) -> None:
        """Handle incoming order book updates."""
        market_id = await self.order_book.update_from_snapshot(snapshot)
        if not market_id:
            return

        if self.kill_switch and self.kill_switch.check_conditions():
            logger.critical("Kill switch triggered - halting execution")
            return

        market = await self.order_book.get_market(market_id)
        if not market:
            return

        signal = self.signal_engine.evaluate(market)

        self.ledger.log_opportunity(signal)

        if signal.is_tradeable and self.executor and not self.executor.is_halted:
            logger.info(f"Trade signal for {market_id}: edge={signal.edge:.4f}")
            result = await self.executor.execute_signal(signal, market)
            if result.success:
                logger.info(f"Trade executed successfully: tradeset_id={result.tradeset_id}")
            else:
                logger.warning(f"Trade failed: {result.error}")

    async def run_forever(self) -> None:
        """Run the bot until shutdown."""
        await self._shutdown_event.wait()


async def run_bot(config: Config) -> None:
    """Main entry point to run the bot."""
    bot = ArbBot(config)

    loop = asyncio.get_event_loop()
    
    def signal_handler():
        logger.info("Received shutdown signal")
        asyncio.create_task(bot.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass

    try:
        await bot.start()
        await bot.run_forever()
    except Exception as e:
        logger.error(f"Bot error: {e}")
        raise
    finally:
        await bot.stop()


if __name__ == "__main__":
    from src.cli.commands import main
    main()
