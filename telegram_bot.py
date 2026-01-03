"""
Project Alpha - Telegram Bot Module
Sends alerts for arbitrage opportunities and whale trades
"""

import os
import asyncio
from typing import Dict, Optional
from telegram import Bot
from telegram.error import TelegramError


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def is_configured() -> bool:
    """Check if Telegram is properly configured."""
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


async def send_message_async(message: str) -> bool:
    """Send a message to the configured Telegram chat (async)."""
    if not is_configured():
        print("Telegram not configured. Message not sent.")
        return False
    
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode="HTML"
        )
        return True
    except TelegramError as e:
        print(f"Telegram error: {e}")
        return False


def send_message(message: str) -> bool:
    """Send a message to the configured Telegram chat (sync wrapper)."""
    try:
        return asyncio.run(send_message_async(message))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(send_message_async(message))
        finally:
            loop.close()


def format_arb_alert(opportunity: Dict) -> str:
    """Format an arbitrage opportunity as a Telegram message."""
    poly_price_cents = int(opportunity.get("poly_price", 0) * 100)
    kalshi_price_cents = int(opportunity.get("kalshi_price", 0) * 100)
    roi = opportunity.get("roi_percent", 0)
    
    strategy = opportunity.get("strategy", "")
    if "YES (Poly)" in strategy:
        poly_side = "YES"
        kalshi_side = "NO"
    else:
        poly_side = "NO"
        kalshi_side = "YES"
    
    message = f"""
<b>ARB OPPORTUNITY</b>

<b>Market:</b> {opportunity.get('market_title', 'Unknown')}

<b>Strategy:</b>
• Buy {poly_side} (Polymarket) @ {poly_price_cents}¢
• Buy {kalshi_side} (Kalshi) @ {kalshi_price_cents}¢

<b>Profit:</b> {roi:.2f}%
<b>Spread:</b> ${opportunity.get('spread', 0):.4f}
<b>Match Score:</b> {opportunity.get('match_score', 0)}%
<b>Min Liquidity:</b> ${opportunity.get('min_liquidity', 0):,.0f}
"""
    return message.strip()


def format_whale_alert(trade: Dict) -> str:
    """Format a whale trade as a Telegram message."""
    address = trade.get("whale_address", "Unknown")
    short_address = f"{address[:6]}...{address[-4:]}" if len(address) > 10 else address
    
    message = f"""
<b>WHALE TRADE DETECTED</b>

<b>Whale:</b> {short_address}
<b>Market:</b> {trade.get('market_title', 'Unknown')}
<b>Action:</b> {trade.get('side', 'Unknown').upper()} {trade.get('outcome', 'Unknown')}
<b>Amount:</b> ${trade.get('amount_usdc', 0):,.2f} USDC
<b>Price:</b> {trade.get('price', 0):.2f}
"""
    return message.strip()


def send_arb_alert(opportunity: Dict) -> bool:
    """Send an arbitrage opportunity alert."""
    message = format_arb_alert(opportunity)
    return send_message(message)


async def send_arb_alert_async(opportunity: Dict) -> bool:
    """Send an arbitrage opportunity alert (async)."""
    message = format_arb_alert(opportunity)
    return await send_message_async(message)


def send_whale_alert(trade: Dict) -> bool:
    """Send a whale trade alert."""
    message = format_whale_alert(trade)
    return send_message(message)


async def send_whale_alert_async(trade: Dict) -> bool:
    """Send a whale trade alert (async)."""
    message = format_whale_alert(trade)
    return await send_message_async(message)


def send_test_message() -> bool:
    """Send a test message to verify configuration."""
    message = """
<b>Project Alpha - Test Message</b>

Telegram integration is working correctly!

You will receive alerts for:
• Arbitrage opportunities
• Whale trades
"""
    return send_message(message.strip())


if __name__ == "__main__":
    print("Testing Telegram integration...")
    
    if not is_configured():
        print("Telegram not configured.")
        print("Please set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables.")
    else:
        if send_test_message():
            print("Test message sent successfully!")
        else:
            print("Failed to send test message.")
