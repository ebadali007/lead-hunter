# 🚀 Lead Hunter AI Automation System ($0/Month Zero-Cost Stack)

A complete, autonomous **Lead Generation, Website Auditing, Cold Outreach (Gmail SMTP + WhatsApp Web), and 24/7 Self-Learning AI Sales Agent** built in **Pure Python (FastAPI + Playwright + SQLite)** for Website, Software & Mobile App Development Agencies.

---

## 📁 Project Folder Structure

```text
lead-hunter/
├── .env.example                 # Template for API keys, Gmail SMTP/IMAP, and limits
├── .env                         # Active environment config (Editable from Dashboard UI too!)
├── agency_knowledge.txt         # Agency services, pricing rules, portfolio & self-learned insights
├── requirements.txt             # Python dependencies
├── start_windows.bat            # One-Click Windows Launcher Script
├── config.py                    # Dynamic configuration & knowledge base manager
├── database.py                  # SQLite database engine (leads, outreach_logs, conversations, daily_reports)
├── main.py                      # FastAPI Server & REST API endpoints
├── workers/
│   ├── ai_engine.py             # Gemini Free Tier (gemini-3.8-flash & gemini-3.5-flash-lite) + Groq Backup
│   ├── maps_scraper.py          # Playwright Google Maps Scraper + Website Contact/About Email Crawler
│   ├── website_auditor.py       # Technical & AI Website Gap Analyzer (Marks No-Website leads as HIGH PRIORITY)
│   ├── email_worker.py          # Gmail SMTP (Port 587) Sender + Gmail IMAP (Port 993) 24/7 Reply Reader
│   ├── whatsapp_worker.py       # Playwright WhatsApp Web Engine (QR Scan, persistent session, send & read)
│   └── orchestrator.py          # Morning Pipeline, Anti-Spam Delays (4-8 min), 5-min AI Sales Agent & EOD Reports
└── static/
    ├── index.html               # Modern Dark-Mode Agency Command Center UI
    ├── styles.css               # Custom dark glassmorphism & animations
    └── app.js                   # Real-time frontend logic, Audit Modal, Chat Viewer & Simulator
```

---

## ⚡ Quick Setup Guide (Windows)

### Option A: One-Click Windows Launch
Double-click **`start_windows.bat`** in `c:\Users\User\Downloads\lead-hunter\`. It will automatically:
1. Create a virtual environment (`.venv`)
2. Install all dependencies from `requirements.txt`
3. Install the Playwright Chromium browser (`playwright install chromium`)
4. Start the server and open **`http://localhost:8000`** in your browser!

### Option B: Manual Terminal Commands (PowerShell / CMD)
```powershell
cd c:\Users\User\Downloads\lead-hunter
pip install -r requirements.txt
playwright install chromium
python main.py
```
Then open **`http://localhost:8000`** in your browser.

---

## 🔑 How to Get Your 100% Free Keys (Configure in `.env` or Dashboard UI)

1. **Google Gemini Free API Key**:
   - Visit [Google AI Studio](https://aistudio.google.com/app/apikey) and click **Create API Key** (100% Free).
   - Paste it into `GEMINI_API_KEY` in `.env` (or under the **⚙️ Knowledge & .env** tab on the Dashboard).
2. **Groq Free Backup API Key (Optional Rate-Limit Fallback)**:
   - Visit [Groq Cloud Console](https://console.groq.com/keys) and generate a free key.
   - Paste it into `GROQ_API_KEY`.
3. **Gmail 16-Digit App Password (For `smtp.gmail.com:587` & `imap.gmail.com:993`)**:
   - Enable 2-Step Verification on your Google Account.
   - Go to [Google App Passwords](https://myaccount.google.com/apppasswords).
   - Create a new App Password named `"Lead Hunter"` and copy the 16-character password into `GMAIL_APP_PASSWORD` in `.env`.
4. **WhatsApp Web QR Scan (Free)**:
   - Click **"WhatsApp QR Connect"** on the top bar of the Dashboard (`http://localhost:8000`) and scan the QR code once using your phone (`WhatsApp -> Linked Devices -> Link a Device`). Your session stays saved in `./whatsapp_session`.

