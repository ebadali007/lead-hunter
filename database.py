import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from config import settings


class DatabaseManager:
    """SQLite Database Manager for Lead Hunter AI Automation System."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or settings.DATABASE_PATH)
        self.init_db()

    @contextmanager
    def get_conn(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self):
        """Create all required tables: leads, outreach_logs, conversations, daily_reports, activity_logs."""
        with self.get_conn() as conn:
            cursor = conn.cursor()

            # 1. LEADS TABLE
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    business_name TEXT NOT NULL,
                    category TEXT DEFAULT '',
                    location TEXT DEFAULT '',
                    phone TEXT DEFAULT '',
                    email TEXT DEFAULT '',
                    website TEXT DEFAULT '',
                    place_url TEXT DEFAULT '',
                    address TEXT DEFAULT '',
                    rating REAL DEFAULT 0.0,
                    reviews_count INTEGER DEFAULT 0,
                    reviews_snippet TEXT DEFAULT '',
                    has_website INTEGER DEFAULT 0,
                    priority TEXT DEFAULT 'MEDIUM',
                    audit_score INTEGER DEFAULT 0,
                    audit_report_json TEXT DEFAULT '{}',
                    draft_email_subject TEXT DEFAULT '',
                    draft_email_body TEXT DEFAULT '',
                    draft_whatsapp_msg TEXT DEFAULT '',
                    email_sent INTEGER DEFAULT 0,
                    whatsapp_sent INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'NEW',
                    is_hot_lead INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

            # 2. OUTREACH LOGS TABLE
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS outreach_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id INTEGER NOT NULL,
                    channel TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    subject TEXT DEFAULT '',
                    message_body TEXT NOT NULL,
                    delivery_status TEXT DEFAULT 'SENT',
                    error_message TEXT DEFAULT '',
                    sent_date TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (lead_id) REFERENCES leads (id) ON DELETE CASCADE
                )
                """
            )

            # 3. CONVERSATIONS TABLE (24/7 AI Sales Agent & Self-Learning)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id INTEGER NOT NULL,
                    channel TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    sender_address TEXT DEFAULT '',
                    message_text TEXT NOT NULL,
                    detected_intent TEXT DEFAULT 'GENERAL',
                    external_msg_id TEXT DEFAULT '',
                    learned_insight TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (lead_id) REFERENCES leads (id) ON DELETE CASCADE
                )
                """
            )

            # 4. DAILY REPORTS TABLE (End-of-Day Summary Analytics)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_date TEXT UNIQUE NOT NULL,
                    leads_scraped INTEGER DEFAULT 0,
                    high_priority_leads INTEGER DEFAULT 0,
                    emails_sent INTEGER DEFAULT 0,
                    whatsapps_sent INTEGER DEFAULT 0,
                    replies_received INTEGER DEFAULT 0,
                    hot_leads_count INTEGER DEFAULT 0,
                    summary_markdown TEXT DEFAULT '',
                    emailed_to_owner INTEGER DEFAULT 0,
                    whatsapped_to_owner INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )

            # 5. ACTIVITY LOGS TABLE (Live Dashboard Stream)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS activity_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL,
                    module TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

            # 6. CUSTOMER PORTAL ORDERS & CALL BOOKINGS TABLE
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS customer_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id INTEGER DEFAULT 0,
                    business_name TEXT NOT NULL,
                    customer_name TEXT DEFAULT '',
                    customer_email TEXT DEFAULT '',
                    customer_phone TEXT DEFAULT '',
                    selected_package TEXT NOT NULL,
                    budget_range TEXT DEFAULT '',
                    preferred_call_time TEXT DEFAULT '',
                    project_notes TEXT DEFAULT '',
                    status TEXT DEFAULT 'NEW_BOOKING',
                    created_at TEXT NOT NULL
                )
                """
            )

            # 7. AUTOPILOT STATE & LOCATION/CATEGORY ROTATION TABLE
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS autopilot_state (
                    id INTEGER PRIMARY KEY,
                    rotation_index INTEGER DEFAULT 0,
                    current_city TEXT DEFAULT '',
                    current_category TEXT DEFAULT '',
                    total_cycles_completed INTEGER DEFAULT 0,
                    last_run_at TEXT DEFAULT '',
                    is_enabled INTEGER DEFAULT 1,
                    daily_quota_target INTEGER DEFAULT 60
                )
                """
            )
            # Ensure row 1 exists
            cursor.execute(
                "INSERT OR IGNORE INTO autopilot_state (id, rotation_index, current_city, current_category, total_cycles_completed, is_enabled, daily_quota_target) VALUES (1, 0, 'New York, NY, USA', 'Restaurants', 0, 1, 60)"
            )

            # Indexes for fast duplicate lookup & dashboard queries
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_name_phone ON leads(business_name, phone);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_website ON leads(website);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_outreach_sent_date ON outreach_logs(sent_date, channel);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conv_lead_id ON conversations(lead_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conv_ext_id ON conversations(external_msg_id);")

            # Safe migration: add screenshot & owner-report columns to existing databases
            existing_cols = {row[1] for row in cursor.execute("PRAGMA table_info(leads)").fetchall()}
            new_columns = {
                "screenshot_desktop": "TEXT DEFAULT ''",
                "screenshot_mobile": "TEXT DEFAULT ''",
                "maps_screenshot": "TEXT DEFAULT ''",
                "owner_report_sent": "INTEGER DEFAULT 0",
                "owner_report_sent_at": "TEXT DEFAULT ''",
            }
            for col_name, col_def in new_columns.items():
                if col_name not in existing_cols:
                    cursor.execute(f"ALTER TABLE leads ADD COLUMN {col_name} {col_def}")

    # -------------------------------------------------------------------------
    # ACTIVITY LOGGING
    # -------------------------------------------------------------------------
    def log_activity(self, level: str, module: str, message: str) -> Dict[str, Any]:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Clear terminal log line for debugging (safe on Windows consoles without UTF-8)
        line = f"[{now}] [{level.upper():<8}] [{module.upper():<12}] {message}"
        try:
            print(line, flush=True)
        except UnicodeEncodeError:
            print(line.encode("ascii", errors="replace").decode("ascii"), flush=True)
        with self.get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO activity_logs (level, module, message, created_at) VALUES (?, ?, ?, ?)",
                (level.upper(), module.upper(), message, now),
            )
            return {
                "id": cur.lastrowid,
                "level": level.upper(),
                "module": module.upper(),
                "message": message,
                "created_at": now,
            }

    def get_recent_logs(self, limit: int = 80) -> List[Dict[str, Any]]:
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM activity_logs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    # -------------------------------------------------------------------------
    # DUPLICATE CHECK & LEAD MANAGEMENT
    # -------------------------------------------------------------------------
    def is_duplicate_lead(self, business_name: str, phone: str = "", website: str = "", place_url: str = "") -> bool:
        """Check if a business is already stored in SQLite to skip duplicates."""
        name_clean = (business_name or "").strip().lower()
        phone_clean = "".join(ch for ch in (phone or "") if ch.isdigit())
        website_clean = (website or "").strip().lower().rstrip("/")
        place_clean = (place_url or "").strip()

        with self.get_conn() as conn:
            if place_clean:
                row = conn.execute(
                    "SELECT id FROM leads WHERE place_url = ? AND place_url != '' LIMIT 1",
                    (place_clean,),
                ).fetchone()
                if row:
                    return True

            if name_clean and phone_clean and len(phone_clean) >= 7:
                rows = conn.execute(
                    "SELECT phone FROM leads WHERE LOWER(business_name) = ?",
                    (name_clean,),
                ).fetchall()
                for r in rows:
                    existing_digits = "".join(ch for ch in (r["phone"] or "") if ch.isdigit())
                    if existing_digits and existing_digits[-7:] == phone_clean[-7:]:
                        return True

            if website_clean and len(website_clean) > 8:
                row = conn.execute(
                    "SELECT id FROM leads WHERE LOWER(TRIM(website, '/')) = ? LIMIT 1",
                    (website_clean,),
                ).fetchone()
                if row:
                    return True

            if name_clean:
                row = conn.execute(
                    "SELECT id FROM leads WHERE LOWER(business_name) = ? LIMIT 1",
                    (name_clean,),
                ).fetchone()
                if row:
                    return True

        return False

    def insert_lead(self, lead_data: Dict[str, Any]) -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        website = (lead_data.get("website") or "").strip()
        has_website = 1 if website else 0
        priority = lead_data.get("priority") or ("HIGH_PRIORITY" if not has_website else "MEDIUM")

        with self.get_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO leads (
                    business_name, category, location, phone, email, website,
                    place_url, address, rating, reviews_count, reviews_snippet,
                    has_website, priority, audit_score, audit_report_json,
                    status, maps_screenshot, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lead_data.get("business_name", "").strip(),
                    lead_data.get("category", "").strip(),
                    lead_data.get("location", "").strip(),
                    lead_data.get("phone", "").strip(),
                    lead_data.get("email", "").strip(),
                    website,
                    lead_data.get("place_url", "").strip(),
                    lead_data.get("address", "").strip(),
                    float(lead_data.get("rating") or 0.0),
                    int(lead_data.get("reviews_count") or 0),
                    lead_data.get("reviews_snippet", "").strip(),
                    has_website,
                    priority,
                    int(lead_data.get("audit_score") or 0),
                    json.dumps(lead_data.get("audit_report") or {}, ensure_ascii=False),
                    lead_data.get("status", "NEW"),
                    lead_data.get("maps_screenshot", "") or "",
                    now,
                    now,
                ),
            )
            return cur.lastrowid

    def update_lead_media(self, lead_id: int, screenshot_desktop: str, screenshot_mobile: str, maps_screenshot: str = ""):
        """Persist captured screenshot paths so the Dashboard and owner report can show them."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.get_conn() as conn:
            conn.execute(
                """
                UPDATE leads
                SET screenshot_desktop = ?, screenshot_mobile = ?,
                    maps_screenshot = CASE WHEN ? != '' THEN ? ELSE maps_screenshot END,
                    updated_at = ?
                WHERE id = ?
                """,
                (screenshot_desktop or "", screenshot_mobile or "", maps_screenshot or "", maps_screenshot or "", now, lead_id),
            )

    def mark_owner_report_sent(self, lead_id: int):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.get_conn() as conn:
            conn.execute(
                "UPDATE leads SET owner_report_sent = 1, owner_report_sent_at = ? WHERE id = ?",
                (now, lead_id),
            )

    def get_weekly_activity(self) -> Dict[str, Any]:
        """Real per-day counts for the last 7 days (powers the Dashboard bar charts)."""
        from datetime import timedelta

        days = [(datetime.now() - timedelta(days=offset)) for offset in range(6, -1, -1)]
        labels, leads_counts, outreach_counts = [], [], []
        with self.get_conn() as conn:
            for d in days:
                day_str = d.strftime("%Y-%m-%d")
                labels.append(d.strftime("%a"))
                leads_counts.append(
                    conn.execute(
                        "SELECT COUNT(*) AS c FROM leads WHERE created_at LIKE ?", (f"{day_str}%",)
                    ).fetchone()["c"]
                )
                outreach_counts.append(
                    conn.execute(
                        "SELECT COUNT(*) AS c FROM outreach_logs WHERE sent_date = ? AND delivery_status = 'SENT'",
                        (day_str,),
                    ).fetchone()["c"]
                )
        return {"labels": labels, "leads": leads_counts, "outreach": outreach_counts}

    def update_lead_audit_and_drafts(
        self,
        lead_id: int,
        priority: str,
        audit_score: int,
        audit_report: Dict[str, Any],
        email_subject: str,
        email_body: str,
        whatsapp_msg: str,
        extracted_email: Optional[str] = None,
    ):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.get_conn() as conn:
            if extracted_email:
                conn.execute(
                    """
                    UPDATE leads
                    SET priority = ?, audit_score = ?, audit_report_json = ?,
                        draft_email_subject = ?, draft_email_body = ?, draft_whatsapp_msg = ?,
                        email = CASE WHEN email = '' THEN ? ELSE email END,
                        status = CASE WHEN status = 'NEW' THEN 'AUDITED' ELSE status END,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        priority,
                        int(audit_score),
                        json.dumps(audit_report, ensure_ascii=False),
                        email_subject,
                        email_body,
                        whatsapp_msg,
                        extracted_email.strip(),
                        now,
                        lead_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE leads
                    SET priority = ?, audit_score = ?, audit_report_json = ?,
                        draft_email_subject = ?, draft_email_body = ?, draft_whatsapp_msg = ?,
                        status = CASE WHEN status = 'NEW' THEN 'AUDITED' ELSE status END,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        priority,
                        int(audit_score),
                        json.dumps(audit_report, ensure_ascii=False),
                        email_subject,
                        email_body,
                        whatsapp_msg,
                        now,
                        lead_id,
                    ),
                )

    def get_leads(
        self,
        status_filter: Optional[str] = None,
        priority_filter: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 250,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM leads WHERE 1=1"
        params: List[Any] = []
        if status_filter and status_filter != "ALL":
            if status_filter == "EMAIL_SENT":
                query += " AND email_sent = 1"
            elif status_filter == "WA_SENT":
                query += " AND whatsapp_sent = 1"
            elif status_filter == "HIGH_SCORE":
                query += " AND audit_score >= 70"
            elif status_filter == "HOT_LEAD":
                query += " AND (is_hot_lead = 1 OR status = 'HOT_LEAD')"
            else:
                query += " AND status = ?"
                params.append(status_filter)
        if priority_filter and priority_filter != "ALL":
            if priority_filter == "HIGH_PRIORITY":
                query += " AND (priority IN ('HIGH_PRIORITY', 'HIGH') OR has_website = 0)"
            else:
                query += " AND priority = ?"
                params.append(priority_filter)
        if search and search.strip():
            s = f"%{search.strip().lower()}%"
            query += " AND (LOWER(business_name) LIKE ? OR LOWER(location) LIKE ? OR LOWER(category) LIKE ? OR LOWER(email) LIKE ? OR LOWER(phone) LIKE ?)"
            params.extend([s, s, s, s, s])
        query += " ORDER BY is_hot_lead DESC, id DESC LIMIT ?"
        params.append(limit)

        with self.get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                try:
                    d["audit_report"] = json.loads(d.get("audit_report_json") or "{}")
                except Exception:
                    d["audit_report"] = {}
                result.append(d)
            return result

    def get_lead_by_id(self, lead_id: int) -> Optional[Dict[str, Any]]:
        with self.get_conn() as conn:
            row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            try:
                d["audit_report"] = json.loads(d.get("audit_report_json") or "{}")
            except Exception:
                d["audit_report"] = {}
            return d

    def update_lead_contact(self, lead_id: int, email: str, phone: str, website: str):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.get_conn() as conn:
            conn.execute(
                """
                UPDATE leads
                SET email = ?, phone = ?, website = ?, has_website = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    email.strip(),
                    phone.strip(),
                    website.strip(),
                    1 if website.strip() else 0,
                    now,
                    lead_id,
                ),
            )

    def delete_lead(self, lead_id: int):
        with self.get_conn() as conn:
            conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))

    def find_lead_by_contact(self, email_or_phone: str) -> Optional[Dict[str, Any]]:
        """Match incoming Gmail IMAP reply or WhatsApp message to an existing lead."""
        val = (email_or_phone or "").strip().lower()
        if not val:
            return None
        with self.get_conn() as conn:
            if "@" in val:
                row = conn.execute(
                    "SELECT * FROM leads WHERE LOWER(email) = ? LIMIT 1", (val,)
                ).fetchone()
                if row:
                    return dict(row)
            digits = "".join(ch for ch in val if ch.isdigit())
            if len(digits) >= 7:
                rows = conn.execute("SELECT * FROM leads WHERE phone != ''").fetchall()
                for r in rows:
                    lead_digits = "".join(ch for ch in (r["phone"] or "") if ch.isdigit())
                    if lead_digits and lead_digits[-7:] == digits[-7:]:
                        return dict(r)
            # Also try matching by business name for WhatsApp chat title
            row = conn.execute(
                "SELECT * FROM leads WHERE LOWER(business_name) = ? LIMIT 1", (val,)
            ).fetchone()
            if row:
                return dict(row)
        return None

    # -------------------------------------------------------------------------
    # OUTREACH & DAILY LIMITS
    # -------------------------------------------------------------------------
    def record_outreach(
        self,
        lead_id: int,
        channel: str,
        recipient: str,
        subject: str,
        message_body: str,
        delivery_status: str = "SENT",
        error_message: str = "",
    ):
        now = datetime.now()
        sent_date = now.strftime("%Y-%m-%d")
        created_at = now.strftime("%Y-%m-%d %H:%M:%S")
        channel_up = channel.upper()

        with self.get_conn() as conn:
            conn.execute(
                """
                INSERT INTO outreach_logs (
                    lead_id, channel, recipient, subject, message_body,
                    delivery_status, error_message, sent_date, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lead_id,
                    channel_up,
                    recipient,
                    subject,
                    message_body,
                    delivery_status,
                    error_message,
                    sent_date,
                    created_at,
                ),
            )
            if delivery_status in ("SENT", "SIMULATED"):
                if channel_up == "EMAIL":
                    conn.execute(
                        "UPDATE leads SET email_sent = 1, status = CASE WHEN status IN ('NEW','AUDITED') THEN 'CONTACTED' ELSE status END, updated_at = ? WHERE id = ?",
                        (created_at, lead_id),
                    )
                elif channel_up == "WHATSAPP":
                    conn.execute(
                        "UPDATE leads SET whatsapp_sent = 1, status = CASE WHEN status IN ('NEW','AUDITED') THEN 'CONTACTED' ELSE status END, updated_at = ? WHERE id = ?",
                        (created_at, lead_id),
                    )
                # Also store outreach message in conversation history
                conn.execute(
                    """
                    INSERT INTO conversations (
                        lead_id, channel, sender, sender_address, message_text,
                        detected_intent, external_msg_id, created_at
                    ) VALUES (?, ?, 'AI_AGENT', ?, ?, 'OUTREACH', '', ?)
                    """,
                    (lead_id, channel_up, recipient, message_body, created_at),
                )

    def get_today_outreach_counts(self) -> Dict[str, int]:
        today = datetime.now().strftime("%Y-%m-%d")
        with self.get_conn() as conn:
            email_count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM outreach_logs WHERE sent_date = ? AND channel = 'EMAIL' AND delivery_status IN ('SENT', 'SIMULATED')",
                (today,),
            ).fetchone()["cnt"]
            wa_count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM outreach_logs WHERE sent_date = ? AND channel = 'WHATSAPP' AND delivery_status IN ('SENT', 'SIMULATED')",
                (today,),
            ).fetchone()["cnt"]
            return {"emails_today": email_count, "whatsapps_today": wa_count}

    def get_outreach_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self.get_conn() as conn:
            rows = conn.execute(
                """
                SELECT o.*, l.business_name
                FROM outreach_logs o
                LEFT JOIN leads l ON o.lead_id = l.id
                ORDER BY o.id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    # -------------------------------------------------------------------------
    # CONVERSATIONS & HOT LEADS
    # -------------------------------------------------------------------------
    def is_message_processed(self, external_msg_id: str) -> bool:
        if not external_msg_id:
            return False
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT id FROM conversations WHERE external_msg_id = ? LIMIT 1",
                (external_msg_id,),
            ).fetchone()
            return bool(row)

    def add_conversation_message(
        self,
        lead_id: int,
        channel: str,
        sender: str,
        sender_address: str,
        message_text: str,
        detected_intent: str = "GENERAL",
        external_msg_id: str = "",
        learned_insight: str = "",
    ) -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.get_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO conversations (
                    lead_id, channel, sender, sender_address, message_text,
                    detected_intent, external_msg_id, learned_insight, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lead_id,
                    channel.upper(),
                    sender.upper(),
                    sender_address,
                    message_text,
                    detected_intent.upper(),
                    external_msg_id,
                    learned_insight,
                    now,
                ),
            )
            if sender.upper() == "CLIENT":
                new_status = "REPLIED"
                is_hot = 0
                if detected_intent.upper() == "HOT_LEAD":
                    new_status = "HOT_LEAD"
                    is_hot = 1
                elif detected_intent.upper() == "NOT_INTERESTED":
                    new_status = "NOT_INTERESTED"
                elif detected_intent.upper() == "AUTO_REPLY":
                    new_status = "CONTACTED"

                conn.execute(
                    """
                    UPDATE leads
                    SET status = CASE WHEN is_hot_lead = 1 AND ? != 'AUTO_REPLY' THEN 'HOT_LEAD' ELSE ? END,
                        is_hot_lead = CASE WHEN ? = 'AUTO_REPLY' THEN 0 WHEN is_hot_lead = 1 OR ? = 1 THEN 1 ELSE 0 END,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (detected_intent.upper(), new_status, detected_intent.upper(), is_hot, now, lead_id),
                )
            return cur.lastrowid

    def get_lead_conversation(self, lead_id: int) -> List[Dict[str, Any]]:
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM conversations WHERE lead_id = ? ORDER BY id ASC",
                (lead_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_conversations_grouped(self) -> List[Dict[str, Any]]:
        """Return leads that have conversation history with their messages."""
        with self.get_conn() as conn:
            lead_rows = conn.execute(
                """
                SELECT DISTINCT l.*
                FROM leads l
                INNER JOIN conversations c ON l.id = c.lead_id
                ORDER BY l.is_hot_lead DESC, l.updated_at DESC
                """
            ).fetchall()
            grouped = []
            for lr in lead_rows:
                lead_dict = dict(lr)
                msgs = conn.execute(
                    "SELECT * FROM conversations WHERE lead_id = ? ORDER BY id ASC",
                    (lead_dict["id"],),
                ).fetchall()
                lead_dict["messages"] = [dict(m) for m in msgs]
                grouped.append(lead_dict)
            return grouped

    # -------------------------------------------------------------------------
    # END-OF-DAY (EOD) ANALYTICS & SUMMARY REPORTS
    # -------------------------------------------------------------------------
    def get_dashboard_stats(self) -> Dict[str, Any]:
        today = datetime.now().strftime("%Y-%m-%d")
        today_dow = int(datetime.now().strftime("%w"))
        with self.get_conn() as conn:
            total_leads = conn.execute("SELECT COUNT(*) AS c FROM leads").fetchone()["c"]
            today_leads = conn.execute(
                "SELECT COUNT(*) AS c FROM leads WHERE created_at LIKE ?", (f"{today}%",)
            ).fetchone()["c"]
            high_priority = conn.execute(
                "SELECT COUNT(*) AS c FROM leads WHERE priority IN ('HIGH_PRIORITY', 'HIGH') OR has_website = 0"
            ).fetchone()["c"]
            hot_leads = conn.execute(
                "SELECT COUNT(*) AS c FROM leads WHERE is_hot_lead = 1 OR status = 'HOT_LEAD'"
            ).fetchone()["c"]
            emails_today = conn.execute(
                "SELECT COUNT(*) AS c FROM outreach_logs WHERE sent_date = ? AND channel = 'EMAIL' AND delivery_status IN ('SENT','SIMULATED')",
                (today,),
            ).fetchone()["c"]
            wa_today = conn.execute(
                "SELECT COUNT(*) AS c FROM outreach_logs WHERE sent_date = ? AND channel = 'WHATSAPP' AND delivery_status IN ('SENT','SIMULATED')",
                (today,),
            ).fetchone()["c"]
            total_emails_sent = conn.execute(
                "SELECT COUNT(*) AS c FROM leads WHERE email_sent = 1"
            ).fetchone()["c"]
            total_wa_sent = conn.execute(
                "SELECT COUNT(*) AS c FROM leads WHERE whatsapp_sent = 1"
            ).fetchone()["c"]
            total_high_score = conn.execute(
                "SELECT COUNT(*) AS c FROM leads WHERE audit_score >= 70"
            ).fetchone()["c"]
            replies_today = conn.execute(
                "SELECT COUNT(*) AS c FROM conversations WHERE sender = 'CLIENT' AND created_at LIKE ?",
                (f"{today}%",),
            ).fetchone()["c"]
            total_replies = conn.execute(
                "SELECT COUNT(*) AS c FROM conversations WHERE sender = 'CLIENT'"
            ).fetchone()["c"]

            # Dynamic 7-Day Trend Bars (Sun=0 .. Sat=6)
            leads_dow = {i: 0 for i in range(7)}
            for r in conn.execute("SELECT strftime('%w', created_at) as dow, count(*) FROM leads GROUP BY dow").fetchall():
                if r[0] is not None:
                    try:
                        leads_dow[int(r[0])] = r[1]
                    except Exception:
                        pass

            outreach_dow = {i: 0 for i in range(7)}
            for r in conn.execute("SELECT strftime('%w', created_at) as dow, count(*) FROM outreach_logs GROUP BY dow").fetchall():
                if r[0] is not None:
                    try:
                        outreach_dow[int(r[0])] = r[1]
                    except Exception:
                        pass

            # Dynamic Percentage Change
            yesterday_dow = (today_dow - 1) % 7
            prev_leads = leads_dow.get(yesterday_dow, 0)
            cur_leads = leads_dow.get(today_dow, today_leads)
            if prev_leads > 0:
                lead_pct = round(((cur_leads - prev_leads) / prev_leads) * 100, 1)
                lead_growth = f"{'+' if lead_pct >= 0 else ''}{lead_pct}%"
            else:
                lead_growth = f"+{min(100, cur_leads * 12)}%"

            prev_outreach = outreach_dow.get(yesterday_dow, 0)
            cur_outreach = outreach_dow.get(today_dow, emails_today + wa_today)
            if prev_outreach > 0:
                out_pct = round(((cur_outreach - prev_outreach) / prev_outreach) * 100, 1)
                outreach_growth = f"{'+' if out_pct >= 0 else ''}{out_pct}%"
            else:
                outreach_growth = f"+{min(100, cur_outreach * 10)}%"

            return {
                "date": today,
                "current_dow": today_dow,
                "total_leads": total_leads,
                "today_leads": today_leads,
                "high_priority": high_priority,
                "hot_leads": hot_leads,
                "emails_today": emails_today,
                "daily_email_limit": settings.DAILY_EMAIL_LIMIT,
                "whatsapps_today": wa_today,
                "daily_whatsapp_limit": settings.DAILY_WHATSAPP_LIMIT,
                "replies_today": replies_today,
                "total_replies": total_replies,
                "leads_dow": leads_dow,
                "outreach_dow": outreach_dow,
                "lead_growth": lead_growth,
                "outreach_growth": outreach_growth,
                "filter_counts": {
                    "all": total_leads,
                    "high_priority": high_priority,
                    "hot": hot_leads,
                    "email_sent": total_emails_sent,
                    "wa_sent": total_wa_sent,
                    "high_score": total_high_score,
                },
            }

    def save_daily_report(
        self,
        report_date: str,
        stats: Dict[str, Any],
        summary_markdown: str,
        emailed: bool = False,
        whatsapped: bool = False,
    ) -> Dict[str, Any]:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.get_conn() as conn:
            conn.execute(
                """
                INSERT INTO daily_reports (
                    report_date, leads_scraped, high_priority_leads,
                    emails_sent, whatsapps_sent, replies_received,
                    hot_leads_count, summary_markdown,
                    emailed_to_owner, whatsapped_to_owner, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_date) DO UPDATE SET
                    leads_scraped = excluded.leads_scraped,
                    high_priority_leads = excluded.high_priority_leads,
                    emails_sent = excluded.emails_sent,
                    whatsapps_sent = excluded.whatsapps_sent,
                    replies_received = excluded.replies_received,
                    hot_leads_count = excluded.hot_leads_count,
                    summary_markdown = excluded.summary_markdown,
                    emailed_to_owner = MAX(daily_reports.emailed_to_owner, excluded.emailed_to_owner),
                    whatsapped_to_owner = MAX(daily_reports.whatsapped_to_owner, excluded.whatsapped_to_owner),
                    created_at = excluded.created_at
                """,
                (
                    report_date,
                    stats.get("today_leads", 0),
                    stats.get("high_priority", 0),
                    stats.get("emails_today", 0),
                    stats.get("whatsapps_today", 0),
                    stats.get("replies_today", 0),
                    stats.get("hot_leads", 0),
                    summary_markdown,
                    1 if emailed else 0,
                    1 if whatsapped else 0,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM daily_reports WHERE report_date = ?", (report_date,)
            ).fetchone()
            return dict(row) if row else {}

    def get_daily_reports(self, limit: int = 30) -> List[Dict[str, Any]]:
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM daily_reports ORDER BY report_date DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    # -------------------------------------------------------------------------
    # CUSTOMER PORTAL REQUESTS & BOOKINGS
    # -------------------------------------------------------------------------
    def create_customer_request(self, data: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lead_id = int(data.get("lead_id") or 0)
        with self.get_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO customer_requests (
                    lead_id, business_name, customer_name, customer_email,
                    customer_phone, selected_package, budget_range,
                    preferred_call_time, project_notes, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'NEW_BOOKING', ?)
                """,
                (
                    lead_id,
                    data.get("business_name", "Valued Client"),
                    data.get("customer_name", ""),
                    data.get("customer_email", ""),
                    data.get("customer_phone", ""),
                    data.get("selected_package", "Website & Online Ordering"),
                    data.get("budget_range", "$499 - $999"),
                    data.get("preferred_call_time", ""),
                    data.get("project_notes", ""),
                    now,
                ),
            )
            req_id = cur.lastrowid
            if lead_id > 0:
                conn.execute(
                    "UPDATE leads SET status = 'HOT_LEAD', is_hot_lead = 1, updated_at = ? WHERE id = ?",
                    (now, lead_id),
                )
            row = conn.execute("SELECT * FROM customer_requests WHERE id = ?", (req_id,)).fetchone()
            return dict(row) if row else {}

    def get_customer_requests(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM customer_requests ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_autopilot_state(self) -> Dict[str, Any]:
        with self.get_conn() as conn:
            row = conn.execute("SELECT * FROM autopilot_state WHERE id = 1").fetchone()
            if not row:
                conn.execute(
                    "INSERT OR IGNORE INTO autopilot_state (id, rotation_index, current_city, current_category, total_cycles_completed, is_enabled, daily_quota_target) VALUES (1, 0, 'New York, NY, USA', 'Restaurants', 0, 1, 60)"
                )
                row = conn.execute("SELECT * FROM autopilot_state WHERE id = 1").fetchone()
            return dict(row) if row else {}

    def update_autopilot_state(
        self,
        rotation_index: Optional[int] = None,
        current_city: Optional[str] = None,
        current_category: Optional[str] = None,
        cycles: Optional[int] = None,
        is_enabled: Optional[int] = None,
        daily_quota: Optional[int] = None,
    ) -> Dict[str, Any]:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.get_conn() as conn:
            cur_state = self.get_autopilot_state()
            new_idx = cur_state.get("rotation_index", 0) if rotation_index is None else rotation_index
            new_city = cur_state.get("current_city", "") if current_city is None else current_city
            new_cat = cur_state.get("current_category", "") if current_category is None else current_category
            new_cyc = cur_state.get("total_cycles_completed", 0) if cycles is None else cycles
            new_en = cur_state.get("is_enabled", 1) if is_enabled is None else is_enabled
            new_quota = cur_state.get("daily_quota_target", 60) if daily_quota is None else daily_quota

            conn.execute(
                """
                UPDATE autopilot_state SET
                    rotation_index = ?,
                    current_city = ?,
                    current_category = ?,
                    total_cycles_completed = ?,
                    last_run_at = ?,
                    is_enabled = ?,
                    daily_quota_target = ?
                WHERE id = 1
                """,
                (new_idx, new_city, new_cat, new_cyc, now, new_en, new_quota),
            )
            return self.get_autopilot_state()

    def mark_deal_won(self, lead_id: int, closing_note: str = "") -> bool:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.get_conn() as conn:
            conn.execute(
                """
                UPDATE leads SET
                    status = 'CLOSED_WON',
                    is_hot_lead = 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, lead_id),
            )
            conn.execute(
                """
                INSERT INTO activity_logs (level, module, message, created_at)
                VALUES ('HOT_LEAD', 'DEAL_CLOSER', ?, ?)
                """,
                (f"🎉 DEAL WON! Client #{lead_id} agreed to proceed: {closing_note[:120]}", now),
            )
            return True


db = DatabaseManager()

