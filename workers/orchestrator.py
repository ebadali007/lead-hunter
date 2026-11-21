import asyncio
from datetime import datetime
import random
import subprocess
import sys
from typing import Any, Dict, List, Optional

from config import settings
from database import db
from workers.ai_engine import ai_engine
from workers.email_worker import email_worker
from workers.maps_scraper import maps_scraper
from workers.website_auditor import website_auditor
from workers.whatsapp_worker import whatsapp_worker


class AutomationOrchestrator:
    """
    Master Background Orchestrator for Lead Hunter AI Automation System:
    1. Morning One-Click Pipeline (Scrape -> Duplicate Check -> AI Audit -> Anti-Spam Outreach)
    2. 24/7 Autonomous AI Sales Agent (Every 5 mins IMAP + WhatsApp check, Self-Learning, Auto-Reply)
    3. Windows Desktop + Dashboard HOT LEAD ALERT System
    4. End-of-Day (EOD) Summary Report Generator & Dispatcher
    """

    def __init__(self):
        self.campaign_running: bool = False
        self.current_stage: str = "IDLE"
        self.current_location: str = ""
        self.current_category: str = ""
        self.target_limit: int = 0
        self.processed_count: int = 0
        self.next_outreach_countdown: int = 0
        self.hot_lead_alerts: List[Dict[str, Any]] = []
        self._campaign_task: Optional[asyncio.Task] = None
        self._daemon_task: Optional[asyncio.Task] = None
        self._last_eod_sent_date: str = ""

    def get_state(self) -> Dict[str, Any]:
        return {
            "campaign_running": self.campaign_running,
            "current_stage": self.current_stage,
            "current_location": self.current_location,
            "current_category": self.current_category,
            "target_limit": self.target_limit,
            "processed_count": self.processed_count,
            "next_outreach_countdown": self.next_outreach_countdown,
            "hot_lead_alerts": self.hot_lead_alerts[-10:],
            "whatsapp_status": whatsapp_worker.get_status_dict(),
            "ai_configured": settings.is_gemini_configured() or settings.is_groq_configured(),
            "gmail_configured": settings.is_gmail_configured(),
        }

    # -------------------------------------------------------------------------
    # WINDOWS DESKTOP NOTIFICATION + DASHBOARD HOT LEAD ALERT
    # -------------------------------------------------------------------------
    def trigger_hot_lead_alert(self, lead: Dict[str, Any], channel: str, client_message: str):
        alert_obj = {
            "id": int(datetime.now().timestamp() * 1000),
            "lead_id": lead["id"],
            "business_name": lead.get("business_name", "Client"),
            "channel": channel,
            "phone": lead.get("phone", ""),
            "email": lead.get("email", ""),
            "client_message": client_message[:180],
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }
        self.hot_lead_alerts.append(alert_obj)

        db.log_activity(
            "HOT_LEAD",
            "SALES_AGENT",
            f"🔥 HOT LEAD ALERT! '{lead.get('business_name')}' is ready for a call on {channel}! Booking link sent.",
        )

        # Trigger Native Windows Desktop Notification (Zero extra binary dependencies)
        if sys.platform.startswith("win"):
            title = f"HOT LEAD ALERT: {lead.get('business_name')}"
            msg = f"Client replied on {channel} and wants to connect! Calendar link sent."
            ps_script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$n = New-Object System.Windows.Forms.NotifyIcon; "
                "$n.Icon = [System.Drawing.SystemIcons]::Information; "
                "$n.Visible = $true; "
                f"$n.ShowBalloonTip(7000, '{title.replace(chr(39), '')}', '{msg.replace(chr(39), '')}', [System.Windows.Forms.ToolTipIcon]::Info); "
                "Start-Sleep -Seconds 2; $n.Dispose()"
            )
            try:
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

    def trigger_deal_won_alert(self, lead: Dict[str, Any], channel: str, client_message: str):
        alert_obj = {
            "id": int(datetime.now().timestamp() * 1000),
            "lead_id": lead["id"],
            "business_name": lead.get("business_name", "Client"),
            "channel": channel,
            "phone": lead.get("phone", ""),
            "email": lead.get("email", ""),
            "client_message": client_message[:240],
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "is_deal_won": True,
        }
        self.hot_lead_alerts.append(alert_obj)

        db.mark_deal_won(lead["id"], client_message)

        db.log_activity(
            "HOT_LEAD",
            "DEAL_CLOSER",
            f"🎉 DEAL CLOSED / CLIENT WON! '{lead.get('business_name')}' agreed to work on {channel}! Alerting owner now.",
        )

        owner_email = settings.MY_PERSONAL_EMAIL or settings.GMAIL_ADDRESS
        if owner_email and settings.is_gmail_configured():
            bname = lead.get("business_name", "Client")
            loc = lead.get("location", "")
            cat = lead.get("category", "")
            phone = lead.get("phone", "N/A")
            email_addr = lead.get("email", "N/A")
            web = lead.get("website", "N/A")

            subject = f"🎉 [DEAL WON] New Client Confirmed: {bname} ({loc}) • Start Work Now!"
            body = (
                f"====================================================================\n"
                f"🎉 REJOICE! A NEW CLIENT HAS CONFIRMED AND IS READY TO WORK WITH YOU!\n"
                f"====================================================================\n\n"
                f"Business Name: {bname}\n"
                f"Category: {cat}\n"
                f"Location: {loc}\n"
                f"Contact Channel: {channel}\n"
                f"Client Email: {email_addr}\n"
                f"Client Phone / WhatsApp: {phone}\n"
                f"Official Website: {web}\n"
                f"Google Maps Link: {lead.get('place_url', 'N/A')}\n\n"
                f"CLIENT CONFIRMATION MESSAGE:\n"
                f"\"{client_message}\"\n\n"
                f"--------------------------------------------------------------------\n"
                f"ACTION REQUIRED FOR YOU (AGENCY OWNER):\n"
                f"1. Contact the client directly via WhatsApp ({phone}) or Email ({email_addr}) to kick off project deliverables!\n"
                f"2. Check your Dashboard at http://localhost:8000 for their full audit and screenshots.\n"
                f"3. Start development / staging setup!\n\n"
                f"Autonomous AI Sales Agent has already sent the initial enthusiastic kickoff reply.\n"
                f"====================================================================\n"
            )
            try:
                asyncio.create_task(
                    email_worker.send_raw_notification_email(owner_email, subject, body)
                )
            except Exception as e:
                db.log_activity("WARN", "EMAIL", f"Deal alert email notice: {e}")

        if sys.platform.startswith("win"):
            title = f"🎉 DEAL WON: {lead.get('business_name')}"
            msg = f"Client agreed to work on {channel}! Check email and dashboard to start project work."
            ps_script = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$n = New-Object System.Windows.Forms.NotifyIcon; "
                "$n.Icon = [System.Drawing.SystemIcons]::Information; "
                "$n.Visible = $true; "
                f"$n.ShowBalloonTip(10000, '{title.replace(chr(39), '')}', '{msg.replace(chr(39), '')}', [System.Windows.Forms.ToolTipIcon]::Info); "
                "Start-Sleep -Seconds 2; $n.Dispose()"
            )
            try:
                subprocess.Popen(
                    ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # ONE-CLICK MORNING CAMPAIGN PIPELINE
    # -------------------------------------------------------------------------
    def start_campaign(
        self,
        location: str,
        category: str,
        daily_limit: int = 10,
        fast_demo_delay: bool = False,
        auto_send: bool = True,
    ) -> Dict[str, Any]:
        if self.campaign_running:
            return {"ok": False, "message": "A campaign is already running in the background."}

        self.campaign_running = True
        self.current_location = location.strip()
        self.current_category = category.strip()
        self.target_limit = max(1, min(int(daily_limit), 100))
        self.processed_count = 0
        self.current_stage = "SCRAPING_MAPS"

        self._campaign_task = asyncio.create_task(
            self._run_campaign_pipeline(
                location=self.current_location,
                category=self.current_category,
                daily_limit=self.target_limit,
                fast_demo_delay=fast_demo_delay,
                auto_send=auto_send,
            )
        )
        return {
            "ok": True,
            "message": f"Started autonomous campaign for '{category}' in '{location}' (Limit: {daily_limit})",
        }

    def stop_campaign(self) -> Dict[str, Any]:
        if self._campaign_task and not self._campaign_task.done():
            self._campaign_task.cancel()
        self.campaign_running = False
        self.current_stage = "IDLE"
        self.next_outreach_countdown = 0
        db.log_activity("WARN", "ORCHESTRATOR", "Campaign stopped by user from Dashboard.")
        return {"ok": True, "message": "Campaign stopped."}

    async def _run_campaign_pipeline(
        self,
        location: str,
        category: str,
        daily_limit: int,
        fast_demo_delay: bool = False,
        auto_send: bool = True,
    ):
        try:
            db.log_activity(
                "INFO",
                "ORCHESTRATOR",
                f"🚀 Morning Control Activated: Target='{category}' in '{location}' | Limit={daily_limit} leads",
            )

            # STEP 1: Scrape Google Maps + Website Emails (Streaming each lead live into SQLite!)
            self.current_stage = "SCRAPING_GOOGLE_MAPS"
            inserted_lead_ids: List[int] = []

            async def _on_lead_found(item: Dict[str, Any]):
                if not db.is_duplicate_lead(
                    business_name=item.get("business_name", ""),
                    phone=item.get("phone", ""),
                    website=item.get("website", ""),
                    place_url=item.get("place_url", ""),
                ):
                    lid = db.insert_lead(item)
                    inserted_lead_ids.append(lid)

            scraped_items = await maps_scraper.scrape_google_maps(
                location=location,
                category=category,
                max_leads=daily_limit,
                on_lead_callback=_on_lead_found,
            )

            # If Google Maps returned 0 (e.g. no listings or CAPTCHA encountered),
            # log warning cleanly. Never generate mock / dummy data.
            if not scraped_items and not inserted_lead_ids:
                db.log_activity(
                    "WARN",
                    "SCRAPER",
                    f"No new unique Google Maps listings found for '{category}' in '{location}'. (If Google showed a verification prompt, check terminal/browser; no mock data generated).",
                )

            db.log_activity(
                "SUCCESS",
                "SCRAPER",
                f"Saved {len(inserted_lead_ids)} new unique leads to SQLite (Duplicates skipped).",
            )

            # STEP 2 & 3: AI Website Audit + Anti-Spam Outreach for each lead
            for idx, lead_id in enumerate(inserted_lead_ids):
                if not self.campaign_running:
                    break

                lead = db.get_lead_by_id(lead_id)
                if not lead:
                    continue

                self.current_stage = f"AUDITING ({idx + 1}/{len(inserted_lead_ids)}): {lead['business_name']}"
                audited_lead = await website_auditor.audit_lead_and_prepare_outreach(lead)

                if auto_send:
                    self.current_stage = f"OUTREACH ({idx + 1}/{len(inserted_lead_ids)}): {lead['business_name']}"
                    lead_email = (audited_lead.get("email") or "").strip()
                    lead_phone = (audited_lead.get("phone") or "").strip()

                    # PRIORITY 1: If email exists, always choose Email first (Sent directly to client only)
                    if lead_email:
                        await email_worker.send_email(
                            lead_id=lead_id,
                            to_email=lead_email,
                            subject=audited_lead.get("draft_email_subject", f"Quick idea for {lead['business_name']}"),
                            body=audited_lead.get("draft_email_body", ""),
                            is_reply=False,
                        )
                        db.log_activity(
                            "SUCCESS",
                            "OUTREACH",
                            f"Priority Channel Selected (EMAIL): Dispatched directly to client '{lead['business_name']}' at {lead_email}. All audit details & screenshots saved to Dashboard.",
                        )
                    # PRIORITY 2: If no email found on website, contact via Phone / WhatsApp
                    elif lead_phone:
                        await whatsapp_worker.send_whatsapp_message(
                            lead_id=lead_id,
                            phone=lead_phone,
                            message=audited_lead.get("draft_whatsapp_msg", ""),
                            is_reply=False,
                        )
                        db.log_activity(
                            "INFO",
                            "OUTREACH",
                            f"Secondary Channel Selected (PHONE/WHATSAPP): No email on website for '{lead['business_name']}' -> Contacted via phone/WhatsApp {lead_phone}.",
                        )
                    else:
                        db.log_activity(
                            "WARN",
                            "OUTREACH",
                            f"Lead '{lead['business_name']}' has neither email nor phone on listing. Full dossier stored in Dashboard.",
                        )
                else:
                    db.log_activity(
                        "INFO",
                        "ORCHESTRATOR",
                        f"Prepared AI Audit & Personalized Email/WhatsApp drafts for '{lead['business_name']}' (Ready to send).",
                    )

                # Note: Per user preference, lead audit dossiers are saved in SQLite/Dashboard only.
                # Emails are sent EXCLUSIVELY to actual clients, and owner (zaiebad56@gmail.com) is notified
                # ONLY when a client confirms/wins a deal or requests a kickoff call.

                self.processed_count = idx + 1

                # Anti-Spam Random Delay between leads (4 to 8 minutes in production, or 3-5s in fast test mode)
                if auto_send and idx < len(inserted_lead_ids) - 1 and self.campaign_running:
                    if fast_demo_delay:
                        delay_secs = random.randint(2, 4)
                    else:
                        delay_secs = random.randint(
                            settings.MIN_OUTREACH_DELAY_SECONDS,
                            settings.MAX_OUTREACH_DELAY_SECONDS,
                        )
                    db.log_activity(
                        "INFO",
                        "ANTI_SPAM",
                        f"Anti-Spam Safety Active: Waiting {delay_secs}s before messaging next lead...",
                    )
                    for remaining in range(delay_secs, 0, -1):
                        if not self.campaign_running:
                            break
                        self.next_outreach_countdown = remaining
                        self.current_stage = f"ANTI-SPAM COOLDOWN ({remaining}s remaining)"
                        await asyncio.sleep(1)
                    self.next_outreach_countdown = 0

            self.current_stage = "COMPLETED"
            db.log_activity(
                "SUCCESS",
                "ORCHESTRATOR",
                f"✅ Campaign Finished! Processed {self.processed_count} leads for '{category}' in '{location}'.",
            )
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            db.log_activity("ERROR", "ORCHESTRATOR", f"Campaign pipeline error: {exc}")
        finally:
            self.campaign_running = False
            self.next_outreach_countdown = 0
            if self.current_stage != "COMPLETED":
                self.current_stage = "IDLE"



    # -------------------------------------------------------------------------
    # 24/7 AUTONOMOUS AI SALES AGENT (REPLY & SELF-LEARNING LOOP)
    # -------------------------------------------------------------------------
    async def process_incoming_reply(
        self,
        lead: Dict[str, Any],
        channel: str,
        sender_address: str,
        message_text: str,
        external_msg_id: str = "",
    ) -> Dict[str, Any]:
        """
        Process a single incoming client reply (from Gmail IMAP, WhatsApp Web, or Dashboard Simulator):
        1. Log client message in SQLite conversations
        2. Run Gemini AI Sales Agent with agency_knowledge.txt + chat history
        3. Persist learned insight to agency_knowledge.txt
        4. Send autonomous reply via Gmail SMTP or WhatsApp Web
        5. Trigger HOT LEAD ALERT (Desktop + Dashboard) if client is interested in call/meeting
        """
        lead_id = lead["id"]
        history = db.get_lead_conversation(lead_id)

        ai_decision = await ai_engine.generate_sales_reply(
            lead=lead,
            incoming_message=message_text,
            channel=channel,
            history=history,
        )

        intent = ai_decision.get("intent", "QUESTION").upper()
        learned_insight = ai_decision.get("learned_insight", "")
        reply_text = ai_decision.get("reply_message", "")
        reply_subject = ai_decision.get("reply_subject", f"Re: {lead.get('business_name')}")
        should_send = bool(ai_decision.get("should_send_reply", True))

        # 1. Record client's incoming message
        db.add_conversation_message(
            lead_id=lead_id,
            channel=channel,
            sender="CLIENT",
            sender_address=sender_address,
            message_text=message_text,
            detected_intent=intent,
            external_msg_id=external_msg_id,
            learned_insight=learned_insight,
        )

        db.log_activity(
            "INFO",
            "SALES_AGENT",
            f"📩 New {channel} reply from '{lead.get('business_name')}' | Detected Intent: {intent}",
        )

        # 2. Save self-learning insight to agency_knowledge.txt
        if learned_insight:
            settings.append_self_learning_insight(learned_insight)

        # 3. If DEAL_WON or HOT_LEAD, trigger Alerts & Owner Email!
        if intent == "DEAL_WON":
            self.trigger_deal_won_alert(lead, channel, message_text)
        elif intent == "HOT_LEAD":
            self.trigger_hot_lead_alert(lead, channel, message_text)

        # 4. Send Autonomous Reply if appropriate
        if should_send and reply_text:
            if channel.upper() == "EMAIL" and lead.get("email"):
                await email_worker.send_email(
                    lead_id=lead_id,
                    to_email=lead["email"],
                    subject=reply_subject,
                    body=reply_text,
                    is_reply=True,
                )
            elif channel.upper() == "WHATSAPP" and lead.get("phone"):
                await whatsapp_worker.send_whatsapp_message(
                    lead_id=lead_id,
                    phone=lead["phone"],
                    message=reply_text,
                    is_reply=True,
                )

            db.add_conversation_message(
                lead_id=lead_id,
                channel=channel,
                sender="AI_AGENT",
                sender_address=settings.GMAIL_ADDRESS if channel.upper() == "EMAIL" else "WhatsApp AI",
                message_text=reply_text,
                detected_intent=intent,
                learned_insight=learned_insight,
            )
            db.log_activity(
                "SUCCESS",
                "SALES_AGENT",
                f"🤖 Autonomous AI Sales Agent replied to '{lead.get('business_name')}' on {channel}.",
            )

        return {
            "lead_id": lead_id,
            "intent": intent,
            "ai_reply": reply_text,
            "learned_insight": learned_insight,
        }

    async def poll_all_replies_once(self) -> int:
        """Poll both Gmail IMAP and WhatsApp Web for new replies."""
        processed = 0

        # 1. Check Gmail IMAP
        imap_replies = await email_worker.check_incoming_replies()
        for item in imap_replies:
            await self.process_incoming_reply(
                lead=item["lead"],
                channel="EMAIL",
                sender_address=item["sender_email"],
                message_text=item["message_text"],
                external_msg_id=item["external_msg_id"],
            )
            processed += 1

        # 2. Check WhatsApp Web Unread
        wa_replies = await whatsapp_worker.check_unread_replies()
        for item in wa_replies:
            await self.process_incoming_reply(
                lead=item["lead"],
                channel="WHATSAPP",
                sender_address=item["sender_phone"],
                message_text=item["message_text"],
                external_msg_id=item["external_msg_id"],
            )
            processed += 1

        return processed

    # -------------------------------------------------------------------------
    # END-OF-DAY (EOD) SUMMARY REPORT GENERATOR & DISPATCHER
    # -------------------------------------------------------------------------
    async def generate_and_send_eod_report(self) -> Dict[str, Any]:
        stats = db.get_dashboard_stats()
        today = stats["date"]
        hot_leads = [
            l for l in db.get_leads(limit=50) if l.get("is_hot_lead") == 1 or l.get("status") == "HOT_LEAD"
        ]
        contacted_today = db.get_outreach_logs(limit=40)

        hot_list_str = "\n".join(
            [
                f"  • {hl['business_name']} ({hl.get('category')}) — Phone: {hl.get('phone') or 'N/A'} | Email: {hl.get('email') or 'N/A'}"
                for hl in hot_leads[:10]
            ]
        ) or "  • None yet today"

        outreach_list_str = "\n".join(
            [
                f"  • {o.get('business_name') or 'Lead'} via {o.get('channel')} ({o.get('recipient')}) -> {o.get('delivery_status')}"
                for o in contacted_today[:12]
            ]
        ) or "  • No outreach sent yet today"

        summary_md = (
            f"📊 END-OF-DAY (EOD) LEAD HUNTER AI REPORT ({today})\n"
            f"====================================================\n"
            f"• New Clients Scraped Today: {stats['today_leads']} (Total in DB: {stats['total_leads']})\n"
            f"• High Priority Leads (No Website / Urgent): {stats['high_priority']}\n"
            f"• Personalized Emails Sent Today: {stats['emails_today']} / {stats['daily_email_limit']}\n"
            f"• WhatsApp Messages Sent Today: {stats['whatsapps_today']} / {stats['daily_whatsapp_limit']}\n"
            f"• Client Replies Received Today: {stats['replies_today']} (Total Replies: {stats['total_replies']})\n"
            f"• 🔥 Hot Leads Ready for Call: {stats['hot_leads']}\n\n"
            f"🔥 HOT LEADS READY FOR CLOSING:\n{hot_list_str}\n\n"
            f"📤 RECENT OUTREACH LOG:\n{outreach_list_str}\n"
        )

        # Send to Agency Owner's Personal Email
        owner_email = settings.AGENCY_OWNER_EMAIL or settings.GMAIL_ADDRESS
        emailed = await email_worker.send_raw_notification_email(
            to_email=owner_email,
            subject=f"📊 EOD Lead Hunter Summary Report - {today} ({stats['hot_leads']} Hot Leads)",
            body=summary_md,
        )

        # Send to Agency Owner's Personal WhatsApp if configured & connected
        whatsapped = False
        if settings.AGENCY_OWNER_WHATSAPP and len(settings.AGENCY_OWNER_WHATSAPP) >= 8:
            wa_res = await whatsapp_worker.send_whatsapp_message(
                lead_id=0,
                phone=settings.AGENCY_OWNER_WHATSAPP,
                message=summary_md,
                is_reply=True,
            )
            whatsapped = wa_res.get("status") == "SENT"

        saved_report = db.save_daily_report(
            report_date=today,
            stats=stats,
            summary_markdown=summary_md,
            emailed=emailed,
            whatsapped=whatsapped,
        )

        db.log_activity(
            "SUCCESS",
            "EOD",
            f"Generated End-of-Day Summary Report for {today} (Hot Leads: {stats['hot_leads']}).",
        )
        return saved_report

    # -------------------------------------------------------------------------
    # BACKGROUND 24/7 DAEMON (5-MINUTE REPLY CHECK + EOD SCHEDULER)
    # -------------------------------------------------------------------------
    async def start_background_daemon(self):
        if self._daemon_task and not self._daemon_task.done():
            return
        self._daemon_task = asyncio.create_task(self._daemon_loop())

    async def _daemon_loop(self):
        db.log_activity(
            "INFO",
            "SALES_AGENT",
            f"24/7 Autonomous AI Sales Agent active (Checking Gmail IMAP & WhatsApp every {settings.REPLY_CHECK_INTERVAL_MINUTES} mins).",
        )
        while True:
            try:
                await asyncio.sleep(max(60, settings.REPLY_CHECK_INTERVAL_MINUTES * 60))
                await self.poll_all_replies_once()

                # Check if current time matches EOD_REPORT_TIME (e.g. "20:00")
                now = datetime.now()
                today_str = now.strftime("%Y-%m-%d")
                hh_mm = now.strftime("%H:%M")
                if hh_mm == settings.EOD_REPORT_TIME and self._last_eod_sent_date != today_str:
                    self._last_eod_sent_date = today_str
                    await self.generate_and_send_eod_report()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                db.log_activity("WARN", "SALES_AGENT", f"Background loop warning: {exc}")


orchestrator = AutomationOrchestrator()

