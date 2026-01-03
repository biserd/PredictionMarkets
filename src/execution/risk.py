"""
Risk management and kill switch logic.
"""
import logging
from datetime import datetime
from typing import Optional, Callable

from src.storage.ledger import Ledger
from src.config import RiskConfig

logger = logging.getLogger(__name__)


class KillSwitch:
    """
    Kill switch for emergency trading halt.
    
    Monitors for dangerous conditions and triggers halt when thresholds are exceeded.
    """

    def __init__(
        self,
        ledger: Ledger,
        risk_config: RiskConfig,
        halt_callback: Optional[Callable[[], None]] = None,
    ):
        self.ledger = ledger
        self.risk_config = risk_config
        self.halt_callback = halt_callback
        self._triggered = False
        self._trigger_reason: Optional[str] = None
        self._trigger_time: Optional[datetime] = None

    @property
    def is_triggered(self) -> bool:
        """Check if kill switch has been triggered."""
        return self._triggered

    @property
    def trigger_reason(self) -> Optional[str]:
        """Get reason for trigger if triggered."""
        return self._trigger_reason

    def check_conditions(self) -> bool:
        """
        Check all kill switch conditions.
        Returns True if kill switch should trigger.
        """
        risk_events = self.ledger.get_risk_events_count(hours=1)

        partial_fills = risk_events.get("partial_fill", 0)
        if partial_fills >= self.risk_config.max_partial_fills_per_hour:
            self._trigger(f"Too many partial fills: {partial_fills}")
            return True

        rejects = risk_events.get("reject", 0)
        if rejects >= self.risk_config.max_rejects_per_hour:
            self._trigger(f"Too many order rejects: {rejects}")
            return True

        disconnects = risk_events.get("ws_disconnect", 0)
        if disconnects >= self.risk_config.max_ws_disconnects_per_hour:
            self._trigger(f"Too many WebSocket disconnects: {disconnects}")
            return True

        return False

    def _trigger(self, reason: str) -> None:
        """Trigger the kill switch."""
        if self._triggered:
            return

        self._triggered = True
        self._trigger_reason = reason
        self._trigger_time = datetime.now()

        logger.critical(f"KILL SWITCH TRIGGERED: {reason}")
        self.ledger.log_risk_event("kill_switch", None, {"reason": reason})

        if self.halt_callback:
            self.halt_callback()

    def reset(self) -> None:
        """Reset the kill switch (requires manual intervention)."""
        if self._triggered:
            logger.info(f"Kill switch reset. Was triggered at {self._trigger_time} for: {self._trigger_reason}")
            self._triggered = False
            self._trigger_reason = None
            self._trigger_time = None

    def manual_trigger(self, reason: str = "Manual trigger") -> None:
        """Manually trigger the kill switch."""
        self._trigger(reason)


class PositionManager:
    """
    Tracks open positions and enforces position limits.
    """

    def __init__(self, max_positions: int):
        self.max_positions = max_positions
        self._positions: dict = {}

    @property
    def position_count(self) -> int:
        """Number of open positions."""
        return len(self._positions)

    @property
    def can_open_position(self) -> bool:
        """Check if we can open a new position."""
        return self.position_count < self.max_positions

    def open_position(self, market_id: str, size: float, cost: float) -> bool:
        """
        Record a new position.
        Returns False if position limit would be exceeded.
        """
        if not self.can_open_position:
            return False

        self._positions[market_id] = {
            "size": size,
            "cost": cost,
            "opened_at": datetime.now(),
        }
        return True

    def close_position(self, market_id: str, payout: float = 0) -> Optional[float]:
        """
        Close a position and return realized PnL.
        Returns None if position doesn't exist.
        """
        position = self._positions.pop(market_id, None)
        if position is None:
            return None

        return payout - position["cost"]

    def get_position(self, market_id: str) -> Optional[dict]:
        """Get details of a specific position."""
        return self._positions.get(market_id)

    def get_all_positions(self) -> dict:
        """Get all open positions."""
        return self._positions.copy()
