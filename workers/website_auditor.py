from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, unquote_plus

import httpx
from bs4 import BeautifulSoup

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    async_playwright = None
    PLAYWRIGHT_AVAILABLE = False

from config import settings
from database import db
from workers.ai_engine import ai_engine
from workers.maps_scraper import (
    DESKTOP_USER_AGENT,
    MOBILE_USER_AGENT,
    EMAIL_REGEX,
    clean_emails,
    decode_cloudflare_email,
    launch_browser,
    make_slug,
    maps_scraper,
)


class WebsiteAuditor:
    """
    Deep Technical & UX Website Auditor + Live Dual Playwright Screenshot Capture (Desktop + Mobile)
    + Gemini/Groq AI Gap Analysis Engine.
    """

    async def extract_emails_from_page(self, page, base_url: str) -> List[str]:
        """Extract authentic emails from live Playwright DOM + /contact page."""
        emails: Set[str] = set()
        try:
            content = await page.content()
            emails.update(EMAIL_REGEX.findall(content))

            # mailto: links
            links = await page.eval_on_selector_all(
                'a[href^="mailto:"]',
                "elements => elements.map(el => el.getAttribute('href'))",
            )
            for href in links:
                if href and href.lower().startswith("mailto:"):
                    emails.add(href[7:])

            # Cloudflare data-cfemail
            cf_elements = await page.eval_on_selector_all(
                "[data-cfemail]",
                "elements => elements.map(el => el.getAttribute('data-cfemail'))",
            )
            for hex_str in cf_elements:
                decoded = decode_cloudflare_email(hex_str)
                if decoded:
                    emails.add(decoded)
        except Exception:
            pass

        return clean_emails(emails)

    async def capture_website_screenshots(
        self, lead: Dict[str, Any], tech_scan: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        Capture both Desktop (1280x800) and Mobile (390x844) viewport screenshots of the client's website,
        or preserve the Google Maps listing screenshot / visual diagnostic snapshot if the business has no website.
        """
        lead_id = lead.get("id", 0)
        bname = lead.get("business_name", "Local Business")
        loc = lead.get("location", "")
        rating = lead.get("rating") or 4.7
        slug = f"lead_{lead_id}_{make_slug(bname)}"

        desktop_file = f"{slug}_desktop.png"
        mobile_file = f"{slug}_mobile.png"
        maps_file = f"{slug}_maps.png"

        desktop_path = settings.SCREENSHOTS_DIR / desktop_file
        mobile_path = settings.SCREENSHOTS_DIR / mobile_file
        maps_path = settings.SCREENSHOTS_DIR / maps_file

        results = {
            "screenshot_desktop": "",
            "screenshot_mobile": "",
            "maps_screenshot": lead.get("maps_screenshot") or "",
            "primary_screenshot": "",
            "extracted_email": "",
        }

        if not PLAYWRIGHT_AVAILABLE:
            return results

        website_url = (lead.get("website") or "").strip()

        try:
            async with async_playwright() as p:
                browser = await launch_browser(p, headless=settings.HEADLESS_SCRAPER)
                if not browser:
                    return results

                # CASE 1: Business has an active website URL
                if website_url and tech_scan.get("reachable", True):
                    url = website_url if website_url.startswith(("http://", "https://")) else "https://" + website_url

                    # --- 1. DESKTOP VIEWPORT SCREENSHOT (1280x800) ---
                    try:
                        ctx_desktop = await browser.new_context(
                            viewport={"width": 1280, "height": 800},
                            user_agent=DESKTOP_USER_AGENT,
                        )
                        page_d = await ctx_desktop.new_page()
                        await page_d.goto(url, wait_until="domcontentloaded", timeout=25000)
                        await page_d.wait_for_timeout(2000)
                        await page_d.screenshot(path=str(desktop_path), full_page=False)
                        results["screenshot_desktop"] = f"/screenshots/{desktop_file}"
                        results["primary_screenshot"] = results["screenshot_desktop"]

                        # Scrape email from live page if lead doesn't have one
                        if not lead.get("email"):
                            found = await self.extract_emails_from_page(page_d, url)
                            if found:
                                results["extracted_email"] = found[0]
                                db.log_activity("SUCCESS", "AUDITOR", f"Discovered website email for '{bname}': {found[0]}")

                        await ctx_desktop.close()
                    except Exception as e:
                        db.log_activity("WARN", "AUDITOR", f"Desktop screenshot warning for '{bname}': {e}")

                    # --- 2. MOBILE VIEWPORT SCREENSHOT (390x844, iPhone 14-style) ---
                    try:
                        ctx_mobile = await browser.new_context(
                            viewport={"width": 390, "height": 844},
                            user_agent=MOBILE_USER_AGENT,
                            is_mobile=True,
                            has_touch=True,
                        )
                        page_m = await ctx_mobile.new_page()
                        await page_m.goto(url, wait_until="domcontentloaded", timeout=25000)
                        await page_m.wait_for_timeout(2000)
                        await page_m.screenshot(path=str(mobile_path), full_page=False)
                        results["screenshot_mobile"] = f"/screenshots/{mobile_file}"

                        # If email wasn't found on desktop, check mobile context
                        if not results["extracted_email"] and not lead.get("email"):
                            found_m = await self.extract_emails_from_page(page_m, url)
                            if found_m:
                                results["extracted_email"] = found_m[0]

                        await ctx_mobile.close()
                    except Exception as e:
                        db.log_activity("WARN", "AUDITOR", f"Mobile screenshot warning for '{bname}': {e}")

                    # Deep multi-page crawler fallback if still no email
                    if not results["extracted_email"] and not lead.get("email") and url:
                        try:
                            deep_email = await maps_scraper.extract_email_from_website(url)
                            if deep_email:
                                results["extracted_email"] = deep_email
                                db.log_activity("SUCCESS", "AUDITOR", f"Discovered deep crawl email for '{bname}': {deep_email}")
                        except Exception:
                            pass

                    await browser.close()

                    if results["screenshot_desktop"] or results["screenshot_mobile"]:
                        db.log_activity(
                            "SUCCESS",
                            "AUDITOR",
                            f"Live Website Screenshots captured for '{bname}' -> Desktop: screenshots/{desktop_file} | Mobile: screenshots/{mobile_file}",
                        )
                        return results

                # CASE 2: Business has NO website (or website failed to load)
                # If we already have a Google Maps screenshot from maps_scraper, reuse it
                if lead.get("maps_screenshot"):
                    results["maps_screenshot"] = lead.get("maps_screenshot")
                    results["primary_screenshot"] = lead.get("maps_screenshot")
                    await browser.close()
                    return results

                # Otherwise render a high-impact Digital Audit Snapshot Card
                ctx_diag = await browser.new_context(viewport={"width": 1280, "height": 760})
                page_diag = await ctx_diag.new_page()

                issues_html = "".join(
                    [
                        f"<li style='margin-bottom:8px;color:#fda4af;'>⚠️ {i}</li>"
                        for i in (tech_scan.get("detected_issues") or [
                            "No official website or mobile app found on Google Maps",
                            "Missing direct commission-free online ordering / appointment booking system",
                            "Invisible on organic Google Search outside Maps pack",
                        ])[:4]
                    ]
                )

                diagnostic_html = f"""
                <!DOCTYPE html>
                <html>
                <body style="margin:0;padding:48px;background:linear-gradient(135deg,#0f172a,#1e1b4b);color:#fff;font-family:Segoe UI,Arial,sans-serif;height:660px;box-sizing:border-box;">
                  <div style="border:2px solid rgba(244,63,94,0.5);background:rgba(15,23,42,0.85);border-radius:24px;padding:40px;max-width:1100px;margin:0 auto;">
                    <span style="background:#e11d48;color:#fff;padding:6px 16px;border-radius:999px;font-size:13px;font-weight:700;letter-spacing:1px;">
                      HIGH PRIORITY LEAD • NO WEBSITE FOUND • SCORE: {tech_scan.get('technical_score', 15)}/100
                    </span>
                    <h1 style="font-size:38px;margin:20px 0 8px 0;">{bname}</h1>
                    <p style="font-size:18px;color:#94a3b8;margin:0 0 28px 0;">📍 {loc} • ★ {rating} Google Rating • No Official Website Attached</p>
                    <div style="background:rgba(244,63,94,0.12);border-left:4px solid #f43f5e;padding:20px 24px;border-radius:12px;">
                      <h3 style="margin:0 0 12px 0;color:#fecdd3;font-size:18px;">Critical Digital Gaps Costing You Customers Daily:</h3>
                      <ul style="margin:0;padding-left:20px;font-size:16px;line-height:1.6;">{issues_html}</ul>
                    </div>
                    <div style="margin-top:28px;padding:18px 24px;background:rgba(16,185,129,0.15);border:1px solid rgba(16,185,129,0.4);border-radius:12px;color:#a7f3d0;font-size:16px;font-weight:600;">
                      ✅ Recommended Action: Launch a Modern Mobile-First Website, Direct 0% Commission Ordering & Custom App with {settings.AGENCY_NAME}.
                    </div>
                  </div>
                </body>
                </html>
                """
                await page_diag.set_content(diagnostic_html)
                await page_diag.screenshot(path=str(maps_path), full_page=False)
                await browser.close()

                results["maps_screenshot"] = f"/screenshots/{maps_file}"
                results["primary_screenshot"] = results["maps_screenshot"]
                db.log_activity("INFO", "AUDITOR", f"No website for '{bname}' -> Saved Digital Audit Card: screenshots/{maps_file}")
                return results

        except Exception as exc:
            db.log_activity("WARN", "AUDITOR", f"Screenshot capture error for '{bname}': {exc}")
            return results

    async def run_technical_scan(self, website_url: str, category: str = "") -> Dict[str, Any]:
        """Deep technical scan of website speed, mobile responsiveness, ordering/booking, and SEO."""
        if not website_url or not website_url.strip():
            return {
                "has_website": False,
                "reachable": False,
                "technical_score": 15,
                "load_time_ms": 0,
                "is_https": False,
                "is_mobile_friendly": False,
                "has_online_ordering_or_booking": False,
                "has_whatsapp_or_chat_widget": False,
                "has_seo_meta": False,
                "detected_issues": [
                    "No business website or web app exists on Google Maps (High Priority Lead)",
                    "Missing direct commission-free online ordering / appointment booking system",
                    "Invisible on organic Google Search outside Maps pack",
                    "No mobile-friendly catalog/menu or instant WhatsApp lead capture",
                ],
                "page_title": "No Website Found - High Priority Lead",
            }

        url = website_url.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        is_https = url.lower().startswith("https://")
        detected_issues = []
        score = 100

        if not is_https:
            detected_issues.append("Website is not secure (Missing HTTPS/SSL security certificate — browsers show 'Not Secure' warning)")
            score -= 15

        headers = {"User-Agent": DESKTOP_USER_AGENT}

        start_t = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=False, headers=headers) as client:
                resp = await client.get(url)
                load_time_ms = int((time.perf_counter() - start_t) * 1000)
                html = resp.text or ""
        except Exception as exc:
            return {
                "has_website": True,
                "reachable": False,
                "technical_score": 25,
                "load_time_ms": 0,
                "is_https": is_https,
                "is_mobile_friendly": False,
                "has_online_ordering_or_booking": False,
                "has_whatsapp_or_chat_widget": False,
                "has_seo_meta": False,
                "detected_issues": [
                    f"Website is broken, offline, or failing to load ({str(exc)[:60]})",
                    "Visitors clicking from Google Maps hit an error page",
                    "Missing working online ordering or appointment booking system",
                ],
                "page_title": "Unreachable Website",
            }

        soup = BeautifulSoup(html, "html.parser")
        html_lower = html.lower()

        if load_time_ms > 2500:
            detected_issues.append(f"Slow website response time ({load_time_ms} ms) causing 40%+ mobile visitors to bounce")
            score -= 15
        elif load_time_ms > 1500:
            score -= 5

        viewport = soup.find("meta", attrs={"name": re.compile(r"viewport", re.I)})
        is_mobile_friendly = bool(viewport)
        if not is_mobile_friendly:
            detected_issues.append("Not mobile-friendly (Missing responsive mobile viewport optimization)")
            score -= 20

        ordering_keywords = [
            "order online",
            "order-online",
            "book now",
            "book appointment",
            "reserve a table",
            "reservation",
            "add to cart",
            "checkout",
            "calendly.com",
            "toasttab.com",
            "chownow.com",
            "shopify",
            "woocommerce",
            "square.site",
            "opentable",
            "resy.com",
        ]
        has_ordering_or_booking = any(kw in html_lower for kw in ordering_keywords)
        if not has_ordering_or_booking:
            detected_issues.append(
                f"No direct commission-free online ordering or instant booking workflow found for {category or 'customers'}"
            )
            score -= 20

        chat_keywords = ["wa.me/", "api.whatsapp.com", "tawk.to", "intercom", "crisp.chat", "tidio", "livechat"]
        has_chat_widget = any(kw in html_lower for kw in chat_keywords)
        if not has_chat_widget:
            detected_issues.append("No instant WhatsApp or 24/7 AI Live Chat widget to convert website visitors into leads")
            score -= 12

        title_tag = soup.title.string.strip() if (soup.title and soup.title.string) else ""
        meta_desc = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
        has_seo_meta = bool(title_tag and meta_desc and meta_desc.get("content"))
        if not has_seo_meta:
            detected_issues.append("Weak Local SEO setup (Missing meta description or search-optimized heading tags)")
            score -= 10

        if any(yr in html_lower for yr in ["© 2018", "© 2019", "© 2020", "© 2021", "copyright 2019", "copyright 2020"]):
            detected_issues.append("Outdated website UI/UX design & legacy code structure")
            score -= 10

        if not detected_issues:
            detected_issues.append("Missing dedicated iOS/Android Mobile Loyalty App & automated AI customer retention")
            score = min(score, 78)

        score = max(15, min(95, score))

        return {
            "has_website": True,
            "reachable": True,
            "technical_score": score,
            "load_time_ms": load_time_ms,
            "is_https": is_https,
            "is_mobile_friendly": is_mobile_friendly,
            "has_online_ordering_or_booking": has_ordering_or_booking,
            "has_whatsapp_or_chat_widget": has_chat_widget,
            "has_seo_meta": has_seo_meta,
            "detected_issues": detected_issues,
            "page_title": title_tag[:100] if title_tag else "Business Website",
        }

    async def audit_lead_and_prepare_outreach(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """
        Full pipeline step for a single lead:
        1. Run deep technical website scan
        2. Capture live dual Playwright screenshots (Desktop 1280x800 & Mobile 390x844)
        3. Extract genuine business email if missing
        4. Run Gemini/Groq AI gap analysis & outreach copywriting
        5. Persist screenshot paths and audit results to SQLite
        """
        lead_id = lead["id"]
        business_name = lead.get("business_name", "Unknown")
        website = lead.get("website", "")
        category = lead.get("category", "")

        db.log_activity(
            "INFO",
            "AUDITOR",
            f"Auditing '{business_name}' ({website if website else 'NO WEBSITE'}) & capturing screenshots...",
        )

        tech_scan = await self.run_technical_scan(website, category)
        shots = await self.capture_website_screenshots(lead, tech_scan)

        # Persist media paths in DB
        db.update_lead_media(
            lead_id=lead_id,
            screenshot_desktop=shots.get("screenshot_desktop", ""),
            screenshot_mobile=shots.get("screenshot_mobile", ""),
            maps_screenshot=shots.get("maps_screenshot", ""),
        )

        extracted_email = shots.get("extracted_email") or ""
        if extracted_email and not lead.get("email"):
            lead["email"] = extracted_email

        ai_result = await ai_engine.analyze_and_craft_outreach(lead, tech_scan)

        priority = ai_result.get("priority", "HIGH_PRIORITY" if not website else "HIGH")
        audit_score = int(ai_result.get("audit_score", tech_scan.get("technical_score", 50)))

        combined_report = {
            "technical_scan": tech_scan,
            "screenshot_url": shots.get("primary_screenshot") or shots.get("screenshot_desktop") or "",
            "screenshot_desktop_url": shots.get("screenshot_desktop", ""),
            "screenshot_mobile_url": shots.get("screenshot_mobile", ""),
            "maps_screenshot_url": shots.get("maps_screenshot", ""),
            "summary": ai_result.get("summary", ""),
            "issues_found": ai_result.get("issues_found", tech_scan.get("detected_issues", [])),
            "recommended_solutions": ai_result.get("recommended_solutions", []),
            "estimated_revenue_impact": ai_result.get(
                "estimated_revenue_impact", "+35% to +45% increase in direct online orders & bookings"
            ),
        }

        email_subject = ai_result.get("email_subject", f"Website & Digital Audit Report for {business_name}")
        email_body = ai_result.get("email_body", "")
        whatsapp_msg = ai_result.get("whatsapp_message", "")

        db.update_lead_audit_and_drafts(
            lead_id=lead_id,
            priority=priority,
            audit_score=audit_score,
            audit_report=combined_report,
            email_subject=email_subject,
            email_body=email_body,
            whatsapp_msg=whatsapp_msg,
            extracted_email=extracted_email or None,
        )

        db.log_activity(
            "SUCCESS",
            "AUDITOR",
            f"Audit + Screenshots complete for '{business_name}' -> Priority: {priority} (Score: {audit_score}/100)",
        )

        return db.get_lead_by_id(lead_id) or {}


website_auditor = WebsiteAuditor()
