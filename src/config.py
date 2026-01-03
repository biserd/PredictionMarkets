"""
Configuration management for the arbitrage bot.
Loads from config.yaml and environment variables.
"""
import os
import yaml
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional
from pathlib import Path


@dataclass
class StrategyConfig:
    min_edge: Decimal = Decimal("0.01")
    cost_buffer: Decimal = Decimal("0.005")
    min_depth: Decimal = Decimal("10")


@dataclass
class ExecutionConfig:
    order_size: Decimal = Decimal("10")
    max_attempts_per_round: int = 3
    order_timeout_seconds: float = 5.0
    max_inflight_seconds: float = 30.0
    cooldown_seconds: float = 2.0


@dataclass
class RiskConfig:
    max_daily_notional: Decimal = Decimal("1000")
    max_open_positions: int = 5
    halt_on_partial_fill: bool = True
    max_partial_fills_per_hour: int = 3
    max_rejects_per_hour: int = 10
    max_ws_disconnects_per_hour: int = 5


@dataclass
class DataConfig:
    sqlite_path: str = "arb_ledger.db"
    log_level: str = "INFO"
    log_json: bool = False


@dataclass
class WebSocketConfig:
    reconnect_delay_initial: float = 1.0
    reconnect_delay_max: float = 60.0
    reconnect_backoff_factor: float = 2.0
    heartbeat_interval: float = 30.0
    snapshot_on_reconnect: bool = True


@dataclass
class VenueConfig:
    name: str = "polymarket"
    api_url: str = "https://clob.polymarket.com"
    ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    proxy_url: Optional[str] = None


@dataclass
class Config:
    venue: VenueConfig = field(default_factory=VenueConfig)
    markets: List[str] = field(default_factory=list)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    data: DataConfig = field(default_factory=DataConfig)
    websocket: WebSocketConfig = field(default_factory=WebSocketConfig)
    paper_mode: bool = True


def load_config(config_path: str = "config.yaml") -> Config:
    """
    Load configuration from YAML file and environment variables.
    Environment variables override YAML values.
    """
    config = Config()

    if Path(config_path).exists():
        with open(config_path, 'r') as f:
            yaml_config = yaml.safe_load(f) or {}

        if 'venue' in yaml_config:
            v = yaml_config['venue']
            config.venue = VenueConfig(
                name=v.get('name', config.venue.name),
                api_url=v.get('api_url', config.venue.api_url),
                ws_url=v.get('ws_url', config.venue.ws_url),
                proxy_url=v.get('proxy_url'),
            )

        if 'markets' in yaml_config:
            config.markets = yaml_config['markets']

        if 'strategy' in yaml_config:
            s = yaml_config['strategy']
            config.strategy = StrategyConfig(
                min_edge=Decimal(str(s.get('min_edge', config.strategy.min_edge))),
                cost_buffer=Decimal(str(s.get('cost_buffer', config.strategy.cost_buffer))),
                min_depth=Decimal(str(s.get('min_depth', config.strategy.min_depth))),
            )

        if 'execution' in yaml_config:
            e = yaml_config['execution']
            config.execution = ExecutionConfig(
                order_size=Decimal(str(e.get('order_size', config.execution.order_size))),
                max_attempts_per_round=e.get('max_attempts_per_round', config.execution.max_attempts_per_round),
                order_timeout_seconds=e.get('order_timeout_seconds', config.execution.order_timeout_seconds),
                max_inflight_seconds=e.get('max_inflight_seconds', config.execution.max_inflight_seconds),
                cooldown_seconds=e.get('cooldown_seconds', config.execution.cooldown_seconds),
            )

        if 'risk' in yaml_config:
            r = yaml_config['risk']
            config.risk = RiskConfig(
                max_daily_notional=Decimal(str(r.get('max_daily_notional', config.risk.max_daily_notional))),
                max_open_positions=r.get('max_open_positions', config.risk.max_open_positions),
                halt_on_partial_fill=r.get('halt_on_partial_fill', config.risk.halt_on_partial_fill),
                max_partial_fills_per_hour=r.get('max_partial_fills_per_hour', config.risk.max_partial_fills_per_hour),
                max_rejects_per_hour=r.get('max_rejects_per_hour', config.risk.max_rejects_per_hour),
                max_ws_disconnects_per_hour=r.get('max_ws_disconnects_per_hour', config.risk.max_ws_disconnects_per_hour),
            )

        if 'data' in yaml_config:
            d = yaml_config['data']
            config.data = DataConfig(
                sqlite_path=d.get('sqlite_path', config.data.sqlite_path),
                log_level=d.get('log_level', config.data.log_level),
                log_json=d.get('log_json', config.data.log_json),
            )

        if 'websocket' in yaml_config:
            w = yaml_config['websocket']
            config.websocket = WebSocketConfig(
                reconnect_delay_initial=w.get('reconnect_delay_initial', config.websocket.reconnect_delay_initial),
                reconnect_delay_max=w.get('reconnect_delay_max', config.websocket.reconnect_delay_max),
                reconnect_backoff_factor=w.get('reconnect_backoff_factor', config.websocket.reconnect_backoff_factor),
                heartbeat_interval=w.get('heartbeat_interval', config.websocket.heartbeat_interval),
                snapshot_on_reconnect=w.get('snapshot_on_reconnect', config.websocket.snapshot_on_reconnect),
            )

        config.paper_mode = yaml_config.get('paper_mode', config.paper_mode)

    env_proxy = os.environ.get('POLYMARKET_PROXY_URL')
    if env_proxy:
        config.venue.proxy_url = env_proxy

    env_api_key = os.environ.get('POLYMARKET_API_KEY')
    env_api_secret = os.environ.get('POLYMARKET_API_SECRET')
    env_passphrase = os.environ.get('POLYMARKET_PASSPHRASE')

    return config
