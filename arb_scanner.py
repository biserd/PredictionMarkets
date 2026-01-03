"""
Project Alpha - Arbitrage Scanner Module
Fetches prices from Polymarket and Kalshi, finds arbitrage opportunities
"""

import requests
import pandas as pd
from thefuzz import fuzz
from typing import List, Dict, Tuple, Optional
import config
import database
import os


def get_polymarket_proxies() -> Optional[Dict]:
    """Get proxy configuration for Polymarket API requests (geo-compliance)."""
    proxy_url = os.environ.get("POLYMARKET_PROXY_URL") or config.POLYMARKET_PROXY_URL
    if proxy_url:
        return {"http": proxy_url, "https": proxy_url}
    return None


def fetch_polymarket_markets() -> List[Dict]:
    """Fetch active markets from Polymarket Gamma API."""
    try:
        url = f"{config.POLYMARKET_API_URL}/markets"
        params = {
            "closed": "false",
            "limit": 100,
        }
        proxies = get_polymarket_proxies()
        response = requests.get(url, params=params, timeout=10, proxies=proxies)
        response.raise_for_status()
        markets = response.json()
        
        processed = []
        for market in markets:
            if market.get("outcomes") and len(market.get("outcomePrices", [])) >= 2:
                try:
                    prices = market.get("outcomePrices", [])
                    yes_price = float(prices[0]) if prices else 0
                    no_price = float(prices[1]) if len(prices) > 1 else 0
                    
                    processed.append({
                        "id": market.get("id", ""),
                        "title": market.get("question", market.get("title", "")),
                        "category": market.get("category", ""),
                        "yes_price": yes_price,
                        "no_price": no_price,
                        "liquidity": float(market.get("liquidityNum", 0)),
                        "volume": float(market.get("volumeNum", 0)),
                        "source": "polymarket"
                    })
                except (ValueError, TypeError, IndexError):
                    continue
        
        return processed
    except requests.RequestException as e:
        print(f"Error fetching Polymarket markets: {e}")
        return []


def fetch_kalshi_markets() -> List[Dict]:
    """Fetch active markets from Kalshi API."""
    try:
        url = f"{config.KALSHI_API_URL}/markets"
        headers = {
            "Accept": "application/json",
        }
        
        kalshi_api_key = os.environ.get("KALSHI_API_KEY")
        if kalshi_api_key:
            headers["Authorization"] = f"Bearer {kalshi_api_key}"
        
        params = {
            "status": "open",
            "limit": 100,
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        markets = data.get("markets", [])
        
        processed = []
        for market in markets:
            try:
                yes_price = float(market.get("yes_bid", 0)) / 100
                no_price = float(market.get("no_bid", 0)) / 100
                
                processed.append({
                    "id": market.get("ticker", ""),
                    "title": market.get("title", ""),
                    "category": market.get("category", ""),
                    "yes_price": yes_price,
                    "no_price": no_price,
                    "liquidity": float(market.get("volume", 0)),
                    "volume": float(market.get("volume_24h", 0)),
                    "source": "kalshi"
                })
            except (ValueError, TypeError):
                continue
        
        return processed
    except requests.RequestException as e:
        print(f"Error fetching Kalshi markets: {e}")
        return []


def fuzzy_match_markets(
    poly_markets: List[Dict],
    kalshi_markets: List[Dict],
    threshold: int = None
) -> List[Tuple[Dict, Dict, int]]:
    """
    Match markets between Polymarket and Kalshi using fuzzy string matching.
    Returns list of (poly_market, kalshi_market, match_score) tuples.
    """
    if threshold is None:
        threshold = config.FUZZY_MATCH_THRESHOLD
    
    matches = []
    
    for poly in poly_markets:
        poly_title = poly["title"].lower().strip()
        best_match = None
        best_score = 0
        
        for kalshi in kalshi_markets:
            kalshi_title = kalshi["title"].lower().strip()
            
            score = fuzz.token_sort_ratio(poly_title, kalshi_title)
            
            if score > best_score and score >= threshold:
                best_score = score
                best_match = kalshi
        
        if best_match:
            matches.append((poly, best_match, best_score))
    
    return matches


def calculate_arbitrage_spread(
    poly_yes: float,
    kalshi_no: float,
    include_fees: bool = True
) -> Tuple[float, float]:
    """
    Calculate arbitrage spread and ROI.
    Strategy: Buy YES on Poly, Buy NO on Kalshi
    Returns (spread, roi_percent)
    """
    total_cost = poly_yes + kalshi_no
    
    if include_fees:
        fees = (poly_yes * config.POLYMARKET_FEE) + (kalshi_no * config.KALSHI_FEE)
        total_cost += fees
    
    spread = 1.00 - total_cost
    roi_percent = (spread / total_cost) * 100 if total_cost > 0 else 0
    
    return spread, roi_percent


def calculate_reverse_spread(
    poly_no: float,
    kalshi_yes: float,
    include_fees: bool = True
) -> Tuple[float, float]:
    """
    Calculate reverse arbitrage spread.
    Strategy: Buy NO on Poly, Buy YES on Kalshi
    Returns (spread, roi_percent)
    """
    total_cost = poly_no + kalshi_yes
    
    if include_fees:
        fees = (poly_no * config.POLYMARKET_FEE) + (kalshi_yes * config.KALSHI_FEE)
        total_cost += fees
    
    spread = 1.00 - total_cost
    roi_percent = (spread / total_cost) * 100 if total_cost > 0 else 0
    
    return spread, roi_percent


def scan_for_arbitrage() -> pd.DataFrame:
    """
    Main scanning function. Fetches markets, matches them, and finds arbitrage.
    Returns DataFrame of opportunities.
    """
    print("Fetching Polymarket markets...")
    poly_markets = fetch_polymarket_markets()
    print(f"Found {len(poly_markets)} Polymarket markets")
    
    print("Fetching Kalshi markets...")
    kalshi_markets = fetch_kalshi_markets()
    print(f"Found {len(kalshi_markets)} Kalshi markets")
    
    print("Matching markets...")
    matches = fuzzy_match_markets(poly_markets, kalshi_markets)
    print(f"Found {len(matches)} matched markets")
    
    opportunities = []
    
    for poly, kalshi, match_score in matches:
        min_liquidity = min(poly["liquidity"], kalshi["liquidity"])
        if min_liquidity < config.MIN_LIQUIDITY:
            continue
        
        spread1, roi1 = calculate_arbitrage_spread(poly["yes_price"], kalshi["no_price"])
        spread2, roi2 = calculate_reverse_spread(poly["no_price"], kalshi["yes_price"])
        
        if spread1 > config.ARB_THRESHOLD:
            opp = {
                "poly_market_id": poly["id"],
                "kalshi_market_id": kalshi["id"],
                "market_title": poly["title"],
                "match_score": match_score,
                "strategy": "Buy YES (Poly) + Buy NO (Kalshi)",
                "poly_price": poly["yes_price"],
                "kalshi_price": kalshi["no_price"],
                "total_cost": poly["yes_price"] + kalshi["no_price"],
                "spread": spread1,
                "roi_percent": roi1,
                "min_liquidity": min_liquidity,
                "poly_liquidity": poly["liquidity"],
                "kalshi_liquidity": kalshi["liquidity"],
            }
            opportunities.append(opp)
            
            database.save_arbitrage_opportunity(
                poly["id"], kalshi["id"], poly["title"],
                poly["yes_price"], kalshi["no_price"],
                spread1, roi1, poly["liquidity"], kalshi["liquidity"]
            )
        
        if spread2 > config.ARB_THRESHOLD:
            opp = {
                "poly_market_id": poly["id"],
                "kalshi_market_id": kalshi["id"],
                "market_title": poly["title"],
                "match_score": match_score,
                "strategy": "Buy NO (Poly) + Buy YES (Kalshi)",
                "poly_price": poly["no_price"],
                "kalshi_price": kalshi["yes_price"],
                "total_cost": poly["no_price"] + kalshi["yes_price"],
                "spread": spread2,
                "roi_percent": roi2,
                "min_liquidity": min_liquidity,
                "poly_liquidity": poly["liquidity"],
                "kalshi_liquidity": kalshi["liquidity"],
            }
            opportunities.append(opp)
            
            database.save_arbitrage_opportunity(
                poly["id"], kalshi["id"], poly["title"],
                poly["no_price"], kalshi["yes_price"],
                spread2, roi2, poly["liquidity"], kalshi["liquidity"]
            )
    
    df = pd.DataFrame(opportunities)
    if not df.empty:
        df = df.sort_values("roi_percent", ascending=False)
    
    return df


def get_demo_opportunities() -> pd.DataFrame:
    """Generate demo data for testing when APIs are unavailable."""
    demo_data = [
        {
            "poly_market_id": "POLY_001",
            "kalshi_market_id": "KALSHI_001",
            "market_title": "Will Bitcoin exceed $100,000 by end of 2025?",
            "match_score": 92,
            "strategy": "Buy YES (Poly) + Buy NO (Kalshi)",
            "poly_price": 0.45,
            "kalshi_price": 0.52,
            "total_cost": 0.97,
            "spread": 0.03,
            "roi_percent": 3.09,
            "min_liquidity": 5000,
            "poly_liquidity": 12500,
            "kalshi_liquidity": 5000,
        },
        {
            "poly_market_id": "POLY_002",
            "kalshi_market_id": "KALSHI_002",
            "market_title": "Fed rate cut in January 2026?",
            "match_score": 88,
            "strategy": "Buy NO (Poly) + Buy YES (Kalshi)",
            "poly_price": 0.38,
            "kalshi_price": 0.59,
            "total_cost": 0.97,
            "spread": 0.03,
            "roi_percent": 3.09,
            "min_liquidity": 8200,
            "poly_liquidity": 15000,
            "kalshi_liquidity": 8200,
        },
        {
            "poly_market_id": "POLY_003",
            "kalshi_market_id": "KALSHI_003",
            "market_title": "Super Bowl LXII Winner: Kansas City Chiefs",
            "match_score": 95,
            "strategy": "Buy YES (Poly) + Buy NO (Kalshi)",
            "poly_price": 0.32,
            "kalshi_price": 0.65,
            "total_cost": 0.97,
            "spread": 0.03,
            "roi_percent": 3.09,
            "min_liquidity": 3500,
            "poly_liquidity": 8000,
            "kalshi_liquidity": 3500,
        },
        {
            "poly_market_id": "POLY_004",
            "kalshi_market_id": "KALSHI_004",
            "market_title": "Ethereum merge to PoS completed successfully",
            "match_score": 85,
            "strategy": "Buy YES (Poly) + Buy NO (Kalshi)",
            "poly_price": 0.88,
            "kalshi_price": 0.09,
            "total_cost": 0.97,
            "spread": 0.03,
            "roi_percent": 3.09,
            "min_liquidity": 25000,
            "poly_liquidity": 45000,
            "kalshi_liquidity": 25000,
        },
    ]
    return pd.DataFrame(demo_data)


if __name__ == "__main__":
    print("Starting arbitrage scan...")
    df = scan_for_arbitrage()
    
    if df.empty:
        print("\nNo arbitrage opportunities found. Loading demo data...")
        df = get_demo_opportunities()
    
    print(f"\nFound {len(df)} opportunities:")
    print(df.to_string())
