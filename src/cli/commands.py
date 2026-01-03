"""
CLI commands for controlling the arbitrage bot.
"""
import asyncio
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout

from src.config import load_config
from src.storage.ledger import Ledger
from src.reporting.report import generate_report


console = Console()


def setup_logging(level: str, json_format: bool = False) -> None:
    """Configure logging based on config."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    if json_format:
        import json
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                return json.dumps({
                    "timestamp": datetime.utcnow().isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                })
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logging.root.handlers = [handler]
    else:
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    
    logging.root.setLevel(log_level)


def cmd_run(args: argparse.Namespace) -> None:
    """Run the arbitrage bot."""
    from src.main import run_bot
    
    config_path = args.config or "config.yaml"
    config = load_config(config_path)
    
    if args.paper:
        config.paper_mode = True
    elif args.live:
        config.paper_mode = False
    
    setup_logging(config.data.log_level, config.data.log_json)
    
    mode = "PAPER" if config.paper_mode else "LIVE"
    console.print(Panel(
        f"[bold green]Starting Arbitrage Bot[/bold green]\n"
        f"Mode: [bold yellow]{mode}[/bold yellow]\n"
        f"Venue: {config.venue.name}\n"
        f"Markets: {len(config.markets)} configured",
        title="Project Alpha",
    ))
    
    try:
        asyncio.run(run_bot(config))
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")


def cmd_status(args: argparse.Namespace) -> None:
    """Show current bot status."""
    config_path = args.config or "config.yaml"
    config = load_config(config_path)
    
    ledger = Ledger(config.data.sqlite_path)
    ledger.connect()
    
    try:
        opp_summary = ledger.get_opportunities_summary()
        ts_summary = ledger.get_tradesets_summary()
        risk_events = ledger.get_risk_events_count(hours=1)
        
        table = Table(title="Bot Status")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Total Opportunities Detected", str(opp_summary['total_opportunities']))
        table.add_row("Signals Traded", str(opp_summary['traded']))
        table.add_row("Signals Skipped", str(opp_summary['skipped']))
        table.add_row("Average Edge", f"{opp_summary['avg_edge']:.4f}" if opp_summary['avg_edge'] else "N/A")
        table.add_row("", "")
        table.add_row("Total Tradesets", str(ts_summary['total_tradesets']))
        table.add_row("Total PnL", f"${ts_summary['total_pnl']:.4f}")
        table.add_row("Total Fees", f"${ts_summary['total_fees']:.4f}")
        table.add_row("", "")
        table.add_row("Partial Fills (1h)", str(risk_events.get('partial_fill', 0)))
        table.add_row("Rejects (1h)", str(risk_events.get('reject', 0)))
        table.add_row("WS Disconnects (1h)", str(risk_events.get('ws_disconnect', 0)))
        
        console.print(table)
        
    finally:
        ledger.close()


def cmd_report(args: argparse.Namespace) -> None:
    """Generate a performance report."""
    config_path = args.config or "config.yaml"
    config = load_config(config_path)
    
    ledger = Ledger(config.data.sqlite_path)
    ledger.connect()
    
    try:
        report = generate_report(ledger, days=args.days)
        console.print(report)
    finally:
        ledger.close()


def cmd_halt(args: argparse.Namespace) -> None:
    """Halt trading (soft stop)."""
    console.print("[red]Halt command - would stop trading in a running bot[/red]")
    console.print("Note: This requires the bot to be running. Use Ctrl+C to stop the bot process.")


def cmd_resume(args: argparse.Namespace) -> None:
    """Resume trading after halt."""
    console.print("[green]Resume command - would resume trading in a running bot[/green]")
    console.print("Note: This requires the bot to be running with a halt state.")


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="arb-bot",
        description="Complete-Set Arbitrage Bot for Prediction Markets",
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to config file (default: config.yaml)",
        default="config.yaml",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    run_parser = subparsers.add_parser("run", help="Start the bot")
    run_parser.add_argument("--paper", action="store_true", help="Run in paper mode (no real orders)")
    run_parser.add_argument("--live", action="store_true", help="Run in live mode (real orders)")
    run_parser.set_defaults(func=cmd_run)
    
    status_parser = subparsers.add_parser("status", help="Show current status")
    status_parser.set_defaults(func=cmd_status)
    
    report_parser = subparsers.add_parser("report", help="Generate performance report")
    report_parser.add_argument("--days", type=int, default=7, help="Number of days to include")
    report_parser.set_defaults(func=cmd_report)
    
    halt_parser = subparsers.add_parser("halt", help="Halt trading")
    halt_parser.set_defaults(func=cmd_halt)
    
    resume_parser = subparsers.add_parser("resume", help="Resume trading")
    resume_parser.set_defaults(func=cmd_resume)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()
