"""
Project Alpha Configuration
Personal Prediction Market Engine Settings
"""

# Whale wallet addresses to monitor on Polymarket (Polygon)
WHALE_ADDRESSES = [
    "0x1234567890abcdef1234567890abcdef12345678",  # Example whale 1
    "0xabcdef1234567890abcdef1234567890abcdef12",  # Example whale 2
]

# Minimum trade size to alert (in USDC)
MIN_TRADE_SIZE = 500

# Arbitrage settings
ARB_THRESHOLD = 0.02  # Minimum spread to trigger alert (2%)
MIN_LIQUIDITY = 100   # Minimum liquidity in USD

# Fuzzy matching threshold (0-100)
FUZZY_MATCH_THRESHOLD = 80

# API refresh interval in seconds
REFRESH_INTERVAL = 5

# Polymarket API endpoints
POLYMARKET_API_URL = "https://gamma-api.polymarket.com"
POLYMARKET_CLOB_WS = "wss://ws-subscriptions-clob.polymarket.com/ws"

# Kalshi API endpoints
KALSHI_API_URL = "https://api.elections.kalshi.com/trade-api/v2"

# Estimated trading fees (as decimal)
POLYMARKET_FEE = 0.02  # 2%
KALSHI_FEE = 0.02      # 2%

# Database settings
DATABASE_PATH = "project_alpha.db"

# Market categories to scan
CATEGORIES = ["sports", "politics", "crypto", "economy"]

# Proxy settings for geo-compliance (NFR-2)
# Set POLYMARKET_PROXY_URL env var to route through Netherlands/Non-US proxy
# Example: "http://nl-proxy.example.com:8080" or "socks5://proxy.example.com:1080"
POLYMARKET_PROXY_URL = None  # Set via environment variable

# Auto-scan settings
AUTO_SCAN_ENABLED = True
AUTO_SCAN_INTERVAL = 5  # seconds
