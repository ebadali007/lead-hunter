import asyncio
import email
import html as html_lib
import imaplib
from pathlib import Path
import re
import smtplib
import socket
from datetime import datetime, timedelta
from email.header import decode_header
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr
from typing import Any, Dict, List, Optional, Tuple

from config import settings
from database import db

BASE_DIR = Path(__file__).resolve().parent.parent


class GmailWorker:
    """
    Zero-Cost Gmail Automation Engine:
    - Outbound Cold Outreach with Professional HTML Audit Template + Embedded Website Screenshot (CID)
    - Inbound Client Reply Detection via Gmail IMAP (imap.gmail.com:993)
    """

    @staticmethod
    def _is_deliverable_domain(email_addr: str) -> bool:
        """Verify domain resolves via DNS before sending live SMTP to protect Gmail sender reputation."""
        if not email_addr or "@" not in email_addr:
            return False
        domain = email_addr.split("@")[-1].strip().lower()
        if not domain or domain.endswith((".local", ".test", ".invalid", ".example")):
            return False
        try:
            socket.getaddrinfo(domain, None)
            return True
        except Exception:
            return False

    @staticmethod
    def build_professional_audit_email_html(
        lead: Optional[Dict[str, Any]],
        body_text: str,
        use_cid_image: bool = True,
    ) -> str:
        """
        Build a rich, responsive Professional Agency HTML Email Template containing:
        1. Personalized intro message
        2. Live captured screenshot of the client's website (embedded via CID or URL)
        3. Technical Score Card (Speed, Mobile UX, Online Ordering/Booking, SEO/SSL)
        4. Detailed list of Website Weaknesses Found (Red Card)
        5. Detailed list of How Our Website/App/Software Upgrade Fixes Them (Green Card)
        6. Call-To-Action Button & Founder Signature
        """
        body_html_paragraphs = "".join(
            [
                f"<p style='margin:0 0 12px 0;font-size:15px;line-height:1.65;color:#1e293b;'>{html_lib.escape(line)}</p>"
                for line in body_text.splitlines()
                if line.strip()
            ]
        )

        # If this is a simple conversational reply without lead audit context, use clean professional wrapper
        if not lead:
            return f"""
            <div style="font-family:'Segoe UI',Arial,sans-serif;max-width:640px;margin:0 auto;padding:24px;color:#1e293b;">
              {body_html_paragraphs}
            </div>
            """

        bname = html_lib.escape(lead.get("business_name") or "Valued Business")
        cat = html_lib.escape(lead.get("category") or "Business")
        loc = html_lib.escape(lead.get("location") or "")
        website = html_lib.escape(lead.get("website") or "No Official Website Linked")
        score = int(lead.get("audit_score") or 50)
        report = lead.get("audit_report") or {}
        tech = report.get("technical_scan") or {}
        screenshot_url = report.get("screenshot_url") or ""

        issues = report.get("issues_found") or tech.get("detected_issues") or [
            "Missing direct commission-free online ordering / appointment booking workflow",
            "Slow mobile page load speed reducing visitor conversion",
            "Missing instant WhatsApp / AI Live Chat lead capture widget",
        ]
        solutions = report.get("recommended_solutions") or [
            f"Redesign & optimize {bname}'s website with a <1.5s mobile-first responsive layout",
            "Integrate a 0% commission direct online ordering / booking system with instant alerts",
            "Build a custom Mobile App (iOS & Android) or AI customer automation software to boost repeat sales",
        ]
        impact = html_lib.escape(
            report.get("estimated_revenue_impact")
            or "+35% to +45% increase in direct online orders, bookings & repeat mobile customers"
        )

        load_ms = tech.get("load_time_ms") or 0
        speed_txt = f"{load_ms} ms" if load_ms > 0 else ("No Site" if not lead.get("website") else "Checked")
        mobile_txt = "✅ Mobile Ready" if tech.get("is_mobile_friendly") else "❌ Needs Mobile UX"
        order_txt = "✅ Active" if tech.get("has_online_ordering_or_booking") else "❌ Missing System"
        score_color = "#e11d48" if score < 55 else ("#d97706" if score < 75 else "#059669")

        # Screenshot block
        img_src = "cid:website_screenshot" if use_cid_image else screenshot_url
        screenshot_section = ""
        if screenshot_url:
            screenshot_section = f"""
            <div style="margin:24px 0;border:1px solid #e2e8f0;border-radius:16px;overflow:hidden;background:#0f172a;box-shadow:0 8px 24px rgba(15,23,42,0.08);">
              <div style="background:#1e293b;padding:10px 16px;color:#cbd5e1;font-size:12px;font-weight:600;border-bottom:1px solid #334155;">
                🔴 LIVE AUDIT SNAPSHOT — {bname} ({website})
              </div>
              <div style="padding:12px;text-align:center;background:#0f172a;">
                <img src="{img_src}" alt="Website Audit Screenshot for {bname}" style="max-width:100%;height:auto;border-radius:10px;border:1px solid #334155;display:block;margin:0 auto;" />
              </div>
            </div>
            """

        issues_rows = "".join(
            [
                f"""
                <tr>
                  <td style="padding:10px 12px;border-bottom:1px solid #ffe4e6;color:#9f1239;font-size:14px;line-height:1.5;">
                    <strong>⚠️ Issue #{idx + 1}:</strong> {html_lib.escape(str(iss))}
                  </td>
                </tr>
                """
                for idx, iss in enumerate(issues)
            ]
        )

        solutions_rows = "".join(
            [
                f"""
                <tr>
                  <td style="padding:10px 12px;border-bottom:1px solid #d1fae5;color:#065f46;font-size:14px;line-height:1.5;">
                    <strong>✅ Upgrade #{idx + 1}:</strong> {html_lib.escape(str(sol))}
                  </td>
                </tr>
                """
                for idx, sol in enumerate(solutions)
            ]
        )

        return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
</head>
<body style="margin:0;padding:0;background-color:#f4f3f9;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1e293b;">
  <div style="max-width:680px;margin:24px auto;background-color:#ffffff;border-radius:20px;overflow:hidden;box-shadow:0 12px 36px rgba(100,116,139,0.12);border:1px solid #e2e8f0;">

    <!-- Top Branded Agency Header -->
    <div style="background:linear-gradient(135deg,#6366f1 0%,#9b51e0 50%,#ec4899 100%);padding:28px 32px;color:#ffffff;">
      <div style="font-size:11px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;opacity:0.9;">
        {html_lib.escape(settings.AGENCY_NAME)} • Custom Technical & Growth Audit
      </div>
      <h1 style="margin:8px 0 4px 0;font-size:22px;font-weight:800;line-height:1.3;">
        Website, Mobile App & Software Audit for {bname}
      </h1>
      <div style="font-size:13px;opacity:0.9;">
        📍 {loc} • Category: {cat} • Audited by {html_lib.escape(settings.SENDER_NAME)}
      </div>
    </div>

    <!-- Main Content Body -->
    <div style="padding:28px 32px;">

      <!-- Personalized Message -->
      <div style="margin-bottom:22px;">
        {body_html_paragraphs}
      </div>

      <!-- Technical Audit Score Bar -->
      <table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;margin-bottom:22px;text-align:center;">
        <tr>
          <td style="padding:14px 8px;border-right:1px solid #e2e8f0;">
            <div style="font-size:11px;color:#64748b;font-weight:600;text-transform:uppercase;">Audit Score</div>
            <div style="font-size:20px;font-weight:800;color:{score_color};margin-top:4px;">{score}/100</div>
          </td>
          <td style="padding:14px 8px;border-right:1px solid #e2e8f0;">
            <div style="font-size:11px;color:#64748b;font-weight:600;text-transform:uppercase;">Response Speed</div>
            <div style="font-size:14px;font-weight:700;color:#1e293b;margin-top:6px;">{speed_txt}</div>
          </td>
          <td style="padding:14px 8px;border-right:1px solid #e2e8f0;">
            <div style="font-size:11px;color:#64748b;font-weight:600;text-transform:uppercase;">Mobile UX</div>
            <div style="font-size:13px;font-weight:700;color:#1e293b;margin-top:6px;">{mobile_txt}</div>
          </td>
          <td style="padding:14px 8px;">
            <div style="font-size:11px;color:#64748b;font-weight:600;text-transform:uppercase;">Direct Ordering</div>
            <div style="font-size:13px;font-weight:700;color:#1e293b;margin-top:6px;">{order_txt}</div>
          </td>
        </tr>
      </table>

      <!-- Live Captured Website Screenshot -->
      {screenshot_section}

      <!-- Section 1: Detailed Website Weaknesses Found -->
      <div style="background:#fff1f2;border:1px solid #fecdd3;border-radius:16px;padding:18px 20px;margin-bottom:20px;">
        <h3 style="margin:0 0 10px 0;font-size:15px;font-weight:800;color:#be123c;">
          🔴 1. Key Bottlenecks & Weaknesses Found on Your Current Website:
        </h3>
        <p style="margin:0 0 12px 0;font-size:13px;color:#881337;">
          Our automated technical & UX audit of <strong>{bname}</strong> identified the following issues that may be costing you daily online customers and direct orders:
        </p>
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:10px;overflow:hidden;border:1px solid #ffe4e6;">
          {issues_rows}
        </table>
      </div>

      <!-- Section 2: How Our Upgrade Will Transform Their Website, App & Software -->
      <div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:16px;padding:18px 20px;margin-bottom:24px;">
        <h3 style="margin:0 0 10px 0;font-size:15px;font-weight:800;color:#047857;">
          🟢 2. How Our Website, Mobile App & Software Upgrade Will Transform Your Business:
        </h3>
        <p style="margin:0 0 12px 0;font-size:13px;color:#065f46;">
          Here is the exact step-by-step improvement plan our engineering team at <strong>{html_lib.escape(settings.AGENCY_NAME)}</strong> can implement for <strong>{bname}</strong>:
        </p>
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:10px;overflow:hidden;border:1px solid #d1fae5;">
          {solutions_rows}
        </table>
        <div style="margin-top:12px;padding:10px 14px;background:#d1fae5;border-radius:8px;color:#065f46;font-size:13px;font-weight:700;">
          📈 Projected Business Impact: {impact}
        </div>
      </div>

      <!-- Call To Action Box -->
      <div style="text-align:center;background:#f8f7fc;border:1px solid #e9d5ff;border-radius:16px;padding:24px 20px;margin-bottom:16px;">
        <div style="font-size:16px;font-weight:800;color:#1e293b;margin-bottom:6px;">
          Want to See Your Free Custom Website & App Prototype?
        </div>
        <p style="margin:0 0 18px 0;font-size:13.5px;color:#64748b;">
          Simply reply to this email with <strong>"YES"</strong> or a convenient time for a quick 10-minute Google Meet demo, and I will share your live custom mockup link right away.
        </p>
        <a href="mailto:{html_lib.escape(settings.GMAIL_ADDRESS)}?subject=Re:%20Website%20Audit%20%26%20Mockup%20for%20{bname}&body=Hi%20Zai%2C%20I%20would%20love%20to%20see%20the%20custom%20mockup%20and%20hop%20on%20a%20quick%2010-minute%20call!"
           style="display:inline-block;background:linear-gradient(135deg,#7c4dff 0%,#ec4899 100%);color:#ffffff;text-decoration:none;font-weight:800;font-size:14px;padding:14px 28px;border-radius:12px;">
          🚀 Request My Free Prototype & 10-Min Demo Call →
        </a>
      </div>

      <!-- Founder Signature Footer -->
      <div style="border-top:1px solid #e2e8f0;padding-top:18px;font-size:13px;color:#475569;line-height:1.6;">
        <strong style="color:#0f172a;font-size:14px;">{html_lib.escape(settings.SENDER_NAME)}</strong><br/>
        {html_lib.escape(settings.AGENCY_NAME)}<br/>
        📧 Direct Email: <a href="mailto:{html_lib.escape(settings.GMAIL_ADDRESS)}" style="color:#7c4dff;text-decoration:none;">{html_lib.escape(settings.GMAIL_ADDRESS)}</a><br/>
        📱 WhatsApp / Direct Call: <a href="https://wa.me/923293246454" style="color:#059669;text-decoration:none;font-weight:600;">+92 329 3246454 (03293246454)</a><br/>
        <span style="font-size:11px;color:#94a3b8;">Custom Websites • Commission-Free Online Ordering • iOS & Android Mobile Apps • AI Software</span>
      </div>

    </div>
  </div>
</body>
</html>"""

    def _send_smtp_sync(
        self,
        to_email: str,
        subject: str,
        body: str,
        lead: Optional[Dict[str, Any]] = None,
         bypass_bounce_guard: bool = False,
    ) -> Tuple[bool, str]:
        """Blocking SMTP send with inline CID screenshot attachment."""
        if not settings.is_gmail_configured():
            return False, "GMAIL_NOT_CONFIGURED"

        if not bypass_bounce_guard and not self._is_deliverable_domain(to_email):
            return False, "GMAIL_BOUNCE_GUARD_SIMULATED"

        # Determine if lead has a captured screenshot file on disk
        screenshot_path: Optional[Path] = None
        if lead:
            report = lead.get("audit_report") or {}
            rel_url = (
                report.get("screenshot_url")
                or report.get("screenshot_desktop_url")
                or lead.get("screenshot_desktop")
                or lead.get("maps_screenshot")
                or ""
            ).lstrip("/")
            if rel_url:
                c1 = settings.SCREENSHOTS_DIR / Path(rel_url).name
                c2 = BASE_DIR / rel_url
                if c1.exists() and c1.is_file():
                    screenshot_path = c1
                elif c2.exists() and c2.is_file():
                    screenshot_path = c2

        msg_root = MIMEMultipart("related")
        msg_root["From"] = f"{settings.SENDER_NAME} <{settings.GMAIL_ADDRESS}>"
        msg_root["To"] = to_email
        msg_root["Subject"] = subject

        msg_alternative = MIMEMultipart("alternative")
        msg_root.attach(msg_alternative)

        # Plain-text fallback
        part_text = MIMEText(body, "plain", "utf-8")
        msg_alternative.attach(part_text)

        # Rich Professional HTML Audit Template
        html_content = self.build_professional_audit_email_html(
            lead=lead,
            body_text=body,
            use_cid_image=bool(screenshot_path),
        )
        part_html = MIMEText(html_content, "html", "utf-8")
        msg_alternative.attach(part_html)

        # Attach inline screenshot image if present
        if screenshot_path and screenshot_path.exists():
            try:
                img_bytes = screenshot_path.read_bytes()
                mime_img = MIMEImage(img_bytes, _subtype="png")
                mime_img.add_header("Content-ID", "<website_screenshot>")
                mime_img.add_header(
                    "Content-Disposition",
                    "inline",
                    filename=f"{lead.get('business_name', 'website')}_audit.png",
                )
                msg_root.attach(mime_img)
            except Exception:
                pass

        try:
            app_password_clean = settings.GMAIL_APP_PASSWORD.replace(" ", "")
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(settings.GMAIL_ADDRESS, app_password_clean)
                server.sendmail(settings.GMAIL_ADDRESS, [to_email], msg_root.as_string())
            return True, "SENT"
        except Exception as exc:
            return False, str(exc)

    async def send_email(
        self,
        lead_id: int,
        to_email: str,
        subject: str,
        body: str,
        is_reply: bool = False,
    ) -> Dict[str, Any]:
        """Send an outreach or autonomous reply email (with Audit HTML + Screenshot) and log it in SQLite."""
        if not to_email or "@" not in to_email:
            return {"ok": False, "status": "SKIPPED", "error": "No valid email address"}

        if not is_reply:
            counts = db.get_today_outreach_counts()
            if counts["emails_today"] >= settings.DAILY_EMAIL_LIMIT:
                db.log_activity(
                    "WARN",
                    "EMAIL",
                    f"Daily email limit ({settings.DAILY_EMAIL_LIMIT}) reached. Skipping email to {to_email}.",
                )
                return {"ok": False, "status": "LIMIT_REACHED", "error": "Daily email limit reached"}

        lead_obj = db.get_lead_by_id(lead_id) if (lead_id > 0 and not is_reply) else None

        # Ensure screenshot exists before sending outreach email
        if lead_obj:
            report = lead_obj.get("audit_report") or {}
            if not report.get("screenshot_url"):
                from workers.website_auditor import website_auditor

                lead_obj = await website_auditor.audit_lead_and_prepare_outreach(lead_obj)

        ok, info = await asyncio.to_thread(
            self._send_smtp_sync, to_email, subject, body, lead_obj, False
        )

        if ok:
            if not is_reply and lead_id > 0:
                db.record_outreach(
                    lead_id=lead_id,
                    channel="EMAIL",
                    recipient=to_email,
                    subject=subject,
                    message_body=body,
                    delivery_status="SENT",
                )
            db.log_activity(
                "SUCCESS",
                "EMAIL",
                f"Professional HTML Audit Email + Screenshot sent via Gmail SMTP to {to_email}",
            )
            return {"ok": True, "status": "SENT"}

        if info in ("GMAIL_NOT_CONFIGURED", "GMAIL_BOUNCE_GUARD_SIMULATED"):
            reason = (
                "Bounce Guard: Demo/Unverified domain simulated to protect Gmail reputation"
                if info == "GMAIL_BOUNCE_GUARD_SIMULATED"
                else "Simulated (Configure Gmail App Password in .env)"
            )
            if not is_reply and lead_id > 0:
                db.record_outreach(
                    lead_id=lead_id,
                    channel="EMAIL",
                    recipient=to_email,
                    subject=subject,
                    message_body=body,
                    delivery_status="SIMULATED",
                    error_message=reason,
                )
            db.log_activity("INFO", "EMAIL", f"[SAFE SIMULATED] {to_email} ({reason})")
            return {"ok": True, "status": "SIMULATED"}

        if not is_reply and lead_id > 0:
            db.record_outreach(
                lead_id=lead_id,
                channel="EMAIL",
                recipient=to_email,
                subject=subject,
                message_body=body,
                delivery_status="FAILED",
                error_message=info,
            )
        db.log_activity("ERROR", "EMAIL", f"Gmail SMTP error for {to_email}: {info}")
        return {"ok": False, "status": "FAILED", "error": info}

    async def send_raw_notification_email(self, to_email: str, subject: str, body: str) -> bool:
        """Used for sending EOD Summary Reports or Hot Lead Alerts to the Agency Owner."""
        if not settings.is_gmail_configured() or not to_email:
            return False
        ok, _ = await asyncio.to_thread(self._send_smtp_sync, to_email, subject, body, None, True)
        return ok

    def build_owner_lead_report_html(
        self,
        lead: Dict[str, Any],
        has_desktop: bool = False,
        has_mobile: bool = False,
        has_maps: bool = False,
    ) -> str:
        """Executive HTML Audit Report template dispatched to MY_PERSONAL_EMAIL."""
        bname = html_lib.escape(lead.get("business_name") or "Valued Business")
        cat = html_lib.escape(lead.get("category") or "Local Business")
        loc = html_lib.escape(lead.get("location") or "")
        addr = html_lib.escape(lead.get("address") or "Not listed on Google Maps")
        phone = html_lib.escape(lead.get("phone") or "Not listed")
        raw_email = (lead.get("email") or "").strip()
        email_addr = html_lib.escape(raw_email or "Not found on website (Use WhatsApp/Phone)")
        client_subject = lead.get("draft_email_subject") or f"2 quick conversion ideas for {lead.get('business_name', 'your')}'s website"
        website = lead.get("website") or ""
        place_url = lead.get("place_url") or ""
        rating = lead.get("rating") or 0.0
        reviews = lead.get("reviews_count") or 0
        priority = lead.get("priority") or "HIGH"
        score = int(lead.get("audit_score") or 50)
        report = lead.get("audit_report") or {}
        tech = report.get("technical_scan") or {}

        issues = report.get("issues_found") or tech.get("detected_issues") or [
            "Missing direct commission-free online ordering / appointment booking system",
            "Slow mobile page load speed",
            "Missing instant WhatsApp lead capture widget",
        ]
        solutions = report.get("recommended_solutions") or [
            f"Build a modern mobile-first website for {bname} with <1.5s load time",
            "Integrate direct online booking & ordering with zero commission",
            "Deploy custom iOS/Android mobile app & automated AI customer retention",
        ]
        impact = html_lib.escape(
            report.get("estimated_revenue_impact")
            or "+35% to +45% increase in direct orders & bookings"
        )

        load_ms = tech.get("load_time_ms") or 0
        speed_txt = f"{load_ms} ms" if load_ms > 0 else ("No Site" if not website else "Checked")
        mobile_txt = "✅ Responsive" if tech.get("is_mobile_friendly") else "❌ Needs Mobile UX"
        order_txt = "✅ Active" if tech.get("has_online_ordering_or_booking") else "❌ Missing System"
        score_color = "#e11d48" if score < 55 else ("#d97706" if score < 75 else "#059669")

        web_link_html = (
            f'<a href="{html_lib.escape(website)}" target="_blank" style="color:#6366f1;text-decoration:underline;font-weight:600;">{html_lib.escape(website)}</a>'
            if website
            else '<span style="color:#e11d48;font-weight:700;">⚠️ NO WEBSITE FOUND — HIGH PRIORITY CLIENT</span>'
        )
        maps_link_html = (
            f'<a href="{html_lib.escape(place_url)}" target="_blank" style="color:#6366f1;text-decoration:underline;">View Real Google Maps Listing ↗</a>'
            if place_url
            else '<span style="color:#64748b;">Not available</span>'
        )

        issues_html = "".join(
            [
                f'<li style="margin-bottom:8px;color:#9f1239;font-size:13.5px;line-height:1.5;"><strong>⚠️ Defect #{i+1}:</strong> {html_lib.escape(str(iss))}</li>'
                for i, iss in enumerate(issues)
            ]
        )
        solutions_html = "".join(
            [
                f'<li style="margin-bottom:8px;color:#065f46;font-size:13.5px;line-height:1.5;"><strong>✅ Upgrade #{i+1}:</strong> {html_lib.escape(str(sol))}</li>'
                for i, sol in enumerate(solutions)
            ]
        )

        # Dual Viewport Screenshots Table (Email Client Compatible)
        shot_sections = []
        if has_desktop:
            shot_sections.append(
                """
                <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:16px;background:#0f172a;border-radius:12px;overflow:hidden;border:1px solid #334155;">
                  <tr>
                    <td style="padding:10px 16px;background:#1e293b;color:#38bdf8;font-size:12px;font-weight:700;letter-spacing:0.5px;">
                      💻 DESKTOP VIEWPORT AUDIT SCREENSHOT (1280x800)
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:14px;text-align:center;background:#0f172a;">
                      <img src="cid:shot_desktop" alt="Desktop Screenshot" style="width:100%;max-width:620px;height:auto;border-radius:8px;display:block;margin:0 auto;border:1px solid #1e293b;" />
                    </td>
                  </tr>
                </table>
                """
            )
        if has_mobile:
            shot_sections.append(
                """
                <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:16px;background:#0f172a;border-radius:12px;overflow:hidden;border:1px solid #334155;">
                  <tr>
                    <td style="padding:10px 16px;background:#1e293b;color:#38bdf8;font-size:12px;font-weight:700;letter-spacing:0.5px;">
                      📱 MOBILE VIEWPORT AUDIT SCREENSHOT (390x844)
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:14px;text-align:center;background:#0f172a;">
                      <img src="cid:shot_mobile" alt="Mobile Screenshot" style="width:100%;max-width:320px;height:auto;border-radius:8px;display:block;margin:0 auto;border:1px solid #1e293b;" />
                    </td>
                  </tr>
                </table>
                """
            )
        if has_maps and not (has_desktop or has_mobile):
            shot_sections.append(
                """
                <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:16px;background:#0f172a;border-radius:12px;overflow:hidden;border:1px solid #334155;">
                  <tr>
                    <td style="padding:10px 16px;background:#1e293b;color:#f43f5e;font-size:12px;font-weight:700;letter-spacing:0.5px;">
                      📍 GOOGLE MAPS LISTING AUDIT SCREENSHOT (NO WEBSITE FOUND)
                    </td>
                  </tr>
                  <tr>
                    <td style="padding:14px;text-align:center;background:#0f172a;">
                      <img src="cid:shot_maps" alt="Maps Screenshot" style="width:100%;max-width:620px;height:auto;border-radius:8px;display:block;margin:0 auto;border:1px solid #1e293b;" />
                    </td>
                  </tr>
                </table>
                """
            )
        shots_grid = "".join(shot_sections) if shot_sections else ""

        if raw_email:
            delivery_status_banner = f"""
            <div style="background:#ecfdf5;border:1.5px solid #10b981;border-radius:14px;padding:16px 20px;margin-bottom:22px;box-shadow:0 4px 12px rgba(16,185,129,0.08);">
              <div style="display:flex;align-items:center;font-size:13px;font-weight:800;color:#065f46;margin-bottom:6px;">
                <span style="font-size:18px;margin-right:8px;">✅</span> CLIENT OUTREACH DISPATCHED DIRECTLY TO CLIENT
              </div>
              <div style="font-size:13px;color:#047857;line-height:1.6;">
                • <strong>Client Recipient:</strong> <span style="font-family:monospace;background:#d1fae5;padding:2px 8px;border-radius:4px;font-weight:700;color:#065f46;">{email_addr}</span><br/>
                • <strong>Pitch Subject Delivered to Client:</strong> <span style="color:#0f172a;font-weight:700;">"{html_lib.escape(client_subject)}"</span><br/>
                • <strong>Verify in Gmail:</strong> Open your Gmail <strong>"Sent"</strong> (Bheje Gaye) folder to review the actual cold pitch delivered.<br/>
                <div style="margin-top:8px;padding:6px 12px;background:#ffffff;border-radius:6px;border:1px solid #a7f3d0;font-size:11.5px;color:#0f766e;">
                  ℹ️ <em>This email in your inbox is your private internal intelligence briefing with technical score & screenshot attachments.</em>
                </div>
              </div>
            </div>
            """
        else:
            delivery_status_banner = f"""
            <div style="background:#fffbeb;border:1.5px solid #f59e0b;border-radius:14px;padding:16px 20px;margin-bottom:22px;box-shadow:0 4px 12px rgba(245,158,11,0.08);">
              <div style="display:flex;align-items:center;font-size:13px;font-weight:800;color:#92400e;margin-bottom:6px;">
                <span style="font-size:18px;margin-right:8px;">⚠️</span> DIRECT CALL / WHATSAPP PRIORITY (NO EMAIL ON WEBSITE)
              </div>
              <div style="font-size:13px;color:#78350f;line-height:1.6;">
                • <strong>Business Phone:</strong> <a href="tel:{phone}" style="color:#b45309;font-weight:700;">{phone}</a><br/>
                • <strong>Action Required:</strong> No public email was detected on the website. Use the audit report & weaknesses below to pitch them directly via phone call or WhatsApp.
              </div>
            </div>
            """

        return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
</head>
<body style="margin:0;padding:0;background-color:#0f172a;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1e293b;">
  <div style="max-width:720px;margin:20px auto;background-color:#ffffff;border-radius:18px;overflow:hidden;box-shadow:0 16px 40px rgba(0,0,0,0.3);border:1px solid #334155;">

    <div style="background:linear-gradient(135deg,#0f172a 0%,#1e1b4b 60%,#4338ca 100%);padding:26px 30px;color:#ffffff;border-bottom:3px solid #6366f1;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <span style="font-size:11px;font-weight:800;letter-spacing:1.5px;text-transform:uppercase;color:#818cf8;">
          {html_lib.escape(settings.AGENCY_NAME.upper())} • PRIVATE CLIENT INTELLIGENCE DOSSIER
        </span>
        <span style="background:#e11d48;color:#ffffff;font-size:11px;font-weight:800;padding:4px 12px;border-radius:999px;">
          {priority}
        </span>
      </div>
      <h1 style="margin:10px 0 4px 0;font-size:24px;font-weight:800;color:#ffffff;">
        {bname}
      </h1>
      <div style="font-size:13px;color:#cbd5e1;">
        📍 {loc} • Category: {cat} • ★ {rating} ({reviews} Google Reviews)
      </div>
    </div>

    <div style="padding:28px 30px;">

      {delivery_status_banner}

      <!-- SECTION 1: AUTHENTIC BUSINESS DETAILS -->
      <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;padding:20px;margin-bottom:20px;">
        <h3 style="margin:0 0 14px 0;font-size:14px;font-weight:800;color:#0f172a;text-transform:uppercase;letter-spacing:0.8px;">
          🏢 1. Authentic Business Contact & Location
        </h3>
        <table width="100%" cellpadding="6" cellspacing="0" style="font-size:13px;color:#334155;">
          <tr>
            <td width="30%" style="font-weight:700;color:#64748b;border-bottom:1px solid #e2e8f0;">Business Name:</td>
            <td style="font-weight:800;color:#0f172a;border-bottom:1px solid #e2e8f0;">{bname}</td>
          </tr>
          <tr>
            <td style="font-weight:700;color:#64748b;border-bottom:1px solid #e2e8f0;">Category & City:</td>
            <td style="border-bottom:1px solid #e2e8f0;">{cat} in {loc}</td>
          </tr>
          <tr>
            <td style="font-weight:700;color:#64748b;border-bottom:1px solid #e2e8f0;">Exact Address:</td>
            <td style="border-bottom:1px solid #e2e8f0;">{addr}</td>
          </tr>
          <tr>
            <td style="font-weight:700;color:#64748b;border-bottom:1px solid #e2e8f0;">Phone Number:</td>
            <td style="border-bottom:1px solid #e2e8f0;"><a href="tel:{phone}" style="color:#0f172a;font-weight:700;text-decoration:none;">📞 {phone}</a></td>
          </tr>
          <tr>
            <td style="font-weight:700;color:#64748b;border-bottom:1px solid #e2e8f0;">Scraped Email:</td>
            <td style="border-bottom:1px solid #e2e8f0;"><a href="mailto:{email_addr}" style="color:#6366f1;font-weight:700;">✉️ {email_addr}</a></td>
          </tr>
          <tr>
            <td style="font-weight:700;color:#64748b;border-bottom:1px solid #e2e8f0;">Official Website:</td>
            <td style="border-bottom:1px solid #e2e8f0;">{web_link_html}</td>
          </tr>
          <tr>
            <td style="font-weight:700;color:#64748b;">Google Maps URL:</td>
            <td>{maps_link_html}</td>
          </tr>
        </table>
      </div>

      <!-- SECTION 2: AI TECHNICAL SCORE BAR -->
      <table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;border:1px solid #cbd5e1;border-radius:14px;margin-bottom:20px;text-align:center;">
        <tr>
          <td style="padding:14px 8px;border-right:1px solid #cbd5e1;">
            <div style="font-size:11px;color:#64748b;font-weight:700;text-transform:uppercase;">Audit Score</div>
            <div style="font-size:22px;font-weight:900;color:{score_color};margin-top:2px;">{score}/100</div>
          </td>
          <td style="padding:14px 8px;border-right:1px solid #cbd5e1;">
            <div style="font-size:11px;color:#64748b;font-weight:700;text-transform:uppercase;">Speed</div>
            <div style="font-size:13px;font-weight:800;color:#0f172a;margin-top:4px;">{speed_txt}</div>
          </td>
          <td style="padding:14px 8px;border-right:1px solid #cbd5e1;">
            <div style="font-size:11px;color:#64748b;font-weight:700;text-transform:uppercase;">Mobile UX</div>
            <div style="font-size:12px;font-weight:800;color:#0f172a;margin-top:4px;">{mobile_txt}</div>
          </td>
          <td style="padding:14px 8px;">
            <div style="font-size:11px;color:#64748b;font-weight:700;text-transform:uppercase;">Direct Ordering</div>
            <div style="font-size:12px;font-weight:800;color:#0f172a;margin-top:4px;">{order_txt}</div>
          </td>
        </tr>
      </table>

      <!-- SECTION 3: WEAKNESSES IDENTIFIED -->
      <div style="background:#fff1f2;border:1px solid #fecdd3;border-radius:14px;padding:18px 20px;margin-bottom:18px;">
        <h4 style="margin:0 0 10px 0;font-size:14px;font-weight:800;color:#be123c;">
          🔴 Key Digital Weaknesses & Gaps Found (What is Broken):
        </h4>
        <ul style="margin:0;padding-left:18px;">{issues_html}</ul>
      </div>

      <!-- SECTION 4: RECOMMENDED SOLUTIONS & PITCH -->
      <div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:14px;padding:18px 20px;margin-bottom:20px;">
        <h4 style="margin:0 0 10px 0;font-size:14px;font-weight:800;color:#047857;">
          🟢 Recommended Agency Improvements (How We Upgrade Them):
        </h4>
        <ul style="margin:0;padding-left:18px;">{solutions_html}</ul>
        <div style="margin-top:12px;padding:10px 14px;background:#d1fae5;border-radius:8px;color:#065f46;font-size:13px;font-weight:800;">
          📈 Projected Revenue Impact: {impact}
        </div>
      </div>

      <!-- SECTION 5: SCREENSHOT ATTACHMENTS PREVIEW -->
      <div style="background:#0f172a;border-radius:14px;padding:18px 20px;margin-bottom:20px;color:#ffffff;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <h4 style="margin:0;font-size:13px;font-weight:800;color:#38bdf8;text-transform:uppercase;letter-spacing:0.8px;">
            📸 Live Captured Screenshots (Attached as Full-Res PNG)
          </h4>
          <span style="font-size:11px;color:#94a3b8;">📎 Attached to this email</span>
        </div>
        <p style="margin:0 0 12px 0;font-size:12px;color:#94a3b8;">
          The full-resolution desktop and mobile viewport screenshots are attached directly to this email so you can inspect them offline or forward them to the client.
        </p>
        {shots_grid}
      </div>

      <div style="border-top:1px solid #e2e8f0;padding-top:14px;font-size:12px;color:#64748b;text-align:center;">
        Generated Autonomously by <strong>{html_lib.escape(settings.AGENCY_NAME)}</strong> • Dispatched to {html_lib.escape(settings.MY_PERSONAL_EMAIL)}
      </div>

    </div>
  </div>
</body>
</html>"""

    def _send_lead_audit_report_to_owner_sync(
        self,
        lead: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """
        Send the full Lead Audit Dossier to MY_PERSONAL_EMAIL via Gmail SMTP with:
        - Authentic details
        - AI Audit breakdown
        - Actual PNG attachments (desktop, mobile, maps)
        """
        if not settings.is_gmail_configured():
            return False, "GMAIL_NOT_CONFIGURED"

        owner_email = settings.MY_PERSONAL_EMAIL
        if not owner_email:
            return False, "NO_OWNER_EMAIL"

        bname = lead.get("business_name", "Lead")
        cat = lead.get("category", "Business")
        loc = lead.get("location", "")
        score = lead.get("audit_score", 50)
        subject = f"🎯 New Client Dossier: {bname} ({loc}) • Audit Score: {score}/100"

        def _resolve_shot(val: str) -> Optional[Path]:
            if not val:
                return None
            val = val.strip().lstrip("/")
            candidates = [
                settings.SCREENSHOTS_DIR / Path(val).name,
                BASE_DIR / val,
                settings.SCREENSHOTS_DIR / val,
            ]
            for c in candidates:
                if c.exists() and c.is_file():
                    return c
            return None

        report = lead.get("audit_report") or {}
        desktop_img = _resolve_shot(
            lead.get("screenshot_desktop") or report.get("screenshot_desktop_url") or report.get("screenshot_url")
        )
        mobile_img = _resolve_shot(lead.get("screenshot_mobile") or report.get("screenshot_mobile_url"))
        maps_img = _resolve_shot(lead.get("maps_screenshot") or report.get("maps_screenshot_url"))

        msg_root = MIMEMultipart("mixed")
        msg_root["From"] = f"{settings.SENDER_NAME} <{settings.GMAIL_ADDRESS}>"
        msg_root["To"] = owner_email
        msg_root["Subject"] = subject

        msg_alternative = MIMEMultipart("alternative")
        msg_root.attach(msg_alternative)

        client_email = (lead.get("email") or "").strip()
        client_subject = lead.get("draft_email_subject") or f"2 quick conversion ideas for {bname}'s website"

        plain_text = (
            f"{settings.AGENCY_NAME.upper()} - CLIENT INTELLIGENCE DOSSIER\n"
            f"Business: {bname}\n"
            f"Category: {cat} | Location: {loc}\n"
            f"Client Outreach Recipient: {client_email or 'No public email found (Use Phone/WhatsApp)'}\n"
            f"Client Pitch Subject: {client_subject}\n"
            f"Address: {lead.get('address')}\n"
            f"Phone: {lead.get('phone')}\n"
            f"Website: {lead.get('website') or 'NO WEBSITE'}\n"
            f"Google Maps: {lead.get('place_url')}\n"
            f"Audit Score: {score}/100\n\n"
            f"Full visual report and screenshots are attached.\n"
        )
        msg_alternative.attach(MIMEText(plain_text, "plain", "utf-8"))

        html_body = self.build_owner_lead_report_html(
            lead=lead,
            has_desktop=bool(desktop_img),
            has_mobile=bool(mobile_img),
            has_maps=bool(maps_img),
        )
        msg_alternative.attach(MIMEText(html_body, "html", "utf-8"))

        slug = re.sub(r"[^a-z0-9]+", "_", bname.lower()).strip("_")[:40] or "lead"
        attached_count = 0

        if desktop_img and desktop_img.exists():
            try:
                mime_d = MIMEImage(desktop_img.read_bytes(), _subtype="png")
                mime_d.add_header("Content-ID", "<shot_desktop>")
                mime_d.add_header("Content-Disposition", "inline", filename=f"{slug}_desktop.png")
                msg_root.attach(mime_d)
                attached_count += 1
            except Exception:
                pass

        if mobile_img and mobile_img.exists():
            try:
                mime_m = MIMEImage(mobile_img.read_bytes(), _subtype="png")
                mime_m.add_header("Content-ID", "<shot_mobile>")
                mime_m.add_header("Content-Disposition", "inline", filename=f"{slug}_mobile.png")
                msg_root.attach(mime_m)
                attached_count += 1
            except Exception:
                pass

        if maps_img and maps_img.exists():
            try:
                mime_map = MIMEImage(maps_img.read_bytes(), _subtype="png")
                mime_map.add_header("Content-ID", "<shot_maps>")
                mime_map.add_header("Content-Disposition", "inline", filename=f"{slug}_maps.png")
                msg_root.attach(mime_map)
                attached_count += 1
            except Exception:
                pass

        try:
            app_password_clean = settings.GMAIL_APP_PASSWORD.replace(" ", "")
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=35) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(settings.GMAIL_ADDRESS, app_password_clean)
                server.sendmail(settings.GMAIL_ADDRESS, [owner_email], msg_root.as_string())
            return True, f"SENT_{attached_count}_ATTACHMENTS"
        except Exception as exc:
            return False, str(exc)

    async def send_lead_audit_report_to_owner(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Async dispatch of lead audit dossier + screenshots to agency owner's personal inbox."""
        if not settings.is_gmail_configured():
            return {"ok": False, "error": "GMAIL_NOT_CONFIGURED"}
        if not settings.MY_PERSONAL_EMAIL:
            return {"ok": False, "error": "NO_OWNER_EMAIL"}

        bname = lead.get("business_name", "Lead")
        ok, info = await asyncio.to_thread(self._send_lead_audit_report_to_owner_sync, lead)
        if ok:
            db.mark_owner_report_sent(lead.get("id", 0))
            db.log_activity(
                "SUCCESS",
                "EMAIL",
                f"Owner Lead Report + Screenshots sent to {settings.MY_PERSONAL_EMAIL} for '{bname}' ({info})",
            )
            return {"ok": True, "status": info}
        else:
            db.log_activity(
                "ERROR",
                "EMAIL",
                f"Failed to send Owner Lead Report to {settings.MY_PERSONAL_EMAIL} for '{bname}': {info}",
            )
            return {"ok": False, "error": info}

    # -------------------------------------------------------------------------
    # GMAIL IMAP CLIENT REPLY READER (imap.gmail.com:993)
    # -------------------------------------------------------------------------
    @staticmethod
    def _decode_mime_words(header_val: str) -> str:
        if not header_val:
            return ""
        decoded_parts = decode_header(header_val)
        out = []
        for content, enc in decoded_parts:
            if isinstance(content, bytes):
                out.append(content.decode(enc or "utf-8", errors="ignore"))
            else:
                out.append(str(content))
        return "".join(out)

    @staticmethod
    def _strip_quoted_reply(text: str) -> str:
        lines = text.splitlines()
        cleaned_lines = []
        for line in lines:
            if re.match(r"^On .* wrote:$", line.strip()):
                break
            if line.strip().startswith("-----Original Message-----"):
                break
            if line.strip().startswith(">"):
                continue
            cleaned_lines.append(line)
        result = "\n".join(cleaned_lines).strip()
        return result or text.strip()

    def _fetch_imap_replies_sync(self) -> List[Dict[str, Any]]:
        if not settings.is_gmail_configured():
            return []

        replies: List[Dict[str, Any]] = []
        app_password_clean = settings.GMAIL_APP_PASSWORD.replace(" ", "")

        try:
            mail = imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT)
            mail.login(settings.GMAIL_ADDRESS, app_password_clean)
            mail.select("INBOX")

            since_date = (datetime.now() - timedelta(days=3)).strftime("%d-%b-%Y")
            status, data = mail.search(None, f'(SINCE "{since_date}")')
            if status != "OK" or not data or not data[0]:
                mail.logout()
                return []

            email_ids = data[0].split()[-40:]
            for e_id in reversed(email_ids):
                res, msg_data = mail.fetch(e_id, "(RFC822)")
                if res != "OK" or not msg_data:
                    continue

                raw_email = msg_data[0][1]
                if not isinstance(raw_email, bytes):
                    continue

                msg = email.message_from_bytes(raw_email)
                msg_id = (msg.get("Message-ID") or "").strip()
                if msg_id and db.is_message_processed(msg_id):
                    continue

                from_header = self._decode_mime_words(msg.get("From", ""))
                _, sender_email = parseaddr(from_header)
                sender_email = (sender_email or "").strip().lower()

                if not sender_email or sender_email == settings.GMAIL_ADDRESS.lower():
                    continue

                matched_lead = db.find_lead_by_contact(sender_email)
                if not matched_lead:
                    continue

                subject = self._decode_mime_words(msg.get("Subject", ""))
                body_text = ""

                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        content_disp = str(part.get("Content-Disposition"))
                        if content_type == "text/plain" and "attachment" not in content_disp:
                            payload = part.get_payload(decode=True)
                            if payload:
                                body_text = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
                                break
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body_text = payload.decode(msg.get_content_charset() or "utf-8", errors="ignore")

                clean_reply = self._strip_quoted_reply(body_text)
                if not clean_reply:
                    continue

                replies.append(
                    {
                        "lead": matched_lead,
                        "sender_email": sender_email,
                        "subject": subject,
                        "message_text": clean_reply,
                        "external_msg_id": msg_id or f"imap_{sender_email}_{len(clean_reply)}",
                    }
                )

            mail.logout()
        except Exception as exc:
            db.log_activity("WARN", "EMAIL", f"Gmail IMAP check warning: {exc}")

        return replies

    async def check_incoming_replies(self) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._fetch_imap_replies_sync)


email_worker = GmailWorker()
