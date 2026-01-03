"""
Project Alpha - Streamlit Dashboard
Personal Prediction Market Engine UI
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import config
import database
import arb_scanner
import telegram_bot

st.set_page_config(
    page_title="Project Alpha - Prediction Market Engine",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stMetric {
        background-color: #1e1e2e;
        padding: 15px;
        border-radius: 10px;
    }
    .positive-roi {
        background-color: #1a472a;
        padding: 10px;
        border-radius: 5px;
    }
    .whale-alert {
        background-color: #2d1b4e;
        padding: 15px;
        border-radius: 8px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

if 'opportunities' not in st.session_state:
    st.session_state.opportunities = pd.DataFrame()
if 'whale_trades' not in st.session_state:
    st.session_state.whale_trades = []
if 'last_scan' not in st.session_state:
    st.session_state.last_scan = None
if 'auto_refresh' not in st.session_state:
    st.session_state.auto_refresh = False

st.title("📈 Project Alpha")
st.caption("Personal Prediction Market Engine - Cross-Venue Arbitrage & Whale Copy-Trading")

with st.sidebar:
    st.header("⚙️ Settings")
    
    st.subheader("Arbitrage Settings")
    arb_threshold = st.slider(
        "Min ROI Threshold (%)",
        min_value=0.5,
        max_value=10.0,
        value=float(config.ARB_THRESHOLD * 100),
        step=0.5
    )
    min_liquidity = st.number_input(
        "Min Liquidity ($)",
        min_value=50,
        max_value=10000,
        value=config.MIN_LIQUIDITY
    )
    
    st.subheader("Whale Watcher")
    with st.expander("Monitored Addresses"):
        whale_addresses = database.get_whale_addresses()
        if whale_addresses:
            for addr in whale_addresses:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.code(f"{addr['address'][:10]}...{addr['address'][-6:]}")
                with col2:
                    if st.button("❌", key=f"remove_{addr['id']}"):
                        database.remove_whale_address(addr['address'])
                        st.rerun()
        else:
            st.info("No addresses being monitored")
        
        new_address = st.text_input("Add Whale Address", placeholder="0x...")
        if st.button("Add Address") and new_address:
            if new_address.startswith("0x") and len(new_address) == 42:
                database.add_whale_address(new_address)
                st.success("Address added!")
                st.rerun()
            else:
                st.error("Invalid address format")
    
    st.subheader("Telegram Alerts")
    telegram_status = "✅ Configured" if telegram_bot.is_configured() else "❌ Not Configured"
    st.write(f"Status: {telegram_status}")
    
    if telegram_bot.is_configured():
        if st.button("Send Test Alert"):
            if telegram_bot.send_test_message():
                st.success("Test message sent!")
            else:
                st.error("Failed to send message")

tab1, tab2, tab3, tab4 = st.tabs(["📊 Arbitrage Scanner", "🐋 Whale Tracker", "📜 Trade History", "📖 About"])

with tab1:
    st.header("Arbitrage Opportunities")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("🔄 Scan Markets", type="primary", use_container_width=True):
            with st.spinner("Scanning Polymarket and Kalshi..."):
                try:
                    df = arb_scanner.scan_for_arbitrage()
                    st.session_state.opportunities = df
                    st.session_state.last_scan = datetime.now()
                    if df.empty:
                        st.warning("No arbitrage opportunities found above the threshold.")
                    else:
                        st.success(f"Found {len(df)} opportunities!")
                except Exception as e:
                    st.error(f"Scan failed: {e}")
    
    with col2:
        st.session_state.auto_refresh = st.checkbox("Auto-Refresh (5s)")
    
    with col3:
        if st.session_state.last_scan:
            st.caption(f"Last scan: {st.session_state.last_scan.strftime('%H:%M:%S')}")
    
    st.divider()
    
    if not st.session_state.opportunities.empty:
        df = st.session_state.opportunities
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Opportunities", len(df))
        with col2:
            avg_roi = df['roi_percent'].mean() if 'roi_percent' in df.columns else 0
            st.metric("Avg ROI", f"{avg_roi:.2f}%")
        with col3:
            max_roi = df['roi_percent'].max() if 'roi_percent' in df.columns else 0
            st.metric("Best ROI", f"{max_roi:.2f}%")
        with col4:
            total_liquidity = df['min_liquidity'].sum() if 'min_liquidity' in df.columns else 0
            st.metric("Total Liquidity", f"${total_liquidity:,.0f}")
        
        st.divider()
        
        def highlight_roi(row):
            if row['roi_percent'] >= 1.0:
                return ['background-color: #1a472a'] * len(row)
            elif row['roi_percent'] >= 0.5:
                return ['background-color: #3d3d00'] * len(row)
            return [''] * len(row)
        
        display_df = df[[
            'market_title', 'strategy', 'poly_price', 'kalshi_price',
            'total_cost', 'spread', 'roi_percent', 'min_liquidity', 'match_score'
        ]].copy()
        
        display_df.columns = [
            'Market', 'Strategy', 'Poly Price', 'Kalshi Price',
            'Total Cost', 'Spread', 'ROI %', 'Liquidity', 'Match %'
        ]
        
        display_df['Poly Price'] = display_df['Poly Price'].apply(lambda x: f"{int(x*100)}¢")
        display_df['Kalshi Price'] = display_df['Kalshi Price'].apply(lambda x: f"{int(x*100)}¢")
        display_df['Total Cost'] = display_df['Total Cost'].apply(lambda x: f"${x:.2f}")
        display_df['Spread'] = display_df['Spread'].apply(lambda x: f"${x:.4f}")
        display_df['ROI %'] = display_df['ROI %'].apply(lambda x: f"{x:.2f}%")
        display_df['Liquidity'] = display_df['Liquidity'].apply(lambda x: f"${x:,.0f}")
        display_df['Match %'] = display_df['Match %'].apply(lambda x: f"{x}%")
        
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
        )
        
        st.subheader("Quick Actions")
        col1, col2 = st.columns(2)
        
        with col1:
            selected_idx = st.selectbox(
                "Select Opportunity",
                range(len(df)),
                format_func=lambda x: f"{df.iloc[x]['market_title'][:50]}... ({df.iloc[x]['roi_percent']:.2f}%)"
            )
        
        with col2:
            if st.button("📱 Send to Telegram", disabled=not telegram_bot.is_configured()):
                opp = df.iloc[selected_idx].to_dict()
                if telegram_bot.send_arb_alert(opp):
                    st.success("Alert sent to Telegram!")
                else:
                    st.error("Failed to send alert")
    else:
        st.info("Click 'Scan Markets' to fetch live arbitrage opportunities from Polymarket and Kalshi")

with tab2:
    st.header("Whale Trade Monitor")
    
    if st.button("🔄 Load Recent Whale Trades", type="primary"):
        db_trades = database.get_recent_whale_trades(50)
        st.session_state.whale_trades = db_trades
        if db_trades:
            st.success(f"Loaded {len(db_trades)} recent whale trades")
        else:
            st.warning("No whale trades recorded yet. Add whale addresses and run the whale watcher to capture trades.")
    
    st.divider()
    
    if st.session_state.whale_trades:
        for trade in st.session_state.whale_trades:
            with st.container():
                st.markdown(f"""
                <div class="whale-alert">
                    <h4>🐋 {trade.get('market_title', 'Unknown Market')}</h4>
                    <p><b>Whale:</b> {trade.get('whale_address', 'Unknown')[:10]}...</p>
                    <p><b>Action:</b> {trade.get('side', 'Unknown').upper()} {trade.get('outcome', '')}</p>
                    <p><b>Amount:</b> ${trade.get('amount_usdc', 0):,.2f} USDC @ {trade.get('price', 0):.2f}</p>
                    <p><small>{trade.get('timestamp', '')}</small></p>
                </div>
                """, unsafe_allow_html=True)
                
                if telegram_bot.is_configured():
                    if st.button(f"📱 Alert", key=f"whale_alert_{trade.get('timestamp')}"):
                        telegram_bot.send_whale_alert(trade)
                        st.success("Alert sent!")
    else:
        st.info("No whale trades detected. Click 'Load Recent Whale Trades' or 'Load Demo Whales' to view activity.")
    
    st.divider()
    st.subheader("Real-Time Monitoring")
    st.info("""
    **WebSocket Monitoring**: The whale watcher runs as a background service.
    
    To start real-time monitoring:
    ```bash
    python whale_watch.py
    ```
    
    Detected trades will be saved to the database and appear here on refresh.
    """)

with tab3:
    st.header("Trade History")
    
    trades = database.get_trade_history()
    
    if trades:
        trade_df = pd.DataFrame(trades)
        st.dataframe(trade_df, use_container_width=True, hide_index=True)
        
        total_pnl = sum(t.get('pnl', 0) or 0 for t in trades)
        st.metric("Total P&L", f"${total_pnl:,.2f}")
    else:
        st.info("No trade history yet. Execute trades to build your history.")
    
    st.divider()
    
    with st.expander("Log Manual Trade"):
        col1, col2 = st.columns(2)
        with col1:
            trade_type = st.selectbox("Trade Type", ["arbitrage", "copy_trade", "manual"])
            venue = st.selectbox("Venue", ["polymarket", "kalshi", "both"])
            market_title = st.text_input("Market Title")
        with col2:
            side = st.selectbox("Side", ["buy", "sell"])
            amount = st.number_input("Amount ($)", min_value=0.0)
            price = st.number_input("Price", min_value=0.0, max_value=1.0, step=0.01)
        
        pnl = st.number_input("P&L ($)", step=0.01)
        notes = st.text_area("Notes")
        
        if st.button("Log Trade"):
            database.log_trade(
                trade_type, venue, "", market_title,
                side, amount, price, pnl, notes
            )
            st.success("Trade logged!")
            st.rerun()

with tab4:
    st.header("About Project Alpha")
    
    st.markdown("""
    ## Personal Prediction Market Engine
    
    Project Alpha is a lightweight trading engine that automates the detection and execution
    of high-probability trades on prediction markets.
    
    ### Core Strategies
    
    **1. Cross-Venue Arbitrage**
    - Exploits price discrepancies between Kalshi (regulated) and Polymarket (crypto)
    - Identifies when YES + NO prices across venues are less than $1.00
    - Guarantees risk-free profit when executed simultaneously
    
    **2. Whale Copy-Trading**
    - Monitors high-conviction trades from specific wallet addresses
    - Detects large trades before the broader market reacts
    - Provides real-time alerts for quick decision-making
    
    ### System Components
    
    | Module | Description |
    |--------|-------------|
    | **Arbitrage Scanner** | Polls market APIs, fuzzy-matches events, calculates spreads |
    | **Whale Watchdog** | WebSocket monitor for large Polymarket trades |
    | **Telegram Bot** | Push notifications for opportunities |
    | **Dashboard** | This Streamlit UI for visualization |
    
    ### Configuration
    
    Set the following environment variables for full functionality:
    
    - `TELEGRAM_BOT_TOKEN` - Your Telegram bot token
    - `TELEGRAM_CHAT_ID` - Your Telegram chat/channel ID
    - `KALSHI_API_KEY` - (Optional) Kalshi API key for authenticated requests
    
    ### Technology Stack
    
    - **Language**: Python 3.11+
    - **Frontend**: Streamlit
    - **Database**: SQLite
    - **APIs**: Polymarket Gamma API, Kalshi v2 API
    - **Real-time**: WebSockets for whale monitoring
    """)
    
    st.divider()
    
    st.subheader("System Status")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Database", "✅ Connected")
        st.caption(f"Path: {config.DATABASE_PATH}")
    
    with col2:
        telegram_status = "✅ Ready" if telegram_bot.is_configured() else "⚠️ Not Configured"
        st.metric("Telegram", telegram_status)
    
    with col3:
        whale_count = len(database.get_whale_addresses())
        st.metric("Monitored Whales", whale_count)

if st.session_state.auto_refresh:
    import time
    time.sleep(config.REFRESH_INTERVAL)
    try:
        df = arb_scanner.scan_for_arbitrage()
        st.session_state.opportunities = df
        st.session_state.last_scan = datetime.now()
    except Exception as e:
        print(f"Auto-scan error: {e}")
    st.rerun()
