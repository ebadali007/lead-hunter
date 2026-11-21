import asyncio
from datetime import datetime
import random
from typing import Any, Dict, List, Optional

from config import settings
from database import db
from workers.ai_engine import ai_engine
from workers.email_worker import email_worker
from workers.maps_scraper import maps_scraper
from workers.orchestrator import orchestrator
from workers.website_auditor import website_auditor
from workers.whatsapp_worker import whatsapp_worker

# -----------------------------------------------------------------------------
# 60+ CURATED HIGH-TICKET ROTATING WORLDWIDE TARGETS
# The AutoPilot continuously cycles through these cities and commercial niches!
# -----------------------------------------------------------------------------
AUTOPILOT_ROTATING_TARGETS = [
    ("Toronto, ON, Canada", "Restaurants & Cafes"),
    ("New York, NY, USA", "Dentists & Dental Clinics"),
    ("London, UK", "Hair & Beauty Salons"),
    ("Dubai, UAE", "Real Estate Agencies"),
    ("Miami, FL, USA", "Medical Spas & Aesthetic Clinics"),
    ("Vancouver, BC, Canada", "HVAC & Plumbing Contractors"),
    ("Sydney, NSW, Australia", "Law Firms & Attorneys"),
    ("Chicago, IL, USA", "Bakeries & Cafes"),
    ("Manchester, UK", "Restaurants & Bistros"),
    ("Los Angeles, CA, USA", "Gyms & Fitness Centers"),
    ("Melbourne, VIC, Australia", "Cosmetic Clinics & Dentists"),
    ("Dallas, TX, USA", "Roofing & Construction Contractors"),
    ("Montreal, QC, Canada", "Boutique Hotels & Restaurants"),
    ("Birmingham, UK", "Auto Repair & Dealerships"),
    ("Houston, TX, USA", "Accounting & Financial Services"),
    ("Dubai, UAE", "Luxury Restaurants & Lounges"),
    ("Seattle, WA, USA", "Coffee Shops & Roasters"),
    ("Brisbane, QLD, Australia", "Veterinary Clinics"),
    ("Edinburgh, Scotland, UK", "Pubs & Restaurants"),
    ("Calgary, AB, Canada", "Landscaping & Tree Services"),
    ("Austin, TX, USA", "Tech Startups & Software"),
    ("San Francisco, CA, USA", "High-End Cafes & Bakeries"),
    ("London, UK", "Private Medical Practices & Clinics"),
    ("Boston, MA, USA", "Dental Specialists & Orthodontists"),
    ("Toronto, ON, Canada", "Physiotherapy & Chiropractic Clinics"),
    ("Phoenix, AZ, USA", "Solar & Electrical Contractors"),
    ("Perth, WA, Australia", "Mining & Engineering Consultancies"),
    ("Ottawa, ON, Canada", "Fine Dining & Restaurants"),
    ("Atlanta, GA, USA", "Logistics & Freight Services"),
    ("Las Vegas, NV, USA", "Event Planners & Venues"),
    ("Liverpool, UK", "Fitness Studios & Personal Trainers"),
    ("Denver, CO, USA", "Veterinary Hospitals"),
    ("Abu Dhabi, UAE", "Interior Design & Architecture"),
    ("San Diego, CA, USA", "Yacht & Boat Services"),
    ("Leeds, UK", "Digital Agencies & Media Studios"),
    ("Tampa, FL, USA", "Home Remodeling & Contractors"),
    ("Glasgow, Scotland, UK", "Boutique Hotels & Inns"),
    ("Nashville, TN, USA", "Music & Entertainment Venues"),
    ("Edmonton, AB, Canada", "Auto Body & Collision Shops"),
    ("Portland, OR, USA", "Artisan Bakeries & Roasters"),
    ("Charlotte, NC, USA", "Commercial Cleaning & Janitorial"),
    ("Adelaide, SA, Australia", "Wineries & Fine Dining"),
    ("Bristol, UK", "Bicycle & Outdoor Sports Shops"),
    ("Orlando, FL, USA", "Vacation Rental Property Managers"),
    ("Philadelphia, PA, USA", "Italian Restaurants & Pizzerias"),
    ("Mississauga, ON, Canada", "Dentists & Family Clinics"),
    ("San Antonio, TX, USA", "Mexican Restaurants & Grills"),
    ("Washington, DC, USA", "Lobbying & Consulting Firms"),
    ("Salt Lake City, UT, USA", "Ski & Outdoor Gear Stores"),
    ("Belfast, Northern Ireland, UK", "Seafood & Grill Restaurants"),
    ("Gold Coast, QLD, Australia", "Surf & Beachwear Boutiques"),
    ("Quebec City, QC, Canada", "French Bistros & Bakeries"),
    ("Raleigh, NC, USA", "Dental Implants & Oral Surgery"),
    ("Cardiff, Wales, UK", "Traditional Pubs & Inns"),
    ("Victoria, BC, Canada", "Tea Rooms & Garden Cafes"),
    ("Miami, FL, USA", "Nightclubs & Cocktail Lounges"),
    ("London, UK", "Art Galleries & Custom Framing"),
    ("Toronto, ON, Canada", "Halal Fine Dining & Steakhouses"),
    ("Dubai, UAE", "Luxury Car Rental Agencies"),
    ("Sydney, NSW, Australia", "Dental Care & Cosmetic Dentists"),
]


class AutoPilotEngine:
    """
    100% Autonomous 24/7 Cloud & Local Machine:
    - Auto-rotates worldwide locations & business categories.
    - Scrapes Google Maps authentically (no dummy data).
    - Captures live desktop + mobile website screenshots.
    - Dispatches high-converting personalized cold pitches directly to clients (Email 1st choice, WA fallback).
    - Polls Gmail IMAP for replies, negotiates, answers objections & closes deals with AI Sales Agent.
    - If client confirms project (DEAL_WON), immediately dispatches urgent alert email to agency owner!
    """

    def __init__(self):
        self.is_running = False

    def get_next_target(self) -> Dict[str, Any]:
        """Fetch the next target location and category from the rotation sequence."""
        state = db.get_autopilot_state()
        rotation_idx = state.get("rotation_index", 0)
        target = AUTOPILOT_ROTATING_TARGETS[rotation_idx % len(AUTOPILOT_ROTATING_TARGETS)]
        return {
            "index": rotation_idx,
            "location": target[0],
            "category": target[1],
            "total_available": len(AUTOPILOT_ROTATING_TARGETS),
        }

    async def run_cycle(self, batch_limit: int = 10, is_cloud: bool = False) -> Dict[str, Any]:
        """
        Execute one full autonomous cycle:
        1. Check daily email quota (target: 50-60/day).
        2. Auto-rotate to next global location & category.
        3. Scrape fresh Google Maps listings (skipping DB duplicates).
        4. Audit websites, capture dual screenshots.
        5. Dispatch direct client emails (or WhatsApp fallback).
        6. Poll incoming replies, run AI Sales Agent, handle objections, close deals.
        7. If deal won, alert owner immediately.
        """
        stats = db.get_dashboard_stats()
        today = stats["date"]
        emails_today = stats.get("emails_today", 0)
        daily_limit = settings.DAILY_EMAIL_LIMIT  # 60

        db.log_activity(
            "INFO",
            "AUTOPILOT",
            f"⚡ AutoPilot Cycle started. Today's outreach progress: {emails_today}/{daily_limit} emails sent.",
        )

        # 1. First, always poll for incoming client replies and handle objections
        replies_handled = await orchestrator.poll_all_replies_once()
        if replies_handled > 0:
            db.log_activity(
                "SUCCESS",
                "AUTOPILOT",
                f"💬 AutoPilot handled {replies_handled} client reply(ies) autonomously with AI Sales Agent.",
            )

        # 2. Check if daily quota already achieved
        if emails_today >= daily_limit:
            msg = f"Daily outreach goal of {daily_limit} emails already achieved for today ({today})! Standing by to handle replies."
            db.log_activity("SUCCESS", "AUTOPILOT", msg)
            return {
                "ok": True,
                "status": "QUOTA_ACHIEVED",
                "emails_today": emails_today,
                "daily_limit": daily_limit,
                "replies_handled": replies_handled,
                "message": msg,
            }

        # 3. Calculate how many leads to hunt in this batch
        remaining_quota = daily_limit - emails_today
        needed_in_batch = min(batch_limit, remaining_quota)

        # 4. Pick next rotating target
        target_info = self.get_next_target()
        location = target_info["location"]
        category = target_info["category"]
        cur_idx = target_info["index"]

        db.log_activity(
            "INFO",
            "AUTOPILOT",
            f"🌍 Auto-Rotating to Target #{cur_idx + 1}: '{category}' in '{location}' (Batch Goal: {needed_in_batch} leads).",
        )

        # Advance rotation index for the next run
        db.update_autopilot_state(
            rotation_index=cur_idx + 1,
            current_city=location,
            current_category=category,
        )

        # 5. Scrape real Google Maps listings
        scraped_raw = await maps_scraper.scrape_google_maps(
            location=location,
            category=category,
            max_leads=needed_in_batch + 5,
        )

        # Deduplicate against SQLite database
        new_leads_to_insert = []
        for item in scraped_raw:
            bname = (item.get("business_name") or "").strip()
            phone = (item.get("phone") or "").strip()
            web = (item.get("website") or "").strip()
            if not bname or bname.lower() in ("search", "google", "maps"):
                continue
            if not db.is_duplicate_lead(bname, phone, web):
                new_leads_to_insert.append(item)

        inserted_lead_ids = []
        for lead_data in new_leads_to_insert[:needed_in_batch]:
            lid = db.insert_lead(lead_data)
            if lid > 0:
                inserted_lead_ids.append(lid)

        db.log_activity(
            "SUCCESS",
            "AUTOPILOT",
            f"Target '{category}' in '{location}': Saved {len(inserted_lead_ids)} new unique leads to database.",
        )

        # 6. Audit websites and dispatch personalized outreach
        dispatched_count = 0
        for idx, lead_id in enumerate(inserted_lead_ids):
            lead = db.get_lead_by_id(lead_id)
            if not lead:
                continue

            # Dual Viewport Website Audit & Screenshots
            audited_lead = await website_auditor.audit_lead_and_prepare_outreach(lead)

            lead_email = (audited_lead.get("email") or "").strip()
            lead_phone = (audited_lead.get("phone") or "").strip()

            # Outreach Priority: Email 1st Choice, WhatsApp Fallback
            if lead_email:
                res = await email_worker.send_email(
                    lead_id=lead_id,
                    to_email=lead_email,
                    subject=audited_lead.get("draft_email_subject", f"Quick idea for {lead['business_name']}"),
                    body=audited_lead.get("draft_email_body", ""),
                    is_reply=False,
                )
                if res.get("ok"):
                    dispatched_count += 1
                    db.log_activity(
                        "SUCCESS",
                        "AUTOPILOT",
                        f"✉️ [OUTREACH {dispatched_count}/{len(inserted_lead_ids)}] Email dispatched directly to '{lead['business_name']}' at {lead_email}",
                    )
            elif lead_phone:
                res = await whatsapp_worker.send_whatsapp_message(
                    lead_id=lead_id,
                    phone=lead_phone,
                    message=audited_lead.get("draft_whatsapp_msg", ""),
                    is_reply=False,
                )
                if res.get("ok"):
                    dispatched_count += 1
                    db.log_activity(
                        "INFO",
                        "AUTOPILOT",
                        f"📱 [OUTREACH {dispatched_count}/{len(inserted_lead_ids)}] Contacted '{lead['business_name']}' via WhatsApp/Phone at {lead_phone}",
                    )

            # Safe Anti-Spam Jitter between outreach sends
            if idx < len(inserted_lead_ids) - 1:
                if is_cloud:
                    delay = random.randint(15, 35)
                else:
                    delay = random.randint(
                        settings.MIN_OUTREACH_DELAY_SECONDS,
                        settings.MAX_OUTREACH_DELAY_SECONDS,
                    )
                await asyncio.sleep(delay)

        # 7. Final poll for any replies that arrived during outreach
        replies_handled_post = await orchestrator.poll_all_replies_once()

        # Update cycle state
        cur_state = db.get_autopilot_state()
        db.update_autopilot_state(
            cycles=cur_state.get("total_cycles_completed", 0) + 1,
            rotation_index=cur_idx + 1,
            current_city=location,
            current_category=category,
        )

        db.log_activity(
            "SUCCESS",
            "AUTOPILOT",
            f"🏁 AutoPilot Cycle completed for '{category}' in '{location}'. Dispatched {dispatched_count} outreach messages. Daily emails: {emails_today + dispatched_count}/{daily_limit}.",
        )

        return {
            "ok": True,
            "status": "CYCLE_COMPLETED",
            "target": {"location": location, "category": category, "index": cur_idx},
            "new_leads_saved": len(inserted_lead_ids),
            "outreach_dispatched": dispatched_count,
            "replies_handled": replies_handled + replies_handled_post,
            "daily_total_emails": emails_today + dispatched_count,
            "daily_quota": daily_limit,
        }

    async def run_daemon(self, interval_minutes: int = 120):
        """Continuous background daemon loop for 24/7 autonomous hunting."""
        self.is_running = True
        db.log_activity("SUCCESS", "AUTOPILOT", f"24/7 AutoPilot Daemon started (Interval: {interval_minutes}m).")
        while self.is_running:
            try:
                await self.run_cycle(batch_limit=12, is_cloud=False)
            except Exception as e:
                db.log_activity("WARN", "AUTOPILOT", f"AutoPilot cycle warning: {e}")

            # Sleep until next scheduled interval
            await asyncio.sleep(interval_minutes * 60)


autopilot = AutoPilotEngine()
