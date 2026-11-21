#!/usr/bin/env python3
"""
===============================================================================
Lead Hunter 24/7 Autonomous Cloud & Local AutoPilot Runner
===============================================================================
This entry point executes autonomous outreach and reply handling:
- Auto-rotates 60+ worldwide cities and business niches
- Scrapes real Google Maps businesses (no duplicates)
- Performs dual-viewport website audits & captures screenshots
- Dispatches hyper-personalized cold outreach directly to client emails (or WhatsApp)
- Polls Gmail IMAP for client replies, answers questions, handles objections
- Closes deals autonomously and alerts agency owner immediately via email & dashboard!

Can be run locally:
    python run_autopilot.py --batch 10
    python run_autopilot.py --daemon

Can be run on GitHub Actions Cloud:
    python run_autopilot.py --cloud --batch 12
    python run_autopilot.py --poll-only
===============================================================================
"""

import argparse
import asyncio
import os
import signal
import sys
from datetime import datetime

from config import settings
from database import db
from workers.autopilot import autopilot
from workers.orchestrator import orchestrator


def parse_args():
    parser = argparse.ArgumentParser(
        description="Lead Hunter Autonomous 24/7 Outreach & AI Sales Engine"
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=10,
        help="Number of leads to hunt and contact in this run (default: 10)",
    )
    parser.add_argument(
        "--cloud",
        action="store_true",
        help="Flag indicating run is inside GitHub Actions or cloud runner",
    )
    parser.add_argument(
        "--poll-only",
        action="store_true",
        help="Only poll for incoming client replies and run AI closer (no new hunting)",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run continuously in a loop (e.g. for background server daemon)",
    )
    parser.add_argument(
        "--interval-minutes",
        type=int,
        default=120,
        help="Interval between cycles in daemon mode (default: 120 mins)",
    )
    return parser.parse_args()


async def run_single_poll():
    """Poll Gmail IMAP and WhatsApp for unread client replies and run AI sales agent."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Polling incoming client replies...")
    replies_count = await orchestrator.poll_all_replies_once()
    print(
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ Completed reply poll: {replies_count} client replies processed."
    )
    return replies_count


async def run_autopilot_cycle(batch_limit: int, is_cloud: bool):
    """Execute a single full autonomous cycle."""
    print(
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🚀 Launching AutoPilot Outreach Cycle (Target batch: {batch_limit}, Cloud: {is_cloud})..."
    )
    result = await autopilot.run_cycle(batch_limit=batch_limit, is_cloud=is_cloud)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Cycle result: {result}")
    return result


async def main_async():
    args = parse_args()

    # Log environment setup
    print("=" * 70)
    print("🤖 LEAD HUNTER AUTONOMOUS 24/7 SYSTEM INITIALIZED")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Mode: {'CLOUD (GitHub Actions)' if args.cloud else 'LOCAL'}")
    print(f"Gmail Configured: {settings.is_gmail_configured()} ({settings.GMAIL_ADDRESS})")
    print(f"Agency Name: {settings.AGENCY_NAME}")
    print(f"Owner Alert Email: {settings.MY_PERSONAL_EMAIL}")
    print(f"Owner WhatsApp: {settings.AGENCY_OWNER_WHATSAPP}")
    print("=" * 70)

    if args.poll_only:
        # Just check for replies and close deals
        await run_single_poll()
        return

    if args.daemon:
        # Continuous daemon mode
        print(f"🔁 Running in continuous daemon mode (every {args.interval_minutes} minutes)...")
        await autopilot.run_daemon(interval_minutes=args.interval_minutes)
        return

    # Single cycle run (standard for GitHub Actions cron or manual trigger)
    await run_autopilot_cycle(batch_limit=args.batch, is_cloud=args.cloud)


def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n🛑 AutoPilot stopped by user (Ctrl+C).")
        sys.exit(0)
    except Exception as exc:
        print(f"\n❌ AutoPilot encountered an error: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
