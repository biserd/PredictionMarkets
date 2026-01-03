"""
Reporting and analytics for trade performance.
"""
from typing import Dict, Any
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from src.storage.ledger import Ledger


def generate_report(ledger: Ledger, days: int = 7) -> Panel:
    """
    Generate a comprehensive performance report.
    
    Returns a Rich Panel for console display.
    """
    opp_summary = ledger.get_opportunities_summary()
    ts_summary = ledger.get_tradesets_summary()
    risk_events = ledger.get_risk_events_count(hours=24 * days)
    
    tables = []
    
    opp_table = Table(title="Opportunities Summary", show_header=True)
    opp_table.add_column("Metric", style="cyan")
    opp_table.add_column("Value", style="green", justify="right")
    
    opp_table.add_row("Total Detected", str(opp_summary['total_opportunities']))
    opp_table.add_row("Traded", str(opp_summary['traded']))
    opp_table.add_row("Skipped", str(opp_summary['skipped']))
    
    if opp_summary['total_opportunities'] > 0:
        trade_rate = opp_summary['traded'] / opp_summary['total_opportunities'] * 100
        opp_table.add_row("Trade Rate", f"{trade_rate:.1f}%")
    
    if opp_summary['avg_edge']:
        opp_table.add_row("Avg Edge", f"{opp_summary['avg_edge']:.4f}")
    if opp_summary['avg_sum_cost']:
        opp_table.add_row("Avg Sum Cost", f"${opp_summary['avg_sum_cost']:.4f}")
    
    tables.append(opp_table)
    
    if opp_summary['by_decision']:
        decision_table = Table(title="Decisions Breakdown", show_header=True)
        decision_table.add_column("Decision", style="cyan")
        decision_table.add_column("Count", style="yellow", justify="right")
        
        for decision, count in sorted(opp_summary['by_decision'].items()):
            decision_table.add_row(decision, str(count))
        
        tables.append(decision_table)
    
    trade_table = Table(title="Trading Summary", show_header=True)
    trade_table.add_column("Metric", style="cyan")
    trade_table.add_column("Value", style="green", justify="right")
    
    trade_table.add_row("Total Tradesets", str(ts_summary['total_tradesets']))
    trade_table.add_row("Total PnL", f"${ts_summary['total_pnl']:.4f}")
    trade_table.add_row("Total Fees Paid", f"${ts_summary['total_fees']:.4f}")
    
    net_pnl = ts_summary['total_pnl'] - ts_summary['total_fees']
    pnl_style = "green" if net_pnl >= 0 else "red"
    trade_table.add_row("Net PnL", Text(f"${net_pnl:.4f}", style=pnl_style))
    
    if ts_summary['total_tradesets'] > 0:
        avg_pnl = ts_summary['total_pnl'] / ts_summary['total_tradesets']
        trade_table.add_row("Avg PnL per Set", f"${avg_pnl:.4f}")
    
    tables.append(trade_table)
    
    if ts_summary['by_status']:
        status_table = Table(title="Tradeset Status", show_header=True)
        status_table.add_column("Status", style="cyan")
        status_table.add_column("Count", style="yellow", justify="right")
        
        for status, count in sorted(ts_summary['by_status'].items()):
            status_table.add_row(status, str(count))
        
        tables.append(status_table)
    
    if risk_events:
        risk_table = Table(title=f"Risk Events (Last {days} days)", show_header=True)
        risk_table.add_column("Event Type", style="cyan")
        risk_table.add_column("Count", style="red", justify="right")
        
        for event_type, count in sorted(risk_events.items()):
            risk_table.add_row(event_type, str(count))
        
        tables.append(risk_table)
    
    console = Console()
    with console.capture() as capture:
        for table in tables:
            console.print(table)
            console.print("")
    
    content = capture.get()
    
    return Panel(
        content,
        title=f"[bold]Performance Report (Last {days} Days)[/bold]",
        border_style="blue",
    )


def get_summary_dict(ledger: Ledger) -> Dict[str, Any]:
    """
    Get a dictionary summary for programmatic use.
    """
    opp_summary = ledger.get_opportunities_summary()
    ts_summary = ledger.get_tradesets_summary()
    
    return {
        "opportunities": opp_summary,
        "tradesets": ts_summary,
        "net_pnl": ts_summary['total_pnl'] - ts_summary['total_fees'],
        "success_rate": (
            ts_summary['by_status'].get('filled', 0) / ts_summary['total_tradesets']
            if ts_summary['total_tradesets'] > 0 else 0
        ),
    }
