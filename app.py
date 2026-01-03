"""
Project Alpha - Complete-Set Arbitrage Bot Dashboard
Streamlit interface for monitoring the arbitrage bot.
"""
import streamlit as st
import pandas as pd
from datetime import datetime
import subprocess
import os

from src.config import load_config
from src.storage.ledger import Ledger

st.set_page_config(
    page_title="Project Alpha - Arbitrage Bot",
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
    .positive-pnl {
        color: #00ff00;
    }
    .negative-pnl {
        color: #ff0000;
    }
</style>
""", unsafe_allow_html=True)

st.title("Project Alpha - Complete-Set Arbitrage Bot")
st.caption("WebSocket-based prediction market arbitrage for Polymarket")

config_path = st.sidebar.selectbox(
    "Config File",
    ["config.yaml", "config_mock.yaml"],
    index=0
)

try:
    config = load_config(config_path)
except Exception as e:
    st.error(f"Failed to load config: {e}")
    st.stop()

st.sidebar.markdown("---")
st.sidebar.subheader("Bot Configuration")
st.sidebar.write(f"**Venue:** {config.venue.name}")
st.sidebar.write(f"**Paper Mode:** {config.paper_mode}")
st.sidebar.write(f"**Min Edge:** {config.strategy.min_edge}")
st.sidebar.write(f"**Order Size:** ${config.execution.order_size}")
st.sidebar.write(f"**Max Daily Notional:** ${config.risk.max_daily_notional}")

try:
    ledger = Ledger(config.data.sqlite_path)
    ledger.connect()
except Exception as e:
    st.warning(f"No ledger database found. Run the bot first to create data.")
    ledger = None

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Dashboard", 
    "Opportunities", 
    "Tradesets", 
    "Risk Events",
    "CLI"
])

with tab1:
    st.header("Performance Dashboard")
    
    if ledger:
        opp_summary = ledger.get_opportunities_summary()
        ts_summary = ledger.get_tradesets_summary()
        risk_events = ledger.get_risk_events_count(hours=24)
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "Opportunities Detected",
                opp_summary['total_opportunities'],
                help="Total opportunities detected by the scanner"
            )
        
        with col2:
            st.metric(
                "Trades Executed",
                opp_summary['traded'],
                help="Number of complete-set trades executed"
            )
        
        with col3:
            total_pnl = ts_summary['total_pnl']
            st.metric(
                "Total PnL",
                f"${total_pnl:.4f}",
                delta=f"${total_pnl:.4f}" if total_pnl != 0 else None,
                delta_color="normal" if total_pnl >= 0 else "inverse"
            )
        
        with col4:
            st.metric(
                "Total Fees",
                f"${ts_summary['total_fees']:.4f}",
                help="Total fees paid"
            )
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Opportunity Breakdown")
            if opp_summary['by_decision']:
                decision_df = pd.DataFrame([
                    {"Decision": k, "Count": v}
                    for k, v in opp_summary['by_decision'].items()
                ])
                st.bar_chart(decision_df.set_index("Decision"))
            else:
                st.info("No opportunities detected yet")
        
        with col2:
            st.subheader("Tradeset Status")
            if ts_summary['by_status']:
                status_df = pd.DataFrame([
                    {"Status": k, "Count": v}
                    for k, v in ts_summary['by_status'].items()
                ])
                st.bar_chart(status_df.set_index("Status"))
            else:
                st.info("No tradesets yet")
        
        st.markdown("---")
        st.subheader("Risk Events (Last 24h)")
        
        risk_cols = st.columns(4)
        with risk_cols[0]:
            st.metric("Partial Fills", risk_events.get('partial_fill', 0))
        with risk_cols[1]:
            st.metric("Rejects", risk_events.get('reject', 0))
        with risk_cols[2]:
            st.metric("WS Disconnects", risk_events.get('ws_disconnect', 0))
        with risk_cols[3]:
            st.metric("Kill Switch", risk_events.get('kill_switch', 0))
    else:
        st.info("No data available. Run the bot to generate data.")

with tab2:
    st.header("Opportunities Log")
    
    if ledger:
        cursor = ledger._conn.cursor()
        cursor.execute("""
            SELECT market_id, timestamp, decision, yes_ask, no_ask, 
                   sum_cost, edge, reason
            FROM opportunities 
            ORDER BY timestamp DESC 
            LIMIT 100
        """)
        rows = cursor.fetchall()
        
        if rows:
            df = pd.DataFrame(rows, columns=[
                "Market ID", "Timestamp", "Decision", "YES Ask", "NO Ask",
                "Sum Cost", "Edge", "Reason"
            ])
            df["Timestamp"] = pd.to_datetime(df["Timestamp"], unit='s')
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No opportunities logged yet")
    else:
        st.info("No data available")

with tab3:
    st.header("Tradesets")
    
    if ledger:
        cursor = ledger._conn.cursor()
        cursor.execute("""
            SELECT id, market_id, status, yes_cost, no_cost, 
                   total_cost, total_fees, realized_pnl, created_at
            FROM tradesets 
            ORDER BY created_at DESC 
            LIMIT 100
        """)
        rows = cursor.fetchall()
        
        if rows:
            df = pd.DataFrame(rows, columns=[
                "ID", "Market ID", "Status", "YES Cost", "NO Cost",
                "Total Cost", "Fees", "Realized PnL", "Created At"
            ])
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No tradesets yet")
    else:
        st.info("No data available")

with tab4:
    st.header("Risk Events")
    
    if ledger:
        cursor = ledger._conn.cursor()
        cursor.execute("""
            SELECT event_type, market_id, details, created_at
            FROM risk_events 
            ORDER BY created_at DESC 
            LIMIT 100
        """)
        rows = cursor.fetchall()
        
        if rows:
            df = pd.DataFrame(rows, columns=[
                "Event Type", "Market ID", "Details", "Created At"
            ])
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No risk events logged")
    else:
        st.info("No data available")

with tab5:
    st.header("CLI Commands")
    
    st.markdown("""
    Use the CLI to control the bot. Available commands:
    
    ```bash
    # Run the bot in paper mode
    python -m src.cli.commands run --paper -c config.yaml
    
    # Run with mock adapter (for testing)
    python -m src.cli.commands run --paper -c config_mock.yaml
    
    # Check bot status
    python -m src.cli.commands status
    
    # Generate performance report
    python -m src.cli.commands report --days 7
    ```
    """)
    
    st.subheader("Quick Commands")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Show Status"):
            result = subprocess.run(
                ["python", "-m", "src.cli.commands", "status", "-c", config_path],
                capture_output=True,
                text=True,
                cwd="/home/runner/workspace"
            )
            st.code(result.stdout or result.stderr)
    
    with col2:
        if st.button("Generate Report"):
            result = subprocess.run(
                ["python", "-m", "src.cli.commands", "report", "-c", config_path],
                capture_output=True,
                text=True,
                cwd="/home/runner/workspace"
            )
            st.code(result.stdout or result.stderr)

if ledger:
    ledger.close()

st.sidebar.markdown("---")
st.sidebar.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if st.sidebar.button("Refresh Data"):
    st.rerun()
