"""
Project Alpha - Arbitrage Scanner Module
Fetches prices from Polymarket and Kalshi, finds arbitrage opportunities
"""

import requests
import pandas as pd
import json
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
            "active": "true",
            "closed": "false",
            "limit": 100,
        }
        proxies = get_polymarket_proxies()
        response = requests.get(url, params=params, timeout=15, proxies=proxies)
        response.raise_for_status()
        markets = response.json()
        
        processed = []
        for market in markets:
            try:
                outcomes_raw = market.get("outcomes", "[]")
                prices_raw = market.get("outcomePrices", "[]")
                
                if isinstance(outcomes_raw, str):
                    outcomes = json.loads(outcomes_raw)
                else:
                    outcomes = outcomes_raw
                    
                if isinstance(prices_raw, str):
                    prices = json.loads(prices_raw)
                else:
                    prices = prices_raw
                
                if not outcomes or len(prices) < 2:
                    continue
                    
                yes_price = float(prices[0]) if prices else 0
                no_price = float(prices[1]) if len(prices) > 1 else 0
                
                liquidity = market.get("liquidityNum") or market.get("liquidity") or 0
                volume = market.get("volumeNum") or market.get("volume") or 0
                
                processed.append({
                    "id": market.get("id", ""),
                    "title": market.get("question", market.get("title", "")),
                    "category": market.get("category", ""),
                    "yes_price": yes_price,
                    "no_price": no_price,
                    "liquidity": float(liquidity) if liquidity else 0,
                    "volume": float(volume) if volume else 0,
                    "source": "polymarket"
                })
            except (ValueError, TypeError, IndexError, json.JSONDecodeError) as e:
                continue
        
        print(f"Polymarket: Processed {len(processed)} markets from {len(markets)} total")
        return processed
    except requests.RequestException as e:
        print(f"Error fetching Polymarket markets: {e}")
        return []


def fetch_kalshi_markets() -> List[Dict]:
    """Fetch active markets from Kalshi API using events endpoint for better matches."""
    try:
        url = f"{config.KALSHI_API_URL}/events"
        headers = {
            "Accept": "application/json",
        }
        
        kalshi_api_key = os.environ.get("KALSHI_API_KEY")
        if kalshi_api_key:
            headers["Authorization"] = f"Bearer {kalshi_api_key}"
        
        params = {
            "status": "open",
            "limit": 100,
            "with_nested_markets": "true",
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        events = data.get("events", [])
        
        processed = []
        for event in events:
            event_title = event.get("title", "")
            event_category = event.get("category", "")
            markets = event.get("markets", [])
            
            for market in markets:
                try:
                    yes_ask_str = market.get("yes_ask_dollars", "0")
                    no_ask_str = market.get("no_ask_dollars", "0")
                    yes_bid_str = market.get("yes_bid_dollars", "0")
                    no_bid_str = market.get("no_bid_dollars", "0")
                    
                    yes_price = float(yes_ask_str) if yes_ask_str else 0
                    no_price = float(no_ask_str) if no_ask_str else 0
                    
                    if yes_price == 0:
                        yes_price = float(yes_bid_str) if yes_bid_str else 0
                    if no_price == 0:
                        no_price = float(no_bid_str) if no_bid_str else 0
                    
                    if yes_price == 0 and no_price == 0:
                        continue
                    
                    liquidity_str = market.get("liquidity_dollars", "0")
                    liquidity = float(liquidity_str) if liquidity_str else 0
                    
                    market_title = market.get("title") or market.get("subtitle") or event_title
                    
                    processed.append({
                        "id": market.get("ticker", ""),
                        "title": market_title,
                        "event_title": event_title,
                        "category": event_category,
                        "yes_price": yes_price,
                        "no_price": no_price,
                        "liquidity": liquidity,
                        "volume": float(market.get("volume", 0)) if market.get("volume") else 0,
                        "source": "kalshi"
                    })
                except (ValueError, TypeError):
                    continue
        
        print(f"Kalshi: Processed {len(processed)} markets from {len(events)} events")
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
    Uses token_sort_ratio as primary matcher with word overlap requirements.
    Returns list of (poly_market, kalshi_market, match_score) tuples.
    """
    if threshold is None:
        threshold = config.FUZZY_MATCH_THRESHOLD
    
    stopwords = {'will', 'the', 'be', 'in', 'to', 'a', 'an', 'of', 'for', 'and', 'or', 'is', 'are', 'by', 'on', 'at', 'with', 'before', 'after'}
    
    matches = []
    
    for poly in poly_markets:
        poly_title = poly["title"].lower().strip()
        poly_words = set(poly_title.split()) - stopwords
        poly_significant = {w for w in poly_words if len(w) > 3}
        best_match = None
        best_score = 0
        
        for kalshi in kalshi_markets:
            kalshi_title = kalshi["title"].lower().strip()
            kalshi_event = kalshi.get("event_title", "").lower().strip()
            kalshi_words = (set(kalshi_title.split()) | set(kalshi_event.split())) - stopwords
            kalshi_significant = {w for w in kalshi_words if len(w) > 3}
            
            common_significant = poly_significant & kalshi_significant
            if len(common_significant) < 1:
                continue
            
            score1 = fuzz.token_sort_ratio(poly_title, kalshi_title)
            score2 = fuzz.token_sort_ratio(poly_title, kalshi_event)
            
            score = max(score1, score2)
            
            if len(common_significant) >= 2:
                score = min(score + 5, 100)
            
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


if __name__ == "__main__":
    print("Starting arbitrage scan...")
    df = scan_for_arbitrage()
    
    if df.empty:
        print("\nNo arbitrage opportunities found meeting the threshold criteria.")
    else:
        print(f"\nFound {len(df)} opportunities:")
        print(df.to_string())
