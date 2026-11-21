"""
100% Authentic Google Maps Scraper (Playwright) — NO mock / dummy / random data.

Flow:
  1. Open real Google Maps (https://www.google.com/maps), type "<category> in <city>" in the search box.
  2. Scroll the left results sidebar and COLLECT every listing link first (no clicking => no stale panel data).
  3. Open EACH listing's own URL directly and wait for its detail panel, then extract:
     Business Name, Category, Exact Address, Phone, Website, Google Maps URL, Rating, Reviews Count.
  4. If the business has NO website, save a screenshot of its Google Maps listing.
  5. Stream each real lead to the orchestrator (website visit, email scraping, screenshots and
     AI audit happen next in workers/website_auditor.py).

If Google shows a "verify you are human" / CAPTCHA page, scraping STOPS and is reported in the
logs. The system never tries to bypass it.
"""

import asyncio
import hashlib
import random
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set
from urllib.parse import parse_qs, quote_plus, unquote_plus, urljoin, urlparse

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


DESKTOP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
IGNORED_EMAIL_DOMAINS = {
    "example.com", "domain.com", "email.com", "yoursite.com", "yourdomain.com", "sentry.io",
    "sentry.wixpress.com", "wixpress.com", "wix.com", "squarespace.com", "wordpress.org",
    "w3.org", "schema.org", "googleapis.com", "googleusercontent.com", "google.com",
    "yelp.com", "tripadvisor.com", "facebook.com", "instagram.com", "sentry-next.wixpress.com",
}
IGNORED_EMAIL_PREFIXES = ("noreply", "no-reply", "donotreply", "user@", "name@", "email@", "your@")
IGNORED_EMAIL_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js", ".woff", ".woff2", ".ttf")

CAPTCHA_MARKERS = ("unusual traffic", "/sorry/", "recaptcha", "not a robot")


def make_slug(name: str, suffix: str = "") -> str:
    """File-system safe slug used for screenshots/<business_name>.png."""
    base = re.sub(r"[^a-z0-9]+", "_", (name or "business").lower()).strip("_")[:60] or "business"
    return f"{base}_{suffix}" if suffix else base


def clean_emails(raw_emails: Set[str]) -> List[str]:
    """Validate & de-duplicate scraped emails (keeps .ca / .com intact)."""
    valid: List[str] = []
    for em in raw_emails:
        e = unquote_plus(em or "").strip().lower().strip(".,;:()<>[]\"'")
        if e.startswith("mailto:"):
            e = e[7:]
        e = e.split("?")[0]
        if len(e) < 6 or len(e) > 80 or e.count("@") != 1:
            continue
        if e.endswith(IGNORED_EMAIL_EXTENSIONS) or e.startswith(IGNORED_EMAIL_PREFIXES):
            continue
        domain = e.split("@")[1]
        if "." not in domain or any(bad == domain or domain.endswith("." + bad) for bad in IGNORED_EMAIL_DOMAINS):
            continue
        if re.search(r"\d{3,}x\d{3,}", e):  # image size patterns like logo@2x / 300x200
            continue
        if e not in valid:
            valid.append(e)
    return valid


def decode_cloudflare_email(encoded_hex: str) -> str:
    """Decode emails hidden by Cloudflare email protection (data-cfemail)."""
    try:
        key = int(encoded_hex[:2], 16)
        return "".join(chr(int(encoded_hex[i:i + 2], 16) ^ key) for i in range(2, len(encoded_hex), 2))
    except Exception:
        return ""


def canonical_place_url(href: str) -> str:
    """Strip tracking query params so the same listing always has the same URL (duplicate check)."""
    if not href:
        return ""
    href = href.split("?")[0]
    if href.startswith("/"):
        href = "https://www.google.com" + href
    return href


async def launch_browser(playwright, headless: bool = True):
    """Launch installed Chrome, then Edge, then Playwright's bundled Chromium."""
    launch_args = ["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"]
    last_error: Optional[Exception] = None
    for channel in ("chrome", "msedge", None):
        try:
            if channel:
                return await playwright.chromium.launch(channel=channel, headless=headless, args=launch_args)
            return await playwright.chromium.launch(headless=headless, args=launch_args)
        except Exception as exc:
            last_error = exc
            continue
    raise RuntimeError(f"Could not launch Chrome/Edge/Chromium: {last_error}")


class GoogleMapsScraper:
    def __init__(self):
        self.last_error: str = ""

    # ------------------------------------------------------------------
    # Lightweight HTTP email crawler (backup for the Playwright crawler)
    # ------------------------------------------------------------------
    async def extract_email_from_website(self, website_url: str) -> str:
        if not website_url:
            return ""
        url = website_url.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        found: Set[str] = set()
        pages: List[str] = [url]
        headers = {"User-Agent": DESKTOP_USER_AGENT, "Accept": "text/html,application/xhtml+xml"}

        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, verify=False, headers=headers) as client:
            for std_path in ("/contact", "/contact-us", "/about"):
                pages.append(urljoin(url, std_path))
            for page_url in pages[:4]:
                try:
                    resp = await client.get(page_url)
                    if resp.status_code != 200 or not resp.text:
                        continue
                    found.update(EMAIL_REGEX.findall(resp.text))
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for a_tag in soup.find_all("a", href=True):
                        if a_tag["href"].lower().startswith("mailto:"):
                            found.add(a_tag["href"][7:])
                    for tag in soup.select("[data-cfemail]"):
                        found.add(decode_cloudflare_email(tag.get("data-cfemail", "")))
                    cleaned = clean_emails(found)
                    if cleaned:
                        return cleaned[0]
                except Exception:
                    continue
        cleaned = clean_emails(found)
        return cleaned[0] if cleaned else ""

    # ------------------------------------------------------------------
    # Google Maps helpers
    # ------------------------------------------------------------------
    @staticmethod
    async def _is_captcha_page(page) -> bool:
        try:
            if "/sorry/" in (page.url or ""):
                return True
            body_text = (await page.inner_text("body", timeout=3000)).lower()
            return any(marker in body_text for marker in CAPTCHA_MARKERS)
        except Exception:
            return False

    @staticmethod
    async def _handle_cookie_consent(page):
        """Accept Google's cookie-consent screen (shown in some regions). This is not a CAPTCHA."""
        try:
            if "consent.google" in (page.url or ""):
                btn = page.locator('button:has-text("Accept all"), button:has-text("Reject all")').first
                if await btn.count() > 0:
                    await btn.click(timeout=5000)
                    await page.wait_for_load_state("domcontentloaded", timeout=15000)
                    await asyncio.sleep(2)
        except Exception:
            pass

    async def _open_search(self, page, search_query: str) -> bool:
        """Open real Google Maps and search for the query. Returns False if blocked."""
        await page.goto("https://www.google.com/maps?hl=en", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(random.uniform(2.5, 4.0))
        await self._handle_cookie_consent(page)

        if await self._is_captcha_page(page):
            return False

        typed = False
        try:
            search_box = page.locator("input#searchboxinput, input[name='q']").first
            await search_box.wait_for(state="visible", timeout=15000)
            await search_box.click()
            await search_box.fill("")
            await search_box.type(search_query, delay=random.randint(45, 95))
            await asyncio.sleep(random.uniform(0.6, 1.2))
            await search_box.press("Enter")
            typed = True
        except Exception as exc:
            db.log_activity("WARN", "SCRAPER", f"Search box not ready ({exc}). Opening the Maps search URL directly...")

        if not typed:
            maps_url = f"https://www.google.com/maps/search/{quote_plus(search_query)}?hl=en"
            await page.goto(maps_url, wait_until="domcontentloaded", timeout=60000)

        await asyncio.sleep(random.uniform(3.0, 4.5))
        await self._handle_cookie_consent(page)
        return not await self._is_captcha_page(page)

    async def _collect_listing_links(self, page, wanted: int) -> List[Dict[str, str]]:
        """Scroll the left results sidebar and collect unique listing URLs + card labels."""
        listings: List[Dict[str, str]] = []
        seen: Set[str] = set()

        # A query can open a single place directly instead of a results list
        try:
            await page.wait_for_selector('div[role="feed"], h1.DUwDvf', timeout=25000)
        except Exception:
            db.log_activity("WARN", "SCRAPER", "Google Maps results did not load within 25s.")
            return listings

        if await page.locator('div[role="feed"]').count() == 0 and "/maps/place/" in page.url:
            url = canonical_place_url(page.url)
            return [{"url": url, "label": ""}]

        feed = page.locator('div[role="feed"]').first
        stale_rounds = 0
        for _ in range(40):
            cards = page.locator('div[role="feed"] a[href*="/maps/place/"]')
            count = await cards.count()
            new_found = 0
            for i in range(count):
                try:
                    href = await cards.nth(i).get_attribute("href") or ""
                    label = (await cards.nth(i).get_attribute("aria-label") or "").strip()
                except Exception:
                    continue
                url = canonical_place_url(href)
                if url and url not in seen:
                    seen.add(url)
                    listings.append({"url": url, "label": label})
                    new_found += 1

            if len(listings) >= wanted:
                break

            end_marker = page.locator("text=You've reached the end of the list")
            if await end_marker.count() > 0:
                break

            stale_rounds = stale_rounds + 1 if new_found == 0 else 0
            if stale_rounds >= 4:
                break

            try:
                await feed.evaluate("el => el.scrollBy(0, el.clientHeight * 0.9)")
            except Exception:
                await page.mouse.wheel(0, 1200)
            await asyncio.sleep(random.uniform(1.6, 2.8))

        db.log_activity("INFO", "SCRAPER", f"Collected {len(listings)} real Google Maps listing links from the sidebar.")
        return listings

    @staticmethod
    async def _attr(page, selector: str, attr: str) -> str:
        try:
            loc = page.locator(selector).first
            if await loc.count() > 0:
                return (await loc.get_attribute(attr, timeout=3000) or "").strip()
        except Exception:
            pass
        return ""

    @staticmethod
    async def _text(page, selector: str) -> str:
        try:
            loc = page.locator(selector).first
            if await loc.count() > 0:
                return (await loc.inner_text(timeout=3000) or "").strip()
        except Exception:
            pass
        return ""

    async def _extract_place_details(self, page, listing: Dict[str, str], location: str, category: str) -> Optional[Dict[str, Any]]:
        """Open a listing's own URL and extract 100% real details from its detail panel."""
        place_url = listing["url"]
        await page.goto(place_url + "?hl=en", wait_until="domcontentloaded", timeout=45000)
        try:
            await page.wait_for_selector("h1.DUwDvf", timeout=20000)
        except Exception:
            db.log_activity("WARN", "SCRAPER", f"Detail panel did not load for {listing.get('label') or place_url}. Skipping.")
            return None
        await asyncio.sleep(random.uniform(1.4, 2.2))  # let address/phone/website buttons render

        name = await self._text(page, "h1.DUwDvf")
        if not name or name.lower() in ("results", "sponsored"):
            name = listing.get("label", "")
        if not name:
            return None

        panel_text = (await self._text(page, 'div[role="main"]')).lower()
        if "permanently closed" in panel_text:
            db.log_activity("INFO", "SCRAPER", f"Skipped '{name}' (permanently closed on Google Maps).")
            return None

        real_category = await self._text(page, "button.DkEaL") or await self._text(page, 'button[jsaction*="category"]') or category

        address = (await self._attr(page, 'button[data-item-id="address"]', "aria-label")).replace("Address:", "").strip()

        phone = (await self._attr(page, 'button[data-item-id^="phone:tel:"]', "aria-label")).replace("Phone:", "").strip()
        if not phone:
            item_id = await self._attr(page, 'button[data-item-id^="phone:tel:"]', "data-item-id")
            phone = item_id.replace("phone:tel:", "").strip()

        website = await self._attr(page, 'a[data-item-id="authority"]', "href")
        if "google.com/url" in website:
            website = parse_qs(urlparse(website).query).get("q", [website])[0]

        rating = 0.0
        reviews_count = 0
        rating_txt = await self._text(page, 'div.F7nice span[aria-hidden="true"]')
        try:
            rating = float(rating_txt.replace(",", "."))
        except ValueError:
            rating = 0.0
        reviews_aria = await self._attr(page, 'div.F7nice span[aria-label*="review"]', "aria-label")
        digits = re.findall(r"[\d,.]+", reviews_aria)
        if digits:
            reviews_count = int(re.sub(r"[^\d]", "", digits[0]) or 0)
        if not reviews_count:
            f7 = await self._text(page, "div.F7nice")
            m = re.search(r"\(([\d,.]+)\)", f7)
            if m:
                reviews_count = int(re.sub(r"[^\d]", "", m.group(1)) or 0)

        reviews_snippet = (await self._text(page, "span.wiI7pd"))[:240]

        lead = {
            "business_name": name,
            "category": real_category,
            "location": location,
            "address": address,
            "phone": phone,
            "email": "",
            "website": website,
            "place_url": place_url,
            "rating": rating,
            "reviews_count": reviews_count,
            "reviews_snippet": reviews_snippet,
            "maps_screenshot": "",
        }

        # No website => save a screenshot of the real Google Maps listing as audit evidence
        if not website:
            suffix = hashlib.md5(place_url.encode("utf-8")).hexdigest()[:6]
            file_name = f"{make_slug(name, suffix)}_maps.png"
            out_path = settings.SCREENSHOTS_DIR / file_name
            try:
                await page.screenshot(path=str(out_path), full_page=False)
                lead["maps_screenshot"] = f"/screenshots/{file_name}"
                db.log_activity("INFO", "SCRAPER", f"No website for '{name}' -> Google Maps listing screenshot saved: screenshots/{file_name}")
            except Exception as exc:
                db.log_activity("WARN", "SCRAPER", f"Could not screenshot Maps listing for '{name}': {exc}")

        return lead

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------
    async def scrape_google_maps(
        self,
        location: str,
        category: str,
        max_leads: int = 10,
        on_lead_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> List[Dict[str, Any]]:
        self.last_error = ""
        if not PLAYWRIGHT_AVAILABLE:
            self.last_error = "Playwright is not installed. Run: pip install playwright && python -m playwright install chromium"
            db.log_activity("ERROR", "SCRAPER", self.last_error)
            return []

        search_query = f"{category} in {location}"
        db.log_activity("INFO", "SCRAPER", f"Opening real Google Maps and searching: '{search_query}' (target {max_leads} new leads)")

        scraped: List[Dict[str, Any]] = []
        try:
            async with async_playwright() as p:
                browser = await launch_browser(p, headless=settings.HEADLESS_SCRAPER)
                context = await browser.new_context(
                    viewport={"width": 1366, "height": 900},
                    locale="en-US",
                    user_agent=DESKTOP_USER_AGENT,
                    extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
                )
                page = await context.new_page()
                page.set_default_timeout(30000)

                if not await self._open_search(page, search_query):
                    self.last_error = (
                        "Google asked for human verification (CAPTCHA). Scraping stopped - the system does not bypass it. "
                        "Wait a while, lower the daily limit, then try again."
                    )
                    db.log_activity("ERROR", "SCRAPER", self.last_error)
                    await browser.close()
                    return []

                # Collect extra links because some will be duplicates already in SQLite or closed businesses
                listings = await self._collect_listing_links(page, wanted=max_leads * 3)
                if not listings:
                    self.last_error = f"Google Maps returned no listings for '{search_query}'."
                    db.log_activity("WARN", "SCRAPER", self.last_error)

                for listing in listings:
                    if len(scraped) >= max_leads:
                        break

                    if db.is_duplicate_lead(business_name=listing.get("label", ""), place_url=listing["url"]):
                        db.log_activity("INFO", "SCRAPER", f"Skipped duplicate (already in SQLite): {listing.get('label') or listing['url']}")
                        continue

                    try:
                        await asyncio.sleep(random.uniform(2.0, 4.0))  # polite, human-like pacing
                        lead = await self._extract_place_details(page, listing, location, category)
                    except Exception as exc:
                        db.log_activity("WARN", "SCRAPER", f"Listing failed ({listing.get('label') or listing['url']}): {exc}")
                        if await self._is_captcha_page(page):
                            self.last_error = "Google asked for human verification (CAPTCHA) mid-run. Scraping stopped."
                            db.log_activity("ERROR", "SCRAPER", self.last_error)
                            break
                        continue

                    if not lead:
                        continue

                    if db.is_duplicate_lead(
                        business_name=lead["business_name"], phone=lead["phone"],
                        website=lead["website"], place_url=lead["place_url"],
                    ):
                        db.log_activity("INFO", "SCRAPER", f"Skipped duplicate (already in SQLite): {lead['business_name']}")
                        continue

                    scraped.append(lead)
                    db.log_activity(
                        "SUCCESS",
                        "SCRAPER",
                        f"REAL BUSINESS #{len(scraped)}: {lead['business_name']} | {lead['category']} | "
                        f"Phone: {lead['phone'] or 'N/A'} | Address: {lead['address'] or 'N/A'} | "
                        f"Rating: {lead['rating'] or 'N/A'} ({lead['reviews_count']} reviews) | "
                        f"Website: {lead['website'] or 'NO WEBSITE (HIGH PRIORITY)'}",
                    )
                    if on_lead_callback:
                        await on_lead_callback(lead)

                await browser.close()
        except Exception as exc:
            self.last_error = f"Google Maps scraper error: {exc}"
            db.log_activity("ERROR", "SCRAPER", self.last_error)

        db.log_activity("INFO", "SCRAPER", f"Google Maps scraping finished: {len(scraped)} new real businesses.")
        return scraped

    # Backward-compatible alias
    scrape_google_maps_playwright = scrape_google_maps


maps_scraper = GoogleMapsScraper()
