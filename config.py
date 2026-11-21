import os
from pathlib import Path
from dotenv import load_dotenv, set_key

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
KNOWLEDGE_PATH = BASE_DIR / "agency_knowledge.txt"

load_dotenv(dotenv_path=ENV_PATH, override=True)


class Settings:
    """Centralized dynamic configuration loaded from .env with live reload support."""

    def __init__(self):
        self.reload()

    def reload(self):
        load_dotenv(dotenv_path=ENV_PATH, override=True)
        # AI Brain
        self.GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
        self.GEMINI_COMPLEX_MODEL: str = os.getenv("GEMINI_COMPLEX_MODEL", "gemini-3.8-flash").strip()
        self.GEMINI_FAST_MODEL: str = os.getenv("GEMINI_FAST_MODEL", "gemini-3.5-flash-lite").strip()
        self.GEMINI_FALLBACK_MODEL: str = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash").strip()

        self.GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "").strip()
        self.GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()

        # Gmail Automation
        self.GMAIL_ADDRESS: str = os.getenv("GMAIL_ADDRESS", "").strip()
        self.GMAIL_APP_PASSWORD: str = os.getenv("GMAIL_APP_PASSWORD", "").strip()
        self.SENDER_NAME: str = os.getenv("SENDER_NAME", "Apex Web & App Studio").strip()
        self.SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
        self.SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
        self.IMAP_HOST: str = os.getenv("IMAP_HOST", "imap.gmail.com").strip()
        self.IMAP_PORT: int = int(os.getenv("IMAP_PORT", "993"))

        # Agency & Booking Details
        self.AGENCY_NAME: str = os.getenv("AGENCY_NAME", "Apex Web & App Studio").strip()
        self.AGENCY_OWNER_EMAIL: str = os.getenv("AGENCY_OWNER_EMAIL", self.GMAIL_ADDRESS).strip()
        # Personal inbox that receives every lead's authentic details + audit + screenshots
        self.MY_PERSONAL_EMAIL: str = (
            os.getenv("MY_PERSONAL_EMAIL", "").strip() or self.AGENCY_OWNER_EMAIL or self.GMAIL_ADDRESS
        )
        self.SEND_LEAD_REPORTS_TO_OWNER: bool = os.getenv(
            "SEND_LEAD_REPORTS_TO_OWNER", "false"
        ).lower() in ("true", "1", "yes")
        self.AGENCY_OWNER_WHATSAPP: str = os.getenv("AGENCY_OWNER_WHATSAPP", "+923293246454").strip()
        self.CALENDAR_BOOKING_LINK: str = os.getenv(
            "CALENDAR_BOOKING_LINK", "https://calendly.com/your-agency/15min-discovery-call"
        ).strip()
        self.AGENCY_PORTFOLIO_URL: str = os.getenv(
            "AGENCY_PORTFOLIO_URL", "https://your-agency-portfolio.com"
        ).strip()

        # Anti-Spam & Safety Limits
        self.DAILY_EMAIL_LIMIT: int = int(os.getenv("DAILY_EMAIL_LIMIT", "60"))
        self.DAILY_WHATSAPP_LIMIT: int = int(os.getenv("DAILY_WHATSAPP_LIMIT", "45"))
        self.MIN_OUTREACH_DELAY_SECONDS: int = int(os.getenv("MIN_OUTREACH_DELAY_SECONDS", "60"))
        self.MAX_OUTREACH_DELAY_SECONDS: int = int(os.getenv("MAX_OUTREACH_DELAY_SECONDS", "140"))
        self.REPLY_CHECK_INTERVAL_MINUTES: int = int(os.getenv("REPLY_CHECK_INTERVAL_MINUTES", "5"))
        self.EOD_REPORT_TIME: str = os.getenv("EOD_REPORT_TIME", "20:00").strip()
        self.AUTOPILOT_ENABLED: bool = os.getenv("AUTOPILOT_ENABLED", "true").lower() in ("true", "1", "yes")

        # Playwright & Database
        self.HEADLESS_SCRAPER: bool = os.getenv("HEADLESS_SCRAPER", "true").lower() in ("true", "1", "yes")
        self.WHATSAPP_SESSION_DIR: Path = BASE_DIR / os.getenv("WHATSAPP_SESSION_DIR", "./whatsapp_session")
        self.DATABASE_PATH: Path = BASE_DIR / os.getenv("DATABASE_PATH", "./lead_hunter.db")
        self.SCREENSHOTS_DIR: Path = BASE_DIR / "screenshots"
        self.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        self.PORT: int = int(os.getenv("PORT", "8000"))

    def update_env(self, updates: dict):
        """Persist updated key-value settings to .env and reload."""
        if not ENV_PATH.exists():
            ENV_PATH.write_text("", encoding="utf-8")
        for key, value in updates.items():
            if value is not None:
                set_key(str(ENV_PATH), key, str(value))
        self.reload()

    def get_knowledge_base(self) -> str:
        """Read agency_knowledge.txt for the AI Sales Agent."""
        if KNOWLEDGE_PATH.exists():
            return KNOWLEDGE_PATH.read_text(encoding="utf-8")
        return "Agency Name: " + self.AGENCY_NAME

    def save_knowledge_base(self, content: str):
        """Overwrite agency_knowledge.txt from Dashboard UI."""
        KNOWLEDGE_PATH.write_text(content, encoding="utf-8")

    def append_self_learning_insight(self, insight: str):
        """Append new learned sales insight into agency_knowledge.txt."""
        current = self.get_knowledge_base()
        if insight.strip() and insight.strip() not in current:
            updated = current.rstrip() + f"\n- Learned Insight: {insight.strip()}\n"
            KNOWLEDGE_PATH.write_text(updated, encoding="utf-8")

    def is_gemini_configured(self) -> bool:
        return bool(self.GEMINI_API_KEY and self.GEMINI_API_KEY != "your_gemini_api_key_here")

    def is_groq_configured(self) -> bool:
        return bool(self.GROQ_API_KEY and self.GROQ_API_KEY != "your_groq_api_key_here")

    def is_gmail_configured(self) -> bool:
        return bool(
            self.GMAIL_ADDRESS
            and self.GMAIL_ADDRESS != "your_agency_email@gmail.com"
            and self.GMAIL_APP_PASSWORD
            and "xxxx" not in self.GMAIL_APP_PASSWORD
        )


settings = Settings()

