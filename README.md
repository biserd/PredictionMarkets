# Polymarket Complete-Set Arbitrage Bot

A high-frequency arbitrage bot that detects and executes **complete-set arbitrage** opportunities on Polymarket prediction markets.

## What is Complete-Set Arbitrage?

In binary prediction markets, every outcome resolves to exactly $1.00. Complete-set arbitrage exploits pricing inefficiencies where:

```
YES_price + NO_price + fees < $1.00
```

When this occurs, buying both YES and NO tokens guarantees profit at resolution, regardless of the outcome.

**Example:**
- YES token ask: $0.45
- NO token ask: $0.52
- Total cost: $0.97
- Resolution payout: $1.00
- **Guaranteed profit: $0.03 (3%)**

## Features

- **Real-time WebSocket data** - Streams order book updates from Polymarket CLOB
- **Sub-second opportunity detection** - Evaluates every book update for arbitrage
- **Paper trading mode** - Full simulation without placing real orders (default)
- **Partial-fill protection** - Cancels unfilled legs and halts on partial fills
- **Kill switch** - Auto-halts on repeated failures to prevent losses
- **Full audit trail** - SQLite ledger tracks every opportunity, order, and fill
- **CLI + Dashboard** - Rich terminal interface and Streamlit web dashboard
- **Venue-agnostic architecture** - Adapter pattern supports multiple venues

## Quick Start

### Prerequisites

- Python 3.11+
- Non-US server (Polymarket blocks US IPs)

### Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/polymarket-arb-bot.git
cd polymarket-arb-bot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

1. Copy the environment template:
```bash
cp deploy/.env.example .env
```

2. Edit `.env` with your Polymarket credentials (for live trading):
```bash
POLYMARKET_API_KEY=your_key
POLYMARKET_API_SECRET=your_secret
POLYMARKET_PASSPHRASE=your_passphrase
```

3. Review `config.yaml` for strategy parameters.

### Run in Paper Mode

```bash
# With mock data (for testing)
python -m src.cli.commands run --paper -c config_mock.yaml

# With real Polymarket data (no real orders)
python -m src.cli.commands run --paper -c config.yaml
```

### Web Dashboard

```bash
streamlit run app.py --server.port 5000
```

## Project Structure

```
polymarket-arb-bot/
├── src/
│   ├── adapters/              # Venue adapters
│   │   ├── base.py            # VenueAdapter interface
│   │   ├── mock.py            # Mock adapter for testing
│   │   └── polymarket.py      # Polymarket CLOB adapter
│   ├── marketdata/
│   │   └── orderbook_state.py # Order book state management
│   ├── strategy/
│   │   └── signal_engine.py   # Opportunity detection
│   ├── execution/
│   │   ├── executor.py        # Trade execution engine
│   │   └── risk.py            # Kill switch & risk management
│   ├── storage/
│   │   └── ledger.py          # SQLite audit trail
│   ├── cli/
│   │   └── commands.py        # CLI interface
│   ├── reporting/
│   │   └── report.py          # Performance reports
│   ├── config.py              # Configuration loader
│   └── main.py                # Bot orchestrator
├── deploy/                    # Deployment files
│   ├── README.md              # Deployment guide
│   ├── install.sh             # Ubuntu setup script
│   ├── arbbot.service         # Systemd service
│   └── .env.example           # Environment template
├── app.py                     # Streamlit dashboard
├── config.yaml                # Production config
├── config_mock.yaml           # Mock testing config
└── requirements.txt           # Python dependencies
```

## CLI Commands

```bash
# Run the bot
python -m src.cli.commands run --paper -c config.yaml

# Check current status
python -m src.cli.commands status

# Generate performance report
python -m src.cli.commands report

# Halt trading (emergency stop)
python -m src.cli.commands halt

# Resume trading
python -m src.cli.commands resume
```

## Configuration

### config.yaml

```yaml
venue:
  name: polymarket           # or "mock" for testing

strategy:
  min_edge: 0.01             # Minimum profit threshold ($0.01)
  min_depth: 10              # Minimum size at best ask
  cooldown_seconds: 5        # Cooldown between trades on same market

execution:
  order_size: 10             # Base order size in tokens
  timeout_seconds: 30        # Order timeout before cancel

risk:
  halt_on_partial_fill: true # Auto-halt if only one leg fills
  max_consecutive_failures: 3 # Kill switch threshold

paper_mode: true             # Simulation mode (no real orders)
```

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `POLYMARKET_API_KEY` | Polymarket API key | For live trading |
| `POLYMARKET_API_SECRET` | Polymarket API secret | For live trading |
| `POLYMARKET_PASSPHRASE` | Polymarket passphrase | For live trading |
| `POLYMARKET_PROXY_URL` | HTTP proxy URL | If behind geo-restriction |

## How It Works

### 1. Market Data Ingestion
The bot connects to Polymarket's WebSocket API and subscribes to order book updates for active markets.

### 2. Opportunity Detection
On every book update, the SignalEngine evaluates:
- Combined cost of YES + NO at best asks
- Available depth at those prices
- Market cooldown status
- Minimum edge threshold

### 3. Trade Execution
When an opportunity is found:
1. Submit buy orders for both YES and NO tokens
2. Monitor for fills with timeout
3. If partial fill occurs, cancel unfilled leg and trigger halt
4. Log all activity to SQLite ledger

### 4. Risk Management
The kill switch monitors for:
- Partial fills (single-leg exposure)
- Order rejections
- WebSocket disconnections
- Consecutive failures

## Deployment

The bot requires a **non-US server** due to Polymarket's geo-restrictions.

### DigitalOcean (Recommended)

1. Create an Ubuntu 24.04 droplet in Amsterdam or any EU region ($8/month)
2. Clone this repo and run the install script:

```bash
git clone https://github.com/YOUR_USERNAME/polymarket-arb-bot.git
cd polymarket-arb-bot
chmod +x deploy/install.sh
sudo ./deploy/install.sh
```

3. Configure your credentials:
```bash
cp deploy/.env.example /home/arbbot/arb-bot/.env
nano /home/arbbot/arb-bot/.env
```

4. Start the bot:
```bash
sudo systemctl start arbbot
sudo systemctl status arbbot
```

See [deploy/README.md](deploy/README.md) for detailed deployment instructions.

## Safety Features

| Feature | Description |
|---------|-------------|
| Paper Mode | Default mode - simulates trades without real orders |
| Kill Switch | Auto-halts after consecutive failures |
| Partial-Fill Protection | Cancels unfilled legs, halts to prevent exposure |
| Cooldown | Prevents rapid-fire trades on same market |
| Audit Trail | Full SQLite log of all trading activity |
| Position Limits | Configurable maximum position sizes |

## Performance Monitoring

### SQLite Ledger

All trading activity is logged to `arb_ledger.db`:

```sql
-- View recent opportunities
SELECT * FROM opportunities ORDER BY timestamp DESC LIMIT 10;

-- View trade history
SELECT * FROM tradesets ORDER BY created_at DESC LIMIT 10;

-- Check risk events
SELECT * FROM risk_events ORDER BY timestamp DESC;
```

### Streamlit Dashboard

The web dashboard provides:
- Real-time bot status
- Opportunity history
- Trade history
- PnL tracking
- Risk event log

## Testing

### Mock Adapter

Use the mock adapter for testing without connecting to Polymarket:

```bash
python -m src.cli.commands run --paper -c config_mock.yaml
```

The mock adapter generates synthetic market data with configurable arbitrage opportunities.

## Troubleshooting

### Connection Issues

If you see "US IP detected" or connection failures:
- Ensure you're running from a non-US server
- Check if proxy is configured in `.env`

### No Opportunities Found

Complete-set arbitrage opportunities are rare. The bot will:
- Log "Scanning..." periodically to confirm it's running
- Alert immediately when opportunities are detected

### High Memory Usage

```bash
# Restart the bot to clear memory
sudo systemctl restart arbbot
```

## Contributing

This is a personal project, but suggestions are welcome. Please open an issue first to discuss any changes.

## Disclaimer

**This software is for educational purposes only.** 

- Trading prediction markets involves significant risk
- Past performance does not guarantee future results
- Always test thoroughly in paper mode before live trading
- The authors are not responsible for any financial losses
- Ensure compliance with all applicable laws in your jurisdiction

## License

MIT License - see [LICENSE](LICENSE) for details.
