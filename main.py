import asyncio
import csv
import io
import imaplib
import smtplib
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import settings
from database import db
from workers.ai_engine import ai_engine
from workers.email_worker import email_worker
from workers.global_presets import GLOBAL_CATEGORIES, GLOBAL_LOCATIONS, HOT_GLOBAL_PRESETS
from workers.orchestrator import orchestrator
from workers.website_auditor import website_auditor
from workers.whatsapp_worker import whatsapp_worker
from workers.autopilot import autopilot

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.log_activity(
        "INFO",
        "SYSTEM",
        f"Lead Hunter AI Automation System started on http://localhost:{settings.PORT}",
    )
    await orchestrator.start_background_daemon()
    yield


app = FastAPI(
    title="Lead Hunter AI Automation System",
    description="100% Free ($0/mo) Autonomous Lead Scraper, AI Website Auditor, Outreach & 24/7 AI Sales Agent",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

SCREENSHOTS_DIR = BASE_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/screenshots", StaticFiles(directory=str(SCREENSHOTS_DIR)), name="screenshots")


# -----------------------------------------------------------------------------
# REQUEST MODELS
# -----------------------------------------------------------------------------
class StartCampaignRequest(BaseModel):
    location: str = "Toronto, Canada"
    category: str = "Restaurants"
    daily_limit: int = 8
    fast_demo_delay: bool = True
    auto_send: bool = True


class SimulateReplyRequest(BaseModel):
    lead_id: int
    channel: str = "EMAIL"
    message_text: str


class ManualOutreachRequest(BaseModel):
    lead_id: int
    channel: str = "EMAIL"
    subject: Optional[str] = None
    message_body: Optional[str] = None


class KnowledgeUpdateRequest(BaseModel):
    content: str


class SettingsUpdateRequest(BaseModel):
    updates: Dict[str, Any]


class CustomLeadRequest(BaseModel):
    business_name: str
    category: str = "Restaurants"
    location: str = "Toronto, Canada"
    phone: str = ""
    email: str = ""
    website: str = ""
    rating: float = 4.8
    reviews_count: int = 64


class LeadContactUpdateRequest(BaseModel):
    email: str = ""
    phone: str = ""
    website: str = ""


class CustomerBookingRequest(BaseModel):
    lead_id: Optional[int] = 0
    business_name: str
    customer_name: str = ""
    customer_email: str = ""
    customer_phone: str = ""
    selected_package: str = "Starter Growth Website + Local SEO ($399 - $699)"
    budget_range: str = "$399 - $699"
    preferred_call_time: str = "Tomorrow 2:00 PM"
    project_notes: str = ""


class CustomerInstantAuditRequest(BaseModel):
    business_name: str
    category: str = "Local Business"
    location: str = "Toronto, Canada"
    website: str = ""
    email: str = ""
    phone: str = ""


# -----------------------------------------------------------------------------
# ROUTES
# -----------------------------------------------------------------------------
@app.get("/")
async def serve_dashboard():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/customer")
async def serve_customer_portal():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/dashboard")
async def get_dashboard_overview(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    search: Optional[str] = None,
):
    """Single aggregated endpoint for fast real-time Dashboard polling with dynamic search."""
    return {
        "stats": db.get_dashboard_stats(),
        "state": orchestrator.get_state(),
        "leads": db.get_leads(status_filter=status, priority_filter=priority, search=search, limit=250),
        "logs": db.get_recent_logs(limit=70),
        "customer_requests": db.get_customer_requests(limit=30),
    }


@app.post("/api/campaign/start")
async def api_start_campaign(req: StartCampaignRequest):
    return orchestrator.start_campaign(
        location=req.location,
        category=req.category,
        daily_limit=req.daily_limit,
        fast_demo_delay=req.fast_demo_delay,
        auto_send=req.auto_send,
    )


@app.post("/api/campaign/stop")
async def api_stop_campaign():
    return orchestrator.stop_campaign()


@app.get("/api/presets/locations-categories")
async def api_get_global_presets():
    """Worldwide locations & high-converting business categories for client hunting."""
    return {
        "locations": GLOBAL_LOCATIONS,
        "categories": GLOBAL_CATEGORIES,
        "hot_presets": HOT_GLOBAL_PRESETS,
    }


@app.get("/api/leads/{lead_id}")
async def api_get_lead(lead_id: int):
    lead = db.get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead["conversation"] = db.get_lead_conversation(lead_id)
    return lead


@app.post("/api/leads/{lead_id}/reaudit")
async def api_reaudit_lead(lead_id: int):
    lead = db.get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    updated = await website_auditor.audit_lead_and_prepare_outreach(lead)
    return {"ok": True, "lead": updated}


@app.post("/api/leads/{lead_id}/send-owner-report")
async def api_send_lead_owner_report(lead_id: int):
    """Manually dispatch the full Lead Audit Dossier + Screenshot attachments to owner's personal email."""
    lead = db.get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # If lead has not been audited yet, run the audit & dual screenshot capture first
    report = lead.get("audit_report") or {}
    if not report.get("screenshot_url") and not lead.get("screenshot_desktop") and not lead.get("maps_screenshot"):
        lead = await website_auditor.audit_lead_and_prepare_outreach(lead)

    res = await email_worker.send_lead_audit_report_to_owner(lead)
    return res


@app.get("/api/leads/{lead_id}/email-preview", response_class=HTMLResponse)
async def api_preview_html_email(lead_id: int):
    """Render the exact Professional HTML Audit Email Template (with live Website Screenshot) in browser."""
    lead = db.get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    report = lead.get("audit_report") or {}
    if not report.get("screenshot_url"):
        lead = await website_auditor.audit_lead_and_prepare_outreach(lead)

    body_text = lead.get("draft_email_body") or f"Hi {lead.get('business_name')} Team,"
    html_email = email_worker.build_professional_audit_email_html(
        lead=lead,
        body_text=body_text,
        use_cid_image=False,
    )
    return HTMLResponse(content=html_email)


@app.post("/api/leads/custom")
async def api_add_custom_lead(req: CustomLeadRequest):
    """Add a custom lead manually and immediately run AI Website Audit & Outreach generation."""
    lead_id = db.insert_lead(
        {
            "business_name": req.business_name,
            "category": req.category,
            "location": req.location,
            "phone": req.phone,
            "email": req.email,
            "website": req.website,
            "rating": req.rating,
            "reviews_count": req.reviews_count,
            "reviews_snippet": f"Local {req.category} business in {req.location}",
        }
    )
    lead = db.get_lead_by_id(lead_id)
    if lead:
        lead = await website_auditor.audit_lead_and_prepare_outreach(lead)
    return {"ok": True, "lead": lead}


@app.put("/api/leads/{lead_id}")
async def api_update_lead_contact(lead_id: int, req: LeadContactUpdateRequest):
    db.update_lead_contact(lead_id, email=req.email, phone=req.phone, website=req.website)
    db.log_activity("INFO", "SYSTEM", f"Updated contact details for Lead #{lead_id}.")
    return {"ok": True, "lead": db.get_lead_by_id(lead_id)}


@app.delete("/api/leads/{lead_id}")
async def api_delete_lead(lead_id: int):
    db.delete_lead(lead_id)
    db.log_activity("INFO", "SYSTEM", f"Deleted Lead #{lead_id}.")
    return {"ok": True}


@app.get("/preview/{lead_id}", response_class=HTMLResponse)
async def serve_dynamic_ai_mockup_preview(lead_id: int):
    """
    Dynamic AI Visual Mockup & Proposal Generator:
    Renders a live, responsive Landing Page Concept + Audit Upgrade Proposal tailored to the lead!
    """
    lead = db.get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    copy_data = await ai_engine.generate_visual_mockup_data(lead)
    bname = lead.get("business_name", "Business")
    cat = lead.get("category", "Local Business")
    loc = lead.get("location", "")
    rating = lead.get("rating") or 4.8
    reviews = lead.get("reviews_count") or 50
    audit = lead.get("audit_report") or {}
    issues = audit.get("issues_found") or ["No direct commission-free mobile ordering/booking system"]
    solutions = audit.get("recommended_solutions") or ["Custom Mobile-First Website & Direct Ordering Engine"]
    features = copy_data.get("features") or []

    features_html = "".join(
        [
            f"""
            <div class="p-6 rounded-2xl bg-slate-900/90 border border-slate-800 shadow-xl">
              <div class="w-10 h-10 rounded-xl bg-indigo-500/20 text-indigo-400 flex items-center justify-center font-bold mb-4">✦</div>
              <h3 class="text-lg font-bold text-white mb-2">{f.get('title', 'Modern Upgrade')}</h3>
              <p class="text-sm text-slate-400 leading-relaxed">{f.get('desc', '')}</p>
            </div>
            """
            for f in features[:3]
        ]
    )

    issues_html = "".join([f"<li class='text-rose-300 text-sm'>• {i}</li>" for i in issues[:4]])
    solutions_html = "".join([f"<li class='text-emerald-300 text-sm'>✓ {s}</li>" for s in solutions[:4]])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{bname} — Custom Interactive Website Concept by {settings.AGENCY_NAME}</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-white font-sans antialiased">
  <!-- Top Proposal Banner -->
  <div class="bg-gradient-to-r from-indigo-600 via-purple-600 to-emerald-600 text-white text-xs py-2.5 px-4 text-center font-semibold">
    ✨ LIVE INTERACTIVE CONCEPT MOCKUP PREPARED FOR <strong>{bname.upper()}</strong> BY {settings.AGENCY_NAME.upper()} ({settings.GMAIL_ADDRESS})
  </div>

  <!-- Hero Section -->
  <header class="max-w-6xl mx-auto px-6 py-16 text-center">
    <span class="inline-block px-4 py-1.5 rounded-full bg-amber-500/15 border border-amber-500/30 text-amber-300 text-xs font-bold mb-6">
      {copy_data.get('hero_badge', f'★ {rating} Rated ({reviews} Reviews) in {loc}')}
    </span>
    <h1 class="text-4xl sm:text-6xl font-extrabold tracking-tight bg-gradient-to-r from-white via-slate-100 to-indigo-300 bg-clip-text text-transparent max-w-4xl mx-auto leading-tight">
      {copy_data.get('hero_headline', f'Welcome to {bname}')}
    </h1>
    <p class="mt-6 text-lg text-slate-300 max-w-2xl mx-auto leading-relaxed">
      {copy_data.get('hero_subheadline', f'Order online or book your appointment directly from your phone with zero third-party commissions.')}
    </p>
    <div class="mt-8 flex flex-wrap items-center justify-center gap-4">
      <a href="mailto:{settings.GMAIL_ADDRESS}?subject=Approve%20Mockup%20for%20{bname}"
         class="px-7 py-3.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-extrabold text-sm shadow-lg shadow-emerald-500/25 transition">
        🚀 {copy_data.get('primary_cta', 'Order / Book Online Now')}
      </a>
      <a href="mailto:{settings.GMAIL_ADDRESS}?subject=Schedule%2010-Min%20Demo%20for%20{bname}"
         class="px-7 py-3.5 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-white font-bold text-sm transition">
        💬 {copy_data.get('secondary_cta', 'Book 10-Min Discovery Call')}
      </a>
    </div>
  </header>

  <!-- 3 Value Pillars -->
  <section class="max-w-6xl mx-auto px-6 py-10 grid grid-cols-1 md:grid-cols-3 gap-6">
    {features_html}
  </section>

  <!-- AI Audit Comparison Card -->
  <section class="max-w-5xl mx-auto px-6 py-12">
    <div class="rounded-3xl bg-slate-900/90 border border-slate-800 p-8 grid grid-cols-1 md:grid-cols-2 gap-8">
      <div>
        <h3 class="text-sm font-extrabold uppercase tracking-wider text-rose-400 mb-3">🔍 Current Digital Bottlenecks Found</h3>
        <ul class="space-y-2">{issues_html}</ul>
      </div>
      <div>
        <h3 class="text-sm font-extrabold uppercase tracking-wider text-emerald-400 mb-3">💡 Proposed {settings.AGENCY_NAME} Upgrade</h3>
        <ul class="space-y-2">{solutions_html}</ul>
      </div>
    </div>
  </section>

  <footer class="border-t border-slate-900 py-8 text-center text-xs text-slate-500">
    Designed & Audited Autonomously by <strong>{settings.SENDER_NAME}</strong> • {settings.AGENCY_NAME} • {settings.GMAIL_ADDRESS}
  </footer>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.post("/api/outreach/send")
async def api_manual_outreach(req: ManualOutreachRequest):
    lead = db.get_lead_by_id(req.lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if req.channel.upper() == "EMAIL":
        to_email = lead.get("email") or "demo-client@business.local"
        subj = req.subject or lead.get("draft_email_subject") or f"Quick idea for {lead['business_name']}"
        body = req.message_body or lead.get("draft_email_body") or ""
        return await email_worker.send_email(
            lead_id=lead["id"], to_email=to_email, subject=subj, body=body, is_reply=False
        )
    else:
        phone = lead.get("phone") or "+14165550199"
        msg = req.message_body or lead.get("draft_whatsapp_msg") or ""
        return await whatsapp_worker.send_whatsapp_message(
            lead_id=lead["id"], phone=phone, message=msg, is_reply=False
        )


@app.get("/api/conversations")
async def api_get_conversations():
    return {"conversations": db.get_all_conversations_grouped()}


@app.post("/api/sales-agent/poll")
async def api_poll_replies_now():
    count = await orchestrator.poll_all_replies_once()
    db.log_activity(
        "INFO",
        "SALES_AGENT",
        f"Manual Gmail IMAP & WhatsApp reply check completed ({count} new replies processed).",
    )
    return {"ok": True, "processed": count}


@app.post("/api/sales-agent/simulate-reply")
async def api_simulate_client_reply(req: SimulateReplyRequest):
    """
    Allows testing the 24/7 Autonomous AI Sales Agent, Self-Learning, Calendar Link injection,
    and Desktop/Dashboard HOT LEAD ALERT with any custom client reply!
    """
    lead = db.get_lead_by_id(req.lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    sender_addr = lead.get("email") if req.channel.upper() == "EMAIL" else lead.get("phone")
    result = await orchestrator.process_incoming_reply(
        lead=lead,
        channel=req.channel.upper(),
        sender_address=sender_addr or "client@business.com",
        message_text=req.message_text,
    )
    return {"ok": True, "result": result}


@app.post("/api/whatsapp/connect")
async def api_connect_whatsapp():
    status = await whatsapp_worker.initialize_session(headless=False)
    return {"ok": True, "whatsapp": status}


@app.get("/api/whatsapp/status")
async def api_whatsapp_status():
    status = await whatsapp_worker.refresh_status()
    return {"ok": True, "whatsapp": status}


@app.get("/api/eod-reports")
async def api_get_eod_reports():
    return {
        "reports": db.get_daily_reports(limit=30),
        "outreach_logs": db.get_outreach_logs(limit=60),
    }


@app.post("/api/eod-reports/generate")
async def api_generate_eod_report():
    report = await orchestrator.generate_and_send_eod_report()
    return {"ok": True, "report": report}


@app.get("/api/settings")
async def api_get_settings():
    return {
        "env": {
            "GEMINI_API_KEY": settings.GEMINI_API_KEY,
            "GEMINI_COMPLEX_MODEL": settings.GEMINI_COMPLEX_MODEL,
            "GEMINI_FAST_MODEL": settings.GEMINI_FAST_MODEL,
            "GROQ_API_KEY": settings.GROQ_API_KEY,
            "GROQ_MODEL": settings.GROQ_MODEL,
            "GMAIL_ADDRESS": settings.GMAIL_ADDRESS,
            "GMAIL_APP_PASSWORD": settings.GMAIL_APP_PASSWORD,
            "SENDER_NAME": settings.SENDER_NAME,
            "AGENCY_NAME": settings.AGENCY_NAME,
            "AGENCY_OWNER_EMAIL": settings.AGENCY_OWNER_EMAIL,
            "MY_PERSONAL_EMAIL": settings.MY_PERSONAL_EMAIL,
            "SEND_LEAD_REPORTS_TO_OWNER": settings.SEND_LEAD_REPORTS_TO_OWNER,
            "AGENCY_OWNER_WHATSAPP": settings.AGENCY_OWNER_WHATSAPP,
            "CALENDAR_BOOKING_LINK": settings.CALENDAR_BOOKING_LINK,
            "AGENCY_PORTFOLIO_URL": settings.AGENCY_PORTFOLIO_URL,
            "DAILY_EMAIL_LIMIT": settings.DAILY_EMAIL_LIMIT,
            "DAILY_WHATSAPP_LIMIT": settings.DAILY_WHATSAPP_LIMIT,
            "MIN_OUTREACH_DELAY_SECONDS": settings.MIN_OUTREACH_DELAY_SECONDS,
            "MAX_OUTREACH_DELAY_SECONDS": settings.MAX_OUTREACH_DELAY_SECONDS,
            "REPLY_CHECK_INTERVAL_MINUTES": settings.REPLY_CHECK_INTERVAL_MINUTES,
            "EOD_REPORT_TIME": settings.EOD_REPORT_TIME,
            "HEADLESS_SCRAPER": settings.HEADLESS_SCRAPER,
        },
        "knowledge_base": settings.get_knowledge_base(),
    }


@app.post("/api/settings")
async def api_save_settings(req: SettingsUpdateRequest):
    settings.update_env(req.updates)
    db.log_activity("SUCCESS", "SYSTEM", "Updated .env configuration settings from Dashboard.")
    return {"ok": True}


@app.post("/api/knowledge")
async def api_save_knowledge(req: KnowledgeUpdateRequest):
    settings.save_knowledge_base(req.content)
    db.log_activity("SUCCESS", "SYSTEM", "Updated agency_knowledge.txt for 24/7 AI Sales Agent.")
    return {"ok": True}


# -----------------------------------------------------------------------------
# 24/7 AUTONOMOUS CLOUD & LOCAL AUTOPILOT CONTROLS
# -----------------------------------------------------------------------------
@app.get("/api/autopilot/state")
async def api_get_autopilot_state():
    state = db.get_autopilot_state()
    next_tgt = autopilot.get_next_target()
    stats = db.get_dashboard_stats()
    return {
        "ok": True,
        "state": state,
        "next_target": next_tgt,
        "stats": {
            "emails_today": stats.get("emails_today", 0),
            "daily_limit": settings.DAILY_EMAIL_LIMIT,
            "hot_leads": stats.get("hot_leads", 0),
            "total_leads": stats.get("total_leads", 0),
        },
    }


@app.post("/api/autopilot/toggle")
async def api_toggle_autopilot():
    state = db.get_autopilot_state()
    new_val = not bool(state.get("is_enabled", 1))
    db.update_autopilot_state(is_enabled=1 if new_val else 0)
    db.log_activity(
        "INFO",
        "AUTOPILOT",
        f"AutoPilot 24/7 autonomous mode turned {'ON' if new_val else 'OFF'} by user.",
    )
    return {"ok": True, "is_enabled": new_val}


@app.post("/api/autopilot/run-now")
async def api_run_autopilot_now():
    if autopilot.is_running:
        return {"ok": False, "message": "AutoPilot cycle is already in progress!"}
    
    asyncio.create_task(autopilot.run_cycle(batch_limit=10, is_cloud=False))
    return {
        "ok": True,
        "message": "AutoPilot cycle launched in background! Check Live Activity Feed for real-time progress.",
    }



@app.post("/api/customer/instant-audit")
async def api_customer_instant_audit(req: CustomerInstantAuditRequest):
    """Customer Panel self-service AI Website & Digital Growth Audit."""
    lead_id = db.insert_lead(
        {
            "business_name": req.business_name,
            "category": req.category,
            "location": req.location,
            "website": req.website,
            "email": req.email,
            "phone": req.phone,
            "rating": 4.8,
            "reviews_count": 45,
        }
    )
    lead = db.get_lead_by_id(lead_id)
    if lead:
        lead = await website_auditor.audit_lead_and_prepare_outreach(lead)
    return {"ok": True, "lead": lead}


@app.post("/api/customer/order")
async def api_customer_submit_order(req: CustomerBookingRequest):
    """Customer Panel package selection & discovery call booking submission."""
    lead_id = req.lead_id or 0
    if lead_id <= 0:
        lead_id = db.insert_lead(
            {
                "business_name": req.business_name,
                "category": "Customer Portal Booking",
                "location": "Customer Portal",
                "email": req.customer_email,
                "phone": req.customer_phone,
                "status": "HOT_LEAD",
                "priority": "HIGH_PRIORITY",
            }
        )
    saved = db.create_customer_request(
        {
            "lead_id": lead_id,
            "business_name": req.business_name,
            "customer_name": req.customer_name,
            "customer_email": req.customer_email,
            "customer_phone": req.customer_phone,
            "selected_package": req.selected_package,
            "budget_range": req.budget_range,
            "preferred_call_time": req.preferred_call_time,
            "project_notes": req.project_notes,
        }
    )
    lead = db.get_lead_by_id(lead_id) or {"id": lead_id, "business_name": req.business_name}
    msg = (
        f"[CUSTOMER PORTAL BOOKING] Package: {req.selected_package} | "
        f"Preferred Call Time: {req.preferred_call_time} | Notes: {req.project_notes}"
    )
    await orchestrator.process_incoming_reply(
        lead=lead,
        channel="EMAIL" if req.customer_email else "WHATSAPP",
        sender_address=req.customer_email or req.customer_phone or "Customer Portal",
        message_text=msg,
    )
    return {"ok": True, "booking": saved, "lead_id": lead_id}


@app.get("/api/leads/export/csv")
async def api_export_leads_csv():
    """Export all scraped leads, AI audit scores, and outreach statuses as a CSV file."""
    leads = db.get_leads(limit=2000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "ID",
            "Business Name",
            "Category",
            "Location",
            "Phone",
            "Email",
            "Website",
            "Rating",
            "Reviews Count",
            "Priority",
            "Audit Score",
            "Stage",
            "Hot Lead",
            "Email Sent",
            "WhatsApp Sent",
            "Created At",
        ]
    )
    for l in leads:
        writer.writerow(
            [
                l.get("id"),
                l.get("business_name"),
                l.get("category"),
                l.get("location"),
                l.get("phone"),
                l.get("email"),
                l.get("website") or "NO WEBSITE",
                l.get("rating"),
                l.get("reviews_count"),
                l.get("priority"),
                l.get("audit_score"),
                l.get("status"),
                "YES" if l.get("is_hot_lead") else "NO",
                "YES" if l.get("email_sent") else "NO",
                "YES" if l.get("whatsapp_sent") else "NO",
                l.get("created_at"),
            ]
        )
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=lead_hunter_leads.csv"},
    )


@app.post("/api/outreach/followup")
async def api_run_followup_sequence():
    """Send a polite Follow-up #2 message to CONTACTED leads that have not replied yet."""
    contacted_leads = db.get_leads(status_filter="CONTACTED", limit=15)
    sent_count = 0
    for lead in contacted_leads:
        bname = lead.get("business_name", "there")
        followup_subj = f"Re: Quick idea for {bname}"
        followup_body = (
            f"Hi {bname} Team,\n\n"
            f"Just floating this to the top of your inbox in case you missed my note earlier! "
            f"I put together a quick 2-minute concept showing how {bname} can capture more direct mobile orders & bookings.\n\n"
            f"Would you like me to share the preview link, or is there a good time for a quick 10-minute chat here: {settings.CALENDAR_BOOKING_LINK} ?\n\n"
            f"Best,\n{settings.SENDER_NAME}"
        )
        if lead.get("email"):
            res = await email_worker.send_email(
                lead_id=lead["id"],
                to_email=lead["email"],
                subject=followup_subj,
                body=followup_body,
                is_reply=True,
            )
            if res.get("ok"):
                sent_count += 1
                db.add_conversation_message(
                    lead_id=lead["id"],
                    channel="EMAIL",
                    sender="AI_AGENT",
                    sender_address=settings.GMAIL_ADDRESS,
                    message_text=followup_body,
                    detected_intent="FOLLOW_UP",
                )
    db.log_activity("SUCCESS", "EMAIL", f"Auto Follow-up Sequence sent to {sent_count} non-replied leads.")
    return {"ok": True, "sent_count": sent_count}


@app.post("/api/diagnostics")
async def api_run_diagnostics():
    """Verify live AI Brain (Gemini/Groq) and Gmail SMTP/IMAP connectivity."""
    ai_reply = await ai_engine.generate("Reply with ONLY: AI_ONLINE", use_complex_model=False)
    ai_ok = bool(ai_reply and "AI_ONLINE" in ai_reply.upper())

    smtp_ok = False
    imap_ok = False
    gmail_error = ""

    if settings.is_gmail_configured():
        pwd = settings.GMAIL_APP_PASSWORD.replace(" ", "")
        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=12) as server:
                server.ehlo()
                server.starttls()
                server.login(settings.GMAIL_ADDRESS, pwd)
                smtp_ok = True
        except Exception as exc:
            gmail_error = f"SMTP: {exc}"

        try:
            mail = imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT)
            mail.login(settings.GMAIL_ADDRESS, pwd)
            mail.logout()
            imap_ok = True
        except Exception as exc:
            gmail_error += f" | IMAP: {exc}"

    db.log_activity(
        "SUCCESS" if (ai_ok and smtp_ok and imap_ok) else "WARN",
        "SYSTEM",
        f"Diagnostics -> AI Brain: {'OK' if ai_ok else 'FAIL'} | Gmail SMTP: {'OK' if smtp_ok else 'FAIL'} | Gmail IMAP: {'OK' if imap_ok else 'FAIL'}",
    )
    return {
        "ok": True,
        "ai_ok": ai_ok,
        "smtp_ok": smtp_ok,
        "imap_ok": imap_ok,
        "gmail_error": gmail_error,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=settings.PORT, reload=False)

