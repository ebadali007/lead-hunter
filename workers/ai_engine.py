import json
import re
import time
from typing import Any, Dict, List, Optional
import httpx

from config import settings
from database import db


class AIEngine:
    """
    Dynamic Multi-Model Zero-Cost AI Brain:
    - Complex Reasoning / Website Audit:
        Primary: Gemini (gemini-3.8-flash -> gemini-2.5-flash)
        Backup:  Groq (llama-3.3-70b-versatile)
    - Fast Filtering / 24/7 Sales Agent Replies:
        Primary: Gemini (gemini-3.5-flash-lite -> gemini-2.0-flash)
        Backup:  Groq (llama-3.1-8b-instant / llama-3.3-70b-versatile)
    - Includes automatic circuit-breaker caching so invalid/rate-limited keys
      switch to backup in 0ms without wasting HTTP retries.
    """

    GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    GROQ_BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self):
        self._gemini_cooldown_until: float = 0.0
        self.last_active_provider: str = "Initializing"

    async def _call_gemini(self, prompt: str, model_name: str, temperature: float = 0.4) -> Optional[str]:
        if not settings.is_gemini_configured():
            return None

        # If Gemini is in cooldown due to invalid key format or 429 quota, skip immediately
        if time.time() < self._gemini_cooldown_until:
            return None

        # Quick check: standard Google AI Studio keys begin with 'AIza'
        if not settings.GEMINI_API_KEY.startswith("AIza"):
            self._gemini_cooldown_until = time.time() + 300
            return None

        candidates = [model_name]
        for fallback in [settings.GEMINI_FALLBACK_MODEL, "gemini-2.5-flash", "gemini-2.0-flash"]:
            if fallback and fallback not in candidates:
                candidates.append(fallback)

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 2048,
            },
        }

        async with httpx.AsyncClient(timeout=35.0) as client:
            for candidate in candidates:
                url = f"{self.GEMINI_BASE_URL}/{candidate}:generateContent?key={settings.GEMINI_API_KEY}"
                try:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates_list = data.get("candidates", [])
                        if candidates_list:
                            parts = candidates_list[0].get("content", {}).get("parts", [])
                            if parts and "text" in parts[0]:
                                self.last_active_provider = f"Gemini ({candidate})"
                                return parts[0]["text"]
                    elif resp.status_code in (400, 401, 403):
                        # Invalid API key or permission disabled; activate 5-min circuit breaker
                        self._gemini_cooldown_until = time.time() + 300
                        break
                    elif resp.status_code == 429:
                        self._gemini_cooldown_until = time.time() + 60
                        db.log_activity(
                            "WARN",
                            "AI_BRAIN",
                            f"Gemini rate limit on {candidate}. Auto-routing to Groq Free API for 60s...",
                        )
                        break
                    elif resp.status_code == 404:
                        continue
                except Exception:
                    break

        return None

    async def _call_groq(
        self, prompt: str, use_complex_model: bool = True, temperature: float = 0.4
    ) -> Optional[str]:
        if not settings.is_groq_configured():
            return None

        # Dynamic model routing on Groq:
        # Complex Audit -> llama-3.3-70b-versatile
        # Fast Sales Reply / Filtering -> llama-3.1-8b-instant (with 70b fallback)
        primary_groq = (
            settings.GROQ_MODEL or "llama-3.3-70b-versatile"
            if use_complex_model
            else "llama-3.1-8b-instant"
        )
        groq_candidates = [primary_groq]
        if "llama-3.3-70b-versatile" not in groq_candidates:
            groq_candidates.append("llama-3.3-70b-versatile")

        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=35.0) as client:
            for g_model in groq_candidates:
                payload = {
                    "model": g_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a Senior AI Automation & Agency Sales Strategist for "
                                f"{settings.AGENCY_NAME}. Always return accurate, high-converting outputs."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": temperature,
                    "max_tokens": 2048,
                }
                try:
                    resp = await client.post(self.GROQ_BASE_URL, headers=headers, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        self.last_active_provider = f"Groq ({g_model})"
                        return data["choices"][0]["message"]["content"]
                except Exception as exc:
                    db.log_activity("WARN", "AI_BRAIN", f"Groq request notice ({g_model}): {exc}")

        return None

    async def generate(self, prompt: str, use_complex_model: bool = True, temperature: float = 0.4) -> Optional[str]:
        """Run prompt on Gemini (complex or fast model) with instant circuit-breaker fallback to Groq."""
        target_model = settings.GEMINI_COMPLEX_MODEL if use_complex_model else settings.GEMINI_FAST_MODEL
        result = await self._call_gemini(prompt, model_name=target_model, temperature=temperature)
        if result:
            return result

        groq_result = await self._call_groq(
            prompt, use_complex_model=use_complex_model, temperature=temperature
        )
        if groq_result:
            return groq_result

        return None

    @staticmethod
    def _extract_json(raw_text: Optional[str]) -> Optional[Dict[str, Any]]:
        if not raw_text:
            return None
        cleaned = raw_text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            return json.loads(cleaned)
        except Exception:
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    return None
        return None

    # -------------------------------------------------------------------------
    # 1. AI AUDIT & HYPER-PERSONALIZED OUTREACH GENERATION
    # -------------------------------------------------------------------------
    async def analyze_and_craft_outreach(
        self, lead: Dict[str, Any], technical_audit: Dict[str, Any]
    ) -> Dict[str, Any]:
        business_name = lead.get("business_name", "Valued Business")
        category = lead.get("category", "Local Business")
        location = lead.get("location", "")
        rating = lead.get("rating", 0.0)
        reviews_count = lead.get("reviews_count", 0)
        reviews_snippet = lead.get("reviews_snippet", "")
        website = lead.get("website", "")
        website_domain = re.sub(r"^https?://(www\.)?", "", website).split("/")[0] if website else business_name
        has_website = bool(website)

        knowledge = settings.get_knowledge_base()

        prompt = f"""
You are a Senior Digital Agency Growth Strategist & Copywriter for "{settings.AGENCY_NAME}".
Analyze this scraped business lead and its technical website audit, then return a strict JSON object.

LEAD DETAILS:
- Business Name: {business_name}
- Category: {category}
- Location: {location}
- Google Rating: {rating} stars ({reviews_count} reviews)
- Customer Review Snippet: {reviews_snippet or "Strong local customer reputation"}
- Website URL: {website or "NONE (NO WEBSITE)"}

TECHNICAL AUDIT METRICS:
{json.dumps(technical_audit, indent=2)}

AGENCY KNOWLEDGE BASE:
{knowledge[:2200]}

INSTRUCTIONS:
1. If the business has NO website, priority MUST be "HIGH_PRIORITY" and audit_score should be 15. Highlight how much local search & mobile ordering/booking traffic they are missing despite their {rating}-star reviews.
2. If the business HAS a website, evaluate its weaknesses from the technical audit (slow speed, non-mobile friendly, missing direct online ordering/appointment booking, missing WhatsApp widget, outdated design, weak SEO) and explain the exact improvements our agency can build.
3. Write a hyper-personalized, natural, human-sounding cold Email (Subject + Body) and a concise WhatsApp message 100% in fluent, professional English.
   - 100% HUMAN APPEARANCE: Must read like a personal 1-on-1 note from an expert developer, NOT a generic agency sales pitch.
   - HIGH-OPEN SUBJECT LINE: Use natural, conversational lowercase subjects like:
     * "quick question for {business_name}"
     * "noticed something on {website_domain}"
     * "{business_name}'s website on mobile"
   - GATEKEEPER-BYPASS OPENING:
     Begin with: "Hi {business_name} team — quick question for the owner or whoever manages your website & customer orders:"
   - MENTION REAL SOCIAL PROOF: Acknowledge their real Google review rating ({rating}★ across {reviews_count} reviews) in {location}.
   - SPECIFIC PROBLEM & FIX:
     * Restaurants/Food: Highlight how direct commission-free mobile ordering saves 20-30% delivery app fees ($1,200+/month).
     * Clinics/Dentists: Highlight 24/7 automated mobile booking reducing phone tag & missed calls.
     * Salons/Spas: Highlight mobile portfolio & 1-click Instagram/Google booking.
     * Contractors/Home Services: Highlight emergency mobile quote forms with instant WhatsApp lead alerts.
   - ZERO-FRICTION PERMISSION CALL-TO-ACTION (CTA):
     Do NOT demand a 15-minute call in cold email #1. Instead, ask for permission to send the visual mockup:
     "I actually sketched out a quick 3-point visual concept preview tailored for {business_name} showing how this would look on mobile. Would it be okay if I sent that preview link over?"
   - SENDER SIGN-OFF:
     Sign off naturally as:
     Best regards,
     Zai Ebad
     Independent Web & App Developer
     WhatsApp / Direct: +92 329 3246454 (03293246454)
     Email: zaiebad56@gmail.com

RETURN ONLY VALID JSON WITH THIS EXACT SCHEMA:
{{
  "priority": "HIGH_PRIORITY" | "HIGH" | "MEDIUM" | "LOW",
  "audit_score": 0 to 100,
  "summary": "2-sentence executive summary of their current digital gap",
  "issues_found": ["issue 1", "issue 2", "issue 3"],
  "recommended_solutions": ["solution 1", "solution 2", "solution 3"],
  "estimated_revenue_impact": "Short statement of how our solution increases orders/bookings",
  "email_subject": "Natural, high-open-rate subject line for {business_name}",
  "email_body": "Full plain-text personalized email with line breaks",
  "whatsapp_message": "Short, friendly 3-4 sentence WhatsApp message for {business_name}"
}}
"""
        raw = await self.generate(prompt, use_complex_model=True, temperature=0.4)
        parsed = self._extract_json(raw)

        if parsed and "email_body" in parsed and "whatsapp_message" in parsed:
            if not has_website:
                parsed["priority"] = "HIGH_PRIORITY"
            return parsed

        return self._fallback_audit_and_outreach(lead, technical_audit)

    def _fallback_audit_and_outreach(
        self, lead: Dict[str, Any], technical_audit: Dict[str, Any]
    ) -> Dict[str, Any]:
        business_name = lead.get("business_name", "there")
        category = lead.get("category", "Business")
        location = lead.get("location", "your area")
        rating = lead.get("rating") or 4.6
        reviews_count = lead.get("reviews_count") or 35
        website = (lead.get("website") or "").strip()

        if not website:
            issues = [
                "No official website linked on Google Maps listing",
                "No direct commission-free online ordering or appointment booking system",
                "Missing mobile web presence for customers searching on smartphones",
            ]
            solutions = [
                f"Launch a fast, mobile-first website for {business_name} in 5–7 days",
                "Integrate direct commission-free online ordering / booking + WhatsApp order alerts",
                "Optimize Local SEO to capture top Google Maps & organic search traffic",
            ]
            priority = "HIGH_PRIORITY"
            score = 15
            summary = f"{business_name} has a strong {rating}★ local reputation ({reviews_count} reviews) in {location}, but has no website or direct online booking/ordering system."
            email_subject = f"quick question for {business_name}"
            email_body = (
                f"Hi {business_name} team — quick question for the owner or whoever manages your customer orders:\n\n"
                f"I came across {business_name} on Google Maps in {location} and noticed your impressive {rating}★ rating across {reviews_count} reviews.\n\n"
                f"However, I noticed there isn't a direct mobile website or online booking/ordering link attached to your profile—meaning customers searching on their smartphones can't view your full offerings or place direct orders.\n\n"
                f"I actually put together a free 3-point visual concept preview tailored for {business_name} showing how a clean, mobile-first ordering site would look.\n\n"
                f"Would it be okay if I sent that preview link over?\n\n"
                f"Best regards,\n"
                f"Zai Ebad\n"
                f"Independent Full-Stack Developer\n"
                f"WhatsApp / Direct: +92 329 3246454 (03293246454)\n"
                f"Email: zaiebad56@gmail.com"
            )
            wa_msg = (
                f"Hi {business_name} team! 👋 Saw your awesome {rating}★ reviews on Google Maps in {location}. "
                f"Noticed you don't have a website or direct online ordering/booking link connected yet. "
                f"I sketched a quick mobile concept preview specifically for {business_name} — mind if I share the link here?"
            )
        else:
            issues = technical_audit.get("detected_issues") or [
                "Slow mobile loading speed impacting visitor conversion",
                "No direct interactive online ordering / instant appointment booking flow",
                "Missing instant WhatsApp / AI lead capture widget on landing page",
            ]
            solutions = [
                "Modernize UI/UX with a <1.5s mobile-first responsive layout",
                "Add integrated direct online booking / ordering system with automated alerts",
                "Add 24/7 AI chat & WhatsApp conversion widget to double customer inquiries",
            ]
            score = int(technical_audit.get("technical_score", 52))
            priority = "HIGH" if score < 65 else "MEDIUM"
            summary = f"Website ({website}) is live, but our technical audit found {len(issues)} conversion bottlenecks including {', '.join(issues[:2])}."
            issue_highlight = issues[0].lower() if issues else "mobile loading speed"
            clean_domain = website.replace("https://", "").replace("http://", "").split("/")[0].replace("www.", "")
            email_subject = f"noticed something on {clean_domain or business_name}"
            email_body = (
                f"Hi {business_name} team — quick question for the owner or whoever manages your website & online orders:\n\n"
                f"I was checking out {business_name} in {location} ({rating}★ on Google!) and took a quick look at your website on mobile ({clean_domain}).\n\n"
                f"While your reputation is fantastic, I noticed a couple of simple things on the site that might be costing you customers—specifically: {issue_highlight}, and the lack of a streamlined 1-click mobile booking/ordering flow.\n\n"
                f"I actually sketched out a quick 3-point visual concept preview showing how {business_name}'s mobile experience would look with these fixed.\n\n"
                f"Would it be okay if I sent that preview link over?\n\n"
                f"Best regards,\n"
                f"Zai Ebad\n"
                f"Independent Full-Stack Developer\n"
                f"WhatsApp / Direct: +92 329 3246454 (03293246454)\n"
                f"Email: zaiebad56@gmail.com"
            )
            wa_msg = (
                f"Hi {business_name} team! 👋 Loved seeing your {rating}★ reviews in {location}. "
                f"I just ran a quick mobile audit on {clean_domain} and spotted 2 simple fixes ({issue_highlight}) that could noticeably boost your direct online bookings/orders. "
                f"Would you like me to send over the free visual summary here?"
            )

        return {
            "priority": priority,
            "audit_score": score,
            "summary": summary,
            "issues_found": issues,
            "recommended_solutions": solutions,
            "estimated_revenue_impact": "+30% to +45% increase in direct mobile inquiries & orders",
            "email_subject": email_subject,
            "email_body": email_body,
            "whatsapp_message": wa_msg,
        }

    async def generate_followup_pitch(
        self, lead: Dict[str, Any], step: int
    ) -> Dict[str, str]:
        """
        Generate high-converting autonomous follow-up email:
        step == 1: Value Bump (Day 3)
        step == 2: Polite Breakup (Day 6)
        """
        bname = lead.get("business_name", "there")
        cat = lead.get("category", "business")
        loc = lead.get("location", "")
        web = lead.get("website", "")
        rep = lead.get("audit_report") or {}
        issues = rep.get("issues_found") or ["mobile loading speed and direct booking flow"]
        issue = str(issues[0]).lower()

        if step == 1:
            clean_name = bname.strip()
            subject = f"quick follow-up for {clean_name}"
            body = (
                f"Hi {clean_name} team,\n\n"
                f"Following up briefly on my note from earlier this week—did you get a chance to see my message regarding {web or clean_name}?\n\n"
                f"With so many local customers searching on their phones in {loc}, fixing {issue} typically creates a noticeable bump in direct inquiries and orders.\n\n"
                f"I already have the free visual concept preview ready to share with your team. Would it be okay if I sent that link over?\n\n"
                f"Best regards,\n"
                f"Zai Ebad\n"
                f"Independent Full-Stack Developer\n"
                f"WhatsApp / Direct: +92 329 3246454 (03293246454)\n"
                f"Email: zaiebad56@gmail.com"
            )
        else:
            clean_name = bname.strip()
            subject = f"closing out notes for {clean_name}"
            body = (
                f"Hi {clean_name} team,\n\n"
                f"I assume you're heads-down running {clean_name} right now and upgrading the website or booking system isn't a priority at the moment—totally understand!\n\n"
                f"I won't clutter your inbox with any more follow-ups. If you ever decide in the future that you'd like to revamp your web presence, launch a custom mobile app, or add direct online ordering, feel free to keep my contact information handy.\n\n"
                f"Wishing you and the {clean_name} team continued success!\n\n"
                f"Warm regards,\n"
                f"Zai Ebad\n"
                f"Independent Full-Stack Developer\n"
                f"WhatsApp / Direct: +92 329 3246454 (03293246454)\n"
                f"Email: zaiebad56@gmail.com"
            )

        return {"subject": subject, "body": body}

    # -------------------------------------------------------------------------
    # 2. 24/7 AUTONOMOUS AI SALES AGENT (REPLY + INTENT + SELF-LEARNING)
    # -------------------------------------------------------------------------
    async def generate_sales_reply(
        self,
        lead: Dict[str, Any],
        incoming_message: str,
        channel: str,
        history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        knowledge = settings.get_knowledge_base()
        formatted_history = "\n".join(
            [f"[{m.get('sender')} - {m.get('created_at')}]: {m.get('message_text')}" for m in history[-10:]]
        )

        prompt = f"""
You are the 24/7 Autonomous AI Sales Agent for "{settings.AGENCY_NAME}" (Founder: {settings.SENDER_NAME}).
A prospect just replied to our outreach on {channel}.

PROSPECT DETAILS:
- Business Name: {lead.get("business_name")}
- Category: {lead.get("category")}
- Website: {lead.get("website") or "No Website"}
- Audit Report Summary: {lead.get("audit_report_json", "")[:600]}

AGENCY KNOWLEDGE BASE & PRICING RULES:
{knowledge}

CALL SCHEDULING INSTRUCTION:
{settings.CALENDAR_BOOKING_LINK}

CONVERSATION HISTORY:
{formatted_history}

LATEST INCOMING MESSAGE FROM CLIENT:
"{incoming_message}"

YOUR TASK:
1. Classify the client's intent into ONE of:
   - "DEAL_WON": The client explicitly agreed to proceed, confirmed they want to work with us, asked to start work, asked for an invoice/contract/onboarding, or agreed to hire us (e.g. "let's do it", "let's start", "proceed", "send invoice", "I'm ready", "let's work together", "when can you start", "ready to move forward").
   - "HOT_LEAD": Real human client is interested, wants a call/meeting/demo/preview, asks for pricing/quote, or asks how to proceed.
   - "QUESTION": Real client is asking a specific question about features, timeline, portfolio, or what we found.
   - "OBJECTION": Real client says they are busy, already have a developer, or budget is tight (handle gracefully, explain 0% commission & free interactive preview to overcome objection).
   - "AUTO_REPLY": Automated bot/system responder, office hours info, confirmation receipt, or out-of-office notice. Set should_send_reply to FALSE so we do not spam their auto-responder bot.
   - "NOT_INTERESTED": Client explicitly asks to unsubscribe, stop messaging, or says firmly not interested.
2. Write a natural, warm, human-style reply in fluent, professional English suitable for {channel} signed by {settings.SENDER_NAME}.
   - If intent is "DEAL_WON", express genuine excitement, confirm that our team is preparing their project kickoff roadmap immediately, and provide next steps or ask for any specific brand assets/preferences.
   - If intent is "AUTO_REPLY" or "NOT_INTERESTED", set should_send_reply to false.
   - If intent is "HOT_LEAD" or they ask for pricing/call, include transparent ballpark pricing from the Knowledge Base AND ask what day/time works best for a quick 10-minute Google Meet or phone call.
3. Formulate 1 short "learned_insight" about what worked or what this business segment cares about so our AI system self-learns over time.

RETURN ONLY VALID JSON:
{{
  "intent": "DEAL_WON" | "HOT_LEAD" | "QUESTION" | "OBJECTION" | "NOT_INTERESTED" | "AUTO_REPLY",
  "should_send_reply": true | false,
  "reply_subject": "Re: Quick idea for {lead.get('business_name')}",
  "reply_message": "Your human-like response text",
  "learned_insight": "1-sentence sales learning from this interaction"
}}
"""
        raw = await self.generate(prompt, use_complex_model=False, temperature=0.35)
        parsed = self._extract_json(raw)
        if parsed and "reply_message" in parsed:
            return parsed

        msg_lower = incoming_message.lower()
        if any(w in msg_lower for w in ["unsubscribe", "stop", "remove me", "not interested", "no thanks"]):
            return {
                "intent": "NOT_INTERESTED",
                "should_send_reply": False,
                "reply_subject": f"Re: {lead.get('business_name')}",
                "reply_message": "",
                "learned_insight": f"{lead.get('category')} prospect declined outreach; respect opt-out immediately.",
            }

        # Check for automated bot / out-of-office autoreponders
        auto_responder_triggers = [
            "thank you for inquiring",
            "thank you for contacting",
            "thank you for reaching out to",
            "automatic reply",
            "auto-reply",
            "out of office",
            "our business hours are",
            "our dinner hours are",
            "will respond to you within",
            "will get back to you within",
            "is part of the verity group",
        ]
        if any(trig in msg_lower for trig in auto_responder_triggers):
            return {
                "intent": "AUTO_REPLY",
                "should_send_reply": False,
                "reply_subject": f"Re: {lead.get('business_name')}",
                "reply_message": "",
                "learned_insight": f"{lead.get('business_name')} has an active corporate auto-responder; waiting for human team follow-up.",
            }

        deal_won_triggers = [
            "let's do it", "lets do it", "let's start", "lets start",
            "start work", "proceed", "send invoice", "send contract",
            "deal", "i'm ready", "im ready", "when can you begin",
            "when can you start", "agreed", "let's work together",
            "lets work together", "sign me up", "how to pay", "we want to hire you",
            "ready to move forward", "let's move forward", "let's proceed"
        ]
        is_deal_won = any(trig in msg_lower for trig in deal_won_triggers)

        if is_deal_won:
            reply_text = (
                f"Fantastic news, {lead.get('business_name')} team! I'm thrilled to work together on this.\n\n"
                f"I have personally notified our engineering team and we are preparing your project kickoff roadmap right now. "
                f"I will send over the onboarding agreement and milestones shortly so we can begin immediately.\n\n"
                f"Looking forward to building something incredible for {lead.get('business_name')}!\n\n"
                f"Warm regards,\n{settings.SENDER_NAME}\n{settings.AGENCY_NAME}\nDirect: {settings.AGENCY_OWNER_WHATSAPP}"
            )
            return {
                "intent": "DEAL_WON",
                "should_send_reply": True,
                "reply_subject": f"Welcome aboard {lead.get('business_name')} — Project Kickoff Confirmed!",
                "reply_message": reply_text,
                "learned_insight": f"{lead.get('business_name')} confirmed deal to proceed with project work! Kickoff initiated.",
            }

        is_hot = any(
            w in msg_lower
            for w in [
                "call",
                "meet",
                "zoom",
                "price",
                "cost",
                "quote",
                "how much",
                "interested",
                "yes",
                "sure",
                "send",
                "preview",
                "demo",
                "book",
                "schedule",
            ]
        )
        intent = "HOT_LEAD" if is_hot else "QUESTION"
        reply_text = (
            f"Thanks so much for getting back to me, {lead.get('business_name')} team!\n\n"
            f"For a custom mobile-ready website & commission-free online ordering/booking setup tailored to {lead.get('business_name')}, "
            f"our packages typically range from $399 to $999 (one-time investment, delivered in 5–10 days with 45 days of free support).\n\n"
            f"I'd love to walk you through the live concept preview on a quick 10-minute Google Meet or phone call. "
            f"What day and time works best for you this week? Just reply with a time that suits you and I'll send the invite right over!\n\n"
            f"Best regards,\n{settings.SENDER_NAME}\n{settings.AGENCY_NAME}"
        )
        return {
            "intent": intent,
            "should_send_reply": True,
            "reply_subject": f"Re: Quick idea for {lead.get('business_name')}",
            "reply_message": reply_text,
            "learned_insight": f"Prospects in {lead.get('category')} respond positively when offered a concrete preview & transparent pricing range.",
        }

    # -------------------------------------------------------------------------
    # 3. DYNAMIC LIVE HTML VISUAL MOCKUP & PROPOSAL GENERATOR
    # -------------------------------------------------------------------------
    async def generate_visual_mockup_data(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Generate tailored copy (hero headline, subheadline, 3 features, CTA) for a custom client preview page."""
        bname = lead.get("business_name", "Your Business")
        cat = lead.get("category", "Local Business")
        loc = lead.get("location", "Your City")
        prompt = f"""
Create high-converting landing page mockup copy for a local business:
- Business Name: {bname}
- Category: {cat}
- Location: {loc}

Return ONLY valid JSON:
{{
  "hero_badge": "Top-Rated {cat} in {loc}",
  "hero_headline": "Compelling 6-8 word headline for {bname}",
  "hero_subheadline": "1-2 sentence persuasive subheadline highlighting quality & instant online ordering/booking",
  "primary_cta": "Order Online / Book Now (0% Commission)",
  "secondary_cta": "View Menu & Specials",
  "features": [
    {{"title": "Feature 1 Title", "desc": "Short benefit description"}},
    {{"title": "Feature 2 Title", "desc": "Short benefit description"}},
    {{"title": "Feature 3 Title", "desc": "Short benefit description"}}
  ]
}}
"""
        raw = await self.generate(prompt, use_complex_model=False, temperature=0.5)
        parsed = self._extract_json(raw)
        if parsed and "hero_headline" in parsed:
            return parsed

        return {
            "hero_badge": f"★ {lead.get('rating') or 4.8} Rated {cat} in {loc}",
            "hero_headline": f"Experience the Best of {bname} — Now Online",
            "hero_subheadline": f"Order directly or book your spot in seconds from any mobile device with zero third-party fees.",
            "primary_cta": "Order / Book Online Now",
            "secondary_cta": "Chat on WhatsApp",
            "features": [
                {"title": "Instant Mobile Ordering & Booking", "desc": "1-click mobile checkout designed to convert local visitors into repeat customers."},
                {"title": "100% Commission-Free Direct Sales", "desc": "Save 20–30% on third-party delivery & booking app commissions."},
                {"title": "24/7 Automated WhatsApp & SMS Alerts", "desc": "Instant order confirmations and customer loyalty rewards built in."},
            ],
        }


ai_engine = AIEngine()
