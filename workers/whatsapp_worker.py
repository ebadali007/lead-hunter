import asyncio
import base64
import hashlib
import random
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote

try:
    from playwright.async_api import BrowserContext, Page, Playwright, async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    BrowserContext = Any
    Page = Any
    Playwright = Any
    async_playwright = None
    PLAYWRIGHT_AVAILABLE = False

from config import settings
from database import db


class WhatsAppWorker:
    """
    Pure Python Playwright WhatsApp Web Automation Engine:
    - Persistent session in ./whatsapp_session (Scan QR once, stays logged in)
    - Live QR Code base64 capture for Dashboard UI + visible browser window option
    - Sends personalized WhatsApp messages with Anti-Spam Delays & Daily Limits
    - Reads incoming client WhatsApp replies for 24/7 AI Sales Agent
    """

    def __init__(self):
        self.playwright: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_connected: bool = False
        self.status_text: str = "Not initialized (Click 'Connect WhatsApp QR' on Dashboard)"
        self.qr_base64: str = ""
        self._lock = asyncio.Lock()

    @staticmethod
    def normalize_phone(phone: str) -> str:
        digits = re.sub(r"\D", "", phone or "")
        # If 10-digit US/Canada number without country code, prefix '1'
        if len(digits) == 10:
            digits = "1" + digits
        return digits

    async def initialize_session(self, headless: bool = False) -> Dict[str, Any]:
        """
        Launch persistent Chromium context for WhatsApp Web so user can scan QR code.
        """
        async with self._lock:
            try:
                settings.WHATSAPP_SESSION_DIR.mkdir(parents=True, exist_ok=True)
                if not self.playwright:
                    self.playwright = await async_playwright().start()

                if not self.context:
                    launch_args = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
                    for ch in [None, "chrome", "msedge"]:
                        try:
                            if ch:
                                self.context = await self.playwright.chromium.launch_persistent_context(
                                    user_data_dir=str(settings.WHATSAPP_SESSION_DIR),
                                    channel=ch,
                                    headless=headless,
                                    viewport={"width": 1200, "height": 800},
                                    args=launch_args,
                                )
                            else:
                                self.context = await self.playwright.chromium.launch_persistent_context(
                                    user_data_dir=str(settings.WHATSAPP_SESSION_DIR),
                                    headless=headless,
                                    viewport={"width": 1200, "height": 800},
                                    args=launch_args,
                                )
                            break
                        except Exception:
                            continue
                    if not self.context:
                        raise RuntimeError("Could not launch Chromium, Chrome, or Edge browser.")

                self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
                if "web.whatsapp.com" not in (self.page.url or ""):
                    self.status_text = "Opening WhatsApp Web..."
                    await self.page.goto("https://web.whatsapp.com", wait_until="domcontentloaded", timeout=45000)
                    await asyncio.sleep(3.5)

                await self.refresh_status()
                return self.get_status_dict()
            except Exception as exc:
                self.status_text = f"Browser launch warning: {exc}"
                db.log_activity("WARN", "WHATSAPP", f"WhatsApp Web launch notice: {exc}")
                return self.get_status_dict()

    async def refresh_status(self) -> Dict[str, Any]:
        """Check if WhatsApp Web is logged in or displaying QR code."""
        if not self.page or self.page.is_closed():
            self.is_connected = False
            return self.get_status_dict()

        try:
            # Check if chat list / side panel is visible (means logged in)
            chat_pane = self.page.locator('#pane-side, div[aria-label="Chat list"]').first
            if await chat_pane.count() > 0 and await chat_pane.is_visible():
                self.is_connected = True
                self.qr_base64 = ""
                self.status_text = "Connected & Active (WhatsApp Web Ready)"
                return self.get_status_dict()

            # Otherwise check if QR code canvas is present and capture screenshot
            qr_canvas = self.page.locator('canvas[aria-label*="Scan"], div[data-ref] canvas').first
            if await qr_canvas.count() > 0 and await qr_canvas.is_visible():
                png_bytes = await qr_canvas.screenshot()
                self.qr_base64 = "data:image/png;base64," + base64.b64encode(png_bytes).decode("utf-8")
                self.is_connected = False
                self.status_text = "Waiting for QR Code Scan on your Phone..."
            else:
                # Take full viewport screenshot fallback so user can see current WhatsApp Web state
                png_bytes = await self.page.screenshot()
                self.qr_base64 = "data:image/png;base64," + base64.b64encode(png_bytes).decode("utf-8")
                self.status_text = "Loading WhatsApp Web interface..."
        except Exception as exc:
            self.status_text = f"Status check: {exc}"

        return self.get_status_dict()

    def get_status_dict(self) -> Dict[str, Any]:
        return {
            "connected": self.is_connected,
            "status_text": self.status_text,
            "qr_base64": self.qr_base64,
        }

    async def send_whatsapp_message(
        self,
        lead_id: int,
        phone: str,
        message: str,
        is_reply: bool = False,
    ) -> Dict[str, Any]:
        """
        Send a WhatsApp message via Playwright WhatsApp Web.
        Falls back to SIMULATED mode if QR code hasn't been scanned yet so user can test freely.
        """
        clean_phone = self.normalize_phone(phone)
        if len(clean_phone) < 8:
            return {"ok": False, "status": "SKIPPED", "error": "No valid phone number"}

        if not is_reply:
            counts = db.get_today_outreach_counts()
            if counts["whatsapps_today"] >= settings.DAILY_WHATSAPP_LIMIT:
                db.log_activity(
                    "WARN",
                    "WHATSAPP",
                    f"Daily WhatsApp limit ({settings.DAILY_WHATSAPP_LIMIT}) reached. Skipping {phone}.",
                )
                return {"ok": False, "status": "LIMIT_REACHED", "error": "Daily WhatsApp limit reached"}

        await self.refresh_status()

        if not self.is_connected or not self.page:
            # Simulated mode when QR isn't linked yet
            if not is_reply and lead_id > 0:
                db.record_outreach(
                    lead_id=lead_id,
                    channel="WHATSAPP",
                    recipient=phone,
                    subject="WhatsApp Direct",
                    message_body=message,
                    delivery_status="SIMULATED",
                    error_message="Simulated (Scan WhatsApp QR code on Dashboard for live WhatsApp sending)",
                )
            db.log_activity(
                "INFO",
                "WHATSAPP",
                f"[SIMULATED WA] Prepared WhatsApp message for {phone} (Connect WhatsApp QR on Dashboard for live sending)",
            )
            return {"ok": True, "status": "SIMULATED"}

        async with self._lock:
            try:
                encoded_text = quote(message)
                send_url = f"https://web.whatsapp.com/send?phone={clean_phone}&text={encoded_text}"
                await self.page.goto(send_url, wait_until="domcontentloaded", timeout=35000)
                await asyncio.sleep(random.uniform(3.5, 5.5))

                # Wait for either the Send button or message input box
                send_btn = self.page.locator('button[aria-label="Send"], span[data-icon="send"]').first
                try:
                    await send_btn.wait_for(state="visible", timeout=15000)
                    await asyncio.sleep(random.uniform(0.8, 1.8))
                    await send_btn.click()
                except Exception:
                    # Try pressing Enter in the compose box
                    box = self.page.locator('div[contenteditable="true"][data-tab="10"]').first
                    if await box.count() > 0:
                        await box.press("Enter")
                    else:
                        raise RuntimeError("Phone number not registered on WhatsApp or compose box did not load")

                await asyncio.sleep(random.uniform(2.0, 3.2))

                if not is_reply and lead_id > 0:
                    db.record_outreach(
                        lead_id=lead_id,
                        channel="WHATSAPP",
                        recipient=phone,
                        subject="WhatsApp Direct",
                        message_body=message,
                        delivery_status="SENT",
                    )
                db.log_activity("SUCCESS", "WHATSAPP", f"Sent live WhatsApp message to {phone}")
                return {"ok": True, "status": "SENT"}

            except Exception as exc:
                if not is_reply and lead_id > 0:
                    db.record_outreach(
                        lead_id=lead_id,
                        channel="WHATSAPP",
                        recipient=phone,
                        subject="WhatsApp Direct",
                        message_body=message,
                        delivery_status="FAILED",
                        error_message=str(exc),
                    )
                db.log_activity("WARN", "WHATSAPP", f"WhatsApp send issue for {phone}: {exc}")
                return {"ok": False, "status": "FAILED", "error": str(exc)}

    async def check_unread_replies(self) -> List[Dict[str, Any]]:
        """
        Scan WhatsApp Web for unread incoming messages every 5 minutes and match with SQLite leads.
        """
        await self.refresh_status()
        if not self.is_connected or not self.page:
            return []

        incoming_list: List[Dict[str, Any]] = []
        async with self._lock:
            try:
                unread_badges = self.page.locator('span[aria-label*="unread message"]')
                count = await unread_badges.count()
                for i in range(min(count, 10)):
                    badge = unread_badges.nth(i)
                    await badge.click()
                    await asyncio.sleep(random.uniform(1.2, 2.2))

                    # Read header contact name / phone
                    header_title = ""
                    header_loc = self.page.locator("header span[dir='auto']").first
                    if await header_loc.count() > 0:
                        header_title = (await header_loc.inner_text()).strip()

                    # Read last incoming message bubble
                    in_bubbles = self.page.locator("div.message-in span.selectable-text")
                    b_count = await in_bubbles.count()
                    if b_count == 0:
                        continue

                    last_text = (await in_bubbles.nth(b_count - 1).inner_text()).strip()
                    if not last_text:
                        continue

                    msg_hash = "wa_" + hashlib.md5(f"{header_title}:{last_text}".encode("utf-8")).hexdigest()
                    if db.is_message_processed(msg_hash):
                        continue

                    matched_lead = db.find_lead_by_contact(header_title)
                    if matched_lead:
                        incoming_list.append(
                            {
                                "lead": matched_lead,
                                "sender_phone": matched_lead.get("phone") or header_title,
                                "message_text": last_text,
                                "external_msg_id": msg_hash,
                            }
                        )
            except Exception as exc:
                db.log_activity("WARN", "WHATSAPP", f"WhatsApp unread check warning: {exc}")

        return incoming_list


whatsapp_worker = WhatsAppWorker()
