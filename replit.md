# Project Alpha - Complete-Set Arbitrage Bot

## Overview
A private, personal PoC trading bot that detects and executes **complete-set arbitrage** on prediction markets. When a binary market's YES + NO asks sum to less than $1.00 (after fees), buying both guarantees profit at resolution.

**Mode**: Paper trading by default (no real orders), with kill switch and risk controls.

## Architecture

### Core Strategy
Complete-set arbitrage exploits inefficiencies where:
- `YES_ask + NO_ask + fees < $1.00`
- Both sides have sufficient depth
- Market is active and not in cooldown

### Project Structure
```
project/
├── src/
│   ├── adapters/           # Venue adapters (Polymarket, Mock)
│   │   ├── base.py         # VenueAdapter interface
│   │   ├── mock.py         # Mock adapter for testing
│   │   └── polymarket.py   # Polymarket CLOB adapter
│   ├── marketdata/
│   │   └── orderbook_state.py  # Order book state management
│   ├── strategy/
│   │   └── signal_engine.py    # Opportunity detection
│   ├── execution/
│   │   ├── executor.py     # Trade execution state machine
│   │   └── risk.py         # Kill switch and risk management
│   ├── storage/
│   │   └── ledger.py       # SQLite audit trail
│   ├── cli/
│   │   └── commands.py     # CLI interface
│   ├── reporting/
│   │   └── report.py       # Performance reports
│   ├── config.py           # Configuration loading
│   └── main.py             # Bot orchestrator
├── app.py                  # Streamlit dashboard
├── config.yaml             # Production config
├── config_mock.yaml        # Mock testing config
└── arb_ledger.db          # SQLite database (auto-created)
```

### Module Descriptions

| Module | Purpose |
|--------|---------|
| `adapters/base.py` | Venue-agnostic interface for market data and orders |
| `adapters/polymarket.py` | Polymarket CLOB WebSocket + REST implementation |
| `adapters/mock.py` | Synthetic market data for testing |
| `orderbook_state.py` | Tracks best bid/ask for YES and NO tokens |
| `signal_engine.py` | Detects complete-set opportunities |
| `executor.py` | Executes trades with partial-fill protection |
| `risk.py` | Kill switch and position management |
| `ledger.py` | SQLite storage for full audit trail |
| `commands.py` | CLI: run, status, report, halt, resume |
| `main.py` | Async bot orchestrator |

## Running the Bot

### Paper Mode (Testing)
```bash
# With mock adapter (synthetic data)
python -m src.cli.commands run --paper -c config_mock.yaml

# With Polymarket (real market data, no real orders)
python -m src.cli.commands run --paper -c config.yaml
```

### CLI Commands
```bash
python -m src.cli.commands status    # Show current status
python -m src.cli.commands report    # Generate performance report
python -m src.cli.commands halt      # Stop trading
python -m src.cli.commands resume    # Resume trading
```

### Streamlit Dashboard
```bash
streamlit run app.py --server.port 5000
```

## Configuration

### config.yaml
- `venue.name`: "polymarket" or "mock"
- `strategy.min_edge`: Minimum profit to trigger trade (default: 0.01)
- `strategy.min_depth`: Minimum size at best ask (default: 10)
- `execution.order_size`: Base order size (default: 10)
- `risk.halt_on_partial_fill`: Auto-halt on partial fills (default: true)
- `paper_mode`: true for simulation, false for live trading

### Environment Variables (for live trading)
```
POLYMARKET_API_KEY=your_key
POLYMARKET_API_SECRET=your_secret
POLYMARKET_PASSPHRASE=your_passphrase
```

## Key Features

1. **WebSocket Market Data**: Real-time order book updates via Polymarket CLOB WebSocket
2. **Signal Detection**: Evaluates every book update for arbitrage opportunities
3. **Paper Mode**: Full simulation without placing real orders
4. **Partial-Fill Protection**: Cancels unfilled orders and triggers halt on partial fills
5. **Kill Switch**: Auto-halt on repeated failures (partial fills, rejects, disconnects)
6. **Full Audit Trail**: SQLite ledger tracks every opportunity, order, fill, and risk event
7. **CLI + Dashboard**: Rich CLI for control, Streamlit dashboard for monitoring

## Technology Stack
- Python 3.11+ with asyncio
- websockets (real-time market data)
- httpx (async REST API)
- SQLite (ledger storage)
- Rich (CLI formatting)
- Streamlit (dashboard)
- pyyaml (configuration)

## Recent Changes
- 2026-01-03: Complete rebuild for complete-set arbitrage strategy
  - Replaced cross-venue arbitrage with single-venue complete-set approach
  - Added WebSocket-based real-time market data ingestion
  - Implemented venue-agnostic adapter pattern (Polymarket, Mock)
  - Built execution engine with partial-fill protection
  - Added kill switch and risk management
  - Created CLI commands and Streamlit dashboard
  - Full SQLite audit trail for all trading activity

## Safety Notes
- Paper mode is the default - no real orders unless explicitly enabled
- Kill switch triggers on repeated failures to prevent catastrophic losses
- Halt-on-partial-fill enabled by default to protect against single-leg exposure
- Never log or expose API keys
