"""
Execution engine for complete-set arbitrage trades.
Handles order placement, partial-fill protection, and risk management.
"""
import asyncio
import uuid
from decimal import Decimal
from typing import Optional, Dict
from datetime import datetime
from enum import Enum
import logging

from src.adapters.base import VenueAdapter, Order, OrderSide, OrderType, OrderStatus
from src.strategy.signal_engine import SignalEngine, TradeSignal
from src.storage.ledger import Ledger
from src.config import ExecutionConfig, RiskConfig
from src.marketdata.orderbook_state import MarketBook

logger = logging.getLogger(__name__)


class ExecutionState(Enum):
    IDLE = "IDLE"
    SIGNAL_DETECTED = "SIGNAL_DETECTED"
    PLACING_ORDERS = "PLACING_ORDERS"
    WAITING_FILLS = "WAITING_FILLS"
    SUCCESS = "SUCCESS"
    PARTIAL_FILL_PROTECT = "PARTIAL_FILL_PROTECT"
    FAILED = "FAILED"
    COOLDOWN = "COOLDOWN"


class ExecutionResult:
    def __init__(
        self,
        success: bool,
        tradeset_id: Optional[int] = None,
        yes_order: Optional[Order] = None,
        no_order: Optional[Order] = None,
        error: Optional[str] = None,
    ):
        self.success = success
        self.tradeset_id = tradeset_id
        self.yes_order = yes_order
        self.no_order = no_order
        self.error = error


class ExecutionEngine:
    """
    State machine for executing complete-set arbitrage trades.
    
    State transitions:
    IDLE -> SIGNAL_DETECTED -> PLACING_ORDERS -> WAITING_FILLS -> SUCCESS/PARTIAL_FILL_PROTECT/FAILED -> COOLDOWN -> IDLE
    """

    def __init__(
        self,
        adapter: VenueAdapter,
        signal_engine: SignalEngine,
        ledger: Ledger,
        execution_config: ExecutionConfig,
        risk_config: RiskConfig,
        paper_mode: bool = True,
    ):
        self.adapter = adapter
        self.signal_engine = signal_engine
        self.ledger = ledger
        self.execution_config = execution_config
        self.risk_config = risk_config
        self.paper_mode = paper_mode

        self._state: Dict[str, ExecutionState] = {}
        self._halted = False
        self._daily_notional = Decimal("0")
        self._open_positions = 0

    @property
    def is_halted(self) -> bool:
        """Check if execution is halted."""
        return self._halted

    def halt(self) -> None:
        """Halt all trading."""
        self._halted = True
        logger.warning("Execution halted")

    def resume(self) -> None:
        """Resume trading after halt."""
        self._halted = False
        logger.info("Execution resumed")

    def get_state(self, market_id: str) -> ExecutionState:
        """Get current execution state for a market."""
        return self._state.get(market_id, ExecutionState.IDLE)

    def _check_risk_limits(self, order_size: Decimal, price: Decimal) -> Optional[str]:
        """Check if trade would violate risk limits."""
        notional = order_size * price * 2

        if self._daily_notional + notional > self.risk_config.max_daily_notional:
            return f"Would exceed daily notional limit ({self._daily_notional + notional} > {self.risk_config.max_daily_notional})"

        if self._open_positions >= self.risk_config.max_open_positions:
            return f"At max open positions ({self._open_positions})"

        risk_events = self.ledger.get_risk_events_count(hours=1)
        
        if risk_events.get("partial_fill", 0) >= self.risk_config.max_partial_fills_per_hour:
            return "Too many partial fills in the last hour"

        if risk_events.get("reject", 0) >= self.risk_config.max_rejects_per_hour:
            return "Too many order rejects in the last hour"

        if risk_events.get("ws_disconnect", 0) >= self.risk_config.max_ws_disconnects_per_hour:
            return "Too many WebSocket disconnects in the last hour"

        return None

    async def execute_signal(
        self,
        signal: TradeSignal,
        market: MarketBook,
    ) -> ExecutionResult:
        """
        Execute a complete-set trade based on a signal.
        
        In paper mode, simulates execution without placing real orders.
        """
        market_id = signal.market_id

        if self._halted:
            logger.info(f"Execution halted, skipping signal for {market_id}")
            return ExecutionResult(success=False, error="Execution halted")

        if not signal.is_tradeable:
            return ExecutionResult(success=False, error=f"Signal not tradeable: {signal.reason}")

        order_size = self.execution_config.order_size
        total_price = signal.yes_ask + signal.no_ask

        risk_check = self._check_risk_limits(order_size, total_price)
        if risk_check:
            logger.warning(f"Risk limit hit: {risk_check}")
            self.ledger.log_risk_event("risk_limit", market_id, {"reason": risk_check})
            return ExecutionResult(success=False, error=risk_check)

        self._state[market_id] = ExecutionState.SIGNAL_DETECTED
        self.signal_engine.set_in_flight(market_id)

        tradeset_id = self.ledger.create_tradeset(market_id)

        try:
            self._state[market_id] = ExecutionState.PLACING_ORDERS

            if self.paper_mode:
                result = await self._execute_paper(
                    market_id, market, signal, order_size, tradeset_id
                )
            else:
                result = await self._execute_live(
                    market_id, market, signal, order_size, tradeset_id
                )

            if result.success:
                self._state[market_id] = ExecutionState.SUCCESS
                self._daily_notional += order_size * total_price
                self._open_positions += 1
            else:
                self._state[market_id] = ExecutionState.FAILED

            return result

        except Exception as e:
            logger.error(f"Execution error for {market_id}: {e}")
            self._state[market_id] = ExecutionState.FAILED
            self.ledger.update_tradeset(tradeset_id, status="failed")
            self.ledger.log_risk_event("execution_error", market_id, {"error": str(e)})
            return ExecutionResult(success=False, tradeset_id=tradeset_id, error=str(e))

        finally:
            self.signal_engine.clear_in_flight(market_id)
            self.signal_engine.set_cooldown(
                market_id, self.execution_config.cooldown_seconds
            )
            self._state[market_id] = ExecutionState.COOLDOWN
            await asyncio.sleep(0.1)
            self._state[market_id] = ExecutionState.IDLE

    async def _execute_paper(
        self,
        market_id: str,
        market: MarketBook,
        signal: TradeSignal,
        order_size: Decimal,
        tradeset_id: int,
    ) -> ExecutionResult:
        """Execute in paper mode - simulate without real orders."""
        now = datetime.now().timestamp()

        yes_order_id = f"paper-yes-{uuid.uuid4().hex[:8]}"
        no_order_id = f"paper-no-{uuid.uuid4().hex[:8]}"

        yes_order = Order(
            order_id=yes_order_id,
            market_id=market_id,
            token_id=market.yes_token.token_id,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            price=signal.yes_ask,
            size=order_size,
            status=OrderStatus.FILLED,
            filled_size=order_size,
            avg_fill_price=signal.yes_ask,
            fee=order_size * signal.yes_ask * self.adapter.fee_rate,
            created_at=now,
            updated_at=now,
        )

        no_order = Order(
            order_id=no_order_id,
            market_id=market_id,
            token_id=market.no_token.token_id,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            price=signal.no_ask,
            size=order_size,
            status=OrderStatus.FILLED,
            filled_size=order_size,
            avg_fill_price=signal.no_ask,
            fee=order_size * signal.no_ask * self.adapter.fee_rate,
            created_at=now,
            updated_at=now,
        )

        self.ledger.log_order(
            yes_order_id, tradeset_id, market_id, market.yes_token.token_id,
            "BUY", "LIMIT", signal.yes_ask, order_size, "FILLED"
        )
        self.ledger.log_order(
            no_order_id, tradeset_id, market_id, market.no_token.token_id,
            "BUY", "LIMIT", signal.no_ask, order_size, "FILLED"
        )

        yes_cost = order_size * signal.yes_ask
        no_cost = order_size * signal.no_ask
        total_fees = yes_order.fee + no_order.fee

        expected_payout = order_size * Decimal("1.0")
        theoretical_pnl = expected_payout - yes_cost - no_cost - total_fees

        self.ledger.update_tradeset(
            tradeset_id,
            status="filled",
            yes_order_id=yes_order_id,
            no_order_id=no_order_id,
            yes_cost=yes_cost,
            no_cost=no_cost,
            total_fees=total_fees,
            realized_pnl=theoretical_pnl,
        )

        logger.info(
            f"[PAPER] Complete-set executed for {market_id}: "
            f"YES@{signal.yes_ask} + NO@{signal.no_ask} = {signal.sum_cost}, "
            f"edge={signal.edge:.4f}, theoretical_pnl={theoretical_pnl:.4f}"
        )

        return ExecutionResult(
            success=True,
            tradeset_id=tradeset_id,
            yes_order=yes_order,
            no_order=no_order,
        )

    async def _execute_live(
        self,
        market_id: str,
        market: MarketBook,
        signal: TradeSignal,
        order_size: Decimal,
        tradeset_id: int,
    ) -> ExecutionResult:
        """Execute live orders with partial-fill protection."""
        try:
            yes_order = await self.adapter.place_order(
                market_id=market_id,
                token_id=market.yes_token.token_id,
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                price=signal.yes_ask,
                size=order_size,
            )

            self.ledger.log_order(
                yes_order.order_id, tradeset_id, market_id, market.yes_token.token_id,
                "BUY", "LIMIT", signal.yes_ask, order_size, yes_order.status.value
            )

            if yes_order.status == OrderStatus.REJECTED:
                self.ledger.log_risk_event("reject", market_id, {"side": "YES"})
                self.ledger.update_tradeset(tradeset_id, status="failed")
                return ExecutionResult(
                    success=False,
                    tradeset_id=tradeset_id,
                    yes_order=yes_order,
                    error="YES order rejected",
                )

        except Exception as e:
            logger.error(f"Failed to place YES order: {e}")
            self.ledger.update_tradeset(tradeset_id, status="failed")
            return ExecutionResult(success=False, tradeset_id=tradeset_id, error=str(e))

        try:
            no_order = await self.adapter.place_order(
                market_id=market_id,
                token_id=market.no_token.token_id,
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                price=signal.no_ask,
                size=order_size,
            )

            self.ledger.log_order(
                no_order.order_id, tradeset_id, market_id, market.no_token.token_id,
                "BUY", "LIMIT", signal.no_ask, order_size, no_order.status.value
            )

            if no_order.status == OrderStatus.REJECTED:
                self.ledger.log_risk_event("reject", market_id, {"side": "NO"})
                await self._handle_partial_fill(market_id, tradeset_id, yes_order, None)
                return ExecutionResult(
                    success=False,
                    tradeset_id=tradeset_id,
                    yes_order=yes_order,
                    no_order=no_order,
                    error="NO order rejected, YES leg exposed",
                )

        except Exception as e:
            logger.error(f"Failed to place NO order: {e}")
            await self._handle_partial_fill(market_id, tradeset_id, yes_order, None)
            return ExecutionResult(
                success=False,
                tradeset_id=tradeset_id,
                yes_order=yes_order,
                error=str(e),
            )

        self._state[market_id] = ExecutionState.WAITING_FILLS

        timeout = self.execution_config.order_timeout_seconds
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            await asyncio.sleep(0.5)

            yes_status = await self.adapter.get_order_status(yes_order.order_id)
            no_status = await self.adapter.get_order_status(no_order.order_id)

            if yes_status:
                yes_order = yes_status
            if no_status:
                no_order = no_status

            yes_filled = yes_order.status == OrderStatus.FILLED
            no_filled = no_order.status == OrderStatus.FILLED

            if yes_filled and no_filled:
                yes_cost = yes_order.filled_size * yes_order.avg_fill_price
                no_cost = no_order.filled_size * no_order.avg_fill_price
                total_fees = yes_order.fee + no_order.fee

                expected_payout = min(yes_order.filled_size, no_order.filled_size) * Decimal("1.0")
                realized_pnl = expected_payout - yes_cost - no_cost - total_fees

                self.ledger.update_tradeset(
                    tradeset_id,
                    status="filled",
                    yes_order_id=yes_order.order_id,
                    no_order_id=no_order.order_id,
                    yes_cost=yes_cost,
                    no_cost=no_cost,
                    total_fees=total_fees,
                    realized_pnl=realized_pnl,
                )

                logger.info(f"Complete-set filled for {market_id}, realized_pnl={realized_pnl:.4f}")
                return ExecutionResult(
                    success=True,
                    tradeset_id=tradeset_id,
                    yes_order=yes_order,
                    no_order=no_order,
                )

            if yes_order.status == OrderStatus.PARTIALLY_FILLED or no_order.status == OrderStatus.PARTIALLY_FILLED:
                self.ledger.log_risk_event("partial_fill", market_id)
                await self._handle_partial_fill(market_id, tradeset_id, yes_order, no_order)
                return ExecutionResult(
                    success=False,
                    tradeset_id=tradeset_id,
                    yes_order=yes_order,
                    no_order=no_order,
                    error="Partial fill detected",
                )

        logger.warning(f"Order timeout for {market_id}")
        await self._handle_partial_fill(market_id, tradeset_id, yes_order, no_order)
        return ExecutionResult(
            success=False,
            tradeset_id=tradeset_id,
            yes_order=yes_order,
            no_order=no_order,
            error="Order timeout",
        )

    async def _handle_partial_fill(
        self,
        market_id: str,
        tradeset_id: int,
        yes_order: Optional[Order],
        no_order: Optional[Order],
    ) -> None:
        """Handle partial fill situation - cancel unfilled orders and log."""
        self._state[market_id] = ExecutionState.PARTIAL_FILL_PROTECT
        logger.warning(f"Partial fill protection triggered for {market_id}")

        if yes_order and yes_order.status in [OrderStatus.OPEN, OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED]:
            try:
                await self.adapter.cancel_order(yes_order.order_id)
                logger.info(f"Cancelled YES order {yes_order.order_id}")
            except Exception as e:
                logger.error(f"Failed to cancel YES order: {e}")

        if no_order and no_order.status in [OrderStatus.OPEN, OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED]:
            try:
                await self.adapter.cancel_order(no_order.order_id)
                logger.info(f"Cancelled NO order {no_order.order_id}")
            except Exception as e:
                logger.error(f"Failed to cancel NO order: {e}")

        self.ledger.update_tradeset(tradeset_id, status="partial_fill")

        if self.risk_config.halt_on_partial_fill:
            self.halt()
            logger.warning("Halting execution due to partial fill (configured behavior)")
