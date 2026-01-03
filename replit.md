# Project Alpha - Personal Prediction Market Engine

## Overview
A lightweight, self-hosted trading engine that automates the detection of high-probability trades on prediction markets (Polymarket and Kalshi). This POC focuses on two core alpha strategies:
- **Cross-Venue Arbitrage**: Exploiting price discrepancies between regulated (Kalshi) and crypto (Polymarket) venues
- **Whale Copy-Trading**: Mirroring high-conviction trades from specific wallet addresses on the Polygon blockchain

## Project Architecture

### Core Modules
```
project/
├── app.py              # Streamlit dashboard - main entry point
├── config.py           # System configuration and settings
├── database.py         # SQLite database operations
├── arb_scanner.py      # Arbitrage opportunity scanner
├── whale_watch.py      # WebSocket whale trade monitor
├── telegram_bot.py     # Telegram notification service
└── project_alpha.db    # SQLite database (auto-created)
```

### Module Descriptions

| Module | Purpose |
|--------|---------|
| `app.py` | Streamlit dashboard with tabs for arbitrage, whale tracking, trade history |
| `config.py` | Configuration constants (thresholds, API endpoints, whale addresses) |
| `database.py` | SQLite operations for whales, trades, opportunities |
| `arb_scanner.py` | Fetches Polymarket/Kalshi prices, fuzzy matches markets, calculates spreads |
| `whale_watch.py` | WebSocket monitor for large trades on Polymarket |
| `telegram_bot.py` | Formats and sends alerts to Telegram |

## Key Features
1. **Arbitrage Scanner**: Polls APIs every 3-5 seconds, matches markets using fuzzy string matching (thefuzz library)
2. **Spread Calculation**: Formula: `Spread = 1.00 - (Price_Poly_Yes + Price_Kalshi_No) - Fees`
3. **Whale Watchdog**: Monitors specific 0x addresses for trades >$500 via WebSocket
4. **Telegram Alerts**: Push notifications for arbitrage opportunities and whale trades
5. **Trade History**: SQLite-backed logging of all detected opportunities and trades

## Environment Variables

Required for full functionality:
- `TELEGRAM_BOT_TOKEN` - Telegram bot token for alerts
- `TELEGRAM_CHAT_ID` - Target chat/channel ID
- `KALSHI_API_KEY` (optional) - For authenticated Kalshi API requests

## Running the Application

**Dashboard**: The Streamlit app runs on port 5000:
```bash
streamlit run app.py --server.port 5000
```

**Standalone Whale Watcher** (background service):
```bash
python whale_watch.py
```

## Configuration

Key settings in `config.py`:
- `ARB_THRESHOLD = 0.02` (2% minimum spread)
- `MIN_LIQUIDITY = 100` ($100 minimum)
- `MIN_TRADE_SIZE = 500` ($500 minimum whale trade)
- `FUZZY_MATCH_THRESHOLD = 80` (80% title match)

## Technology Stack
- Python 3.11+
- Streamlit (dashboard)
- SQLite (database)
- pandas (data processing)
- thefuzz (fuzzy matching)
- websockets (real-time monitoring)
- python-telegram-bot (notifications)

## Recent Changes
- 2026-01-03: Initial implementation of all core modules
  - Created arbitrage scanner with Polymarket/Kalshi API integration
  - Built whale watchdog with WebSocket support
  - Implemented Streamlit dashboard with 4 tabs
  - Added SQLite database for persistence
  - Integrated Telegram notification system
