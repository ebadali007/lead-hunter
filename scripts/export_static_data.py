import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys

# Ensure root directory is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from database import db
from workers.global_presets import GLOBAL_CATEGORIES, GLOBAL_LOCATIONS, HOT_GLOBAL_PRESETS


def export_pages_data():
    docs_dir = BASE_DIR / "docs"
    data_dir = docs_dir / "data"
    docs_screenshots_dir = docs_dir / "screenshots"

    docs_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    docs_screenshots_dir.mkdir(parents=True, exist_ok=True)

    # 1. Export database dashboard data to JSON
    stats = db.get_dashboard_stats()
    leads = db.get_leads(limit=1000)
    logs = db.get_recent_logs(limit=100)
    customer_requests = db.get_customer_requests(limit=50)
    autopilot_state = db.get_autopilot_state()

    dashboard_payload = {
      "stats": stats,
      "state": {
        "is_running": True,
        "active_campaign": {
          "location": autopilot_state.get("current_city") or "Global AutoPilot Rotation",
          "category": autopilot_state.get("current_category") or "High-Ticket Businesses",
          "status": "24/7 Cloud Engine Active",
        },
        "whatsapp_status": {
          "connected": False,
          "status": "Cloud Headless Mode (Direct 1-Click WA links active)",
        },
      },
      "leads": leads,
      "logs": logs,
      "customer_requests": customer_requests,
      "autopilot": autopilot_state,
    }

    dashboard_json_path = data_dir / "dashboard.json"
    dashboard_json_path.write_text(json.dumps(dashboard_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Exported {len(leads)} leads and live stats to {dashboard_json_path}")

    # 2. Export presets JSON
    presets_payload = {
      "locations": GLOBAL_LOCATIONS,
      "categories": GLOBAL_CATEGORIES,
      "hot_presets": HOT_GLOBAL_PRESETS,
    }
    presets_json_path = data_dir / "presets.json"
    presets_json_path.write_text(json.dumps(presets_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # 3. Copy static assets to docs/ for self-contained GitHub Pages hosting
    static_dir = BASE_DIR / "static"
    if static_dir.exists():
        index_html_src = static_dir / "index.html"
        if index_html_src.exists():
            html_text = index_html_src.read_text(encoding="utf-8")
            # Replace absolute /static/ with relative ./ for GitHub Pages subfolder compatibility
            html_text = html_text.replace('href="/static/styles.css"', 'href="./styles.css"')
            html_text = html_text.replace('src="/static/app.js"', 'src="./app.js"')
            html_text = html_text.replace('href="/static/', 'href="./')
            html_text = html_text.replace('src="/static/', 'src="./')
            (docs_dir / "index.html").write_text(html_text, encoding="utf-8")

        styles_css_src = static_dir / "styles.css"
        if styles_css_src.exists():
            shutil.copy2(styles_css_src, docs_dir / "styles.css")

        app_js_src = static_dir / "app.js"
        if app_js_src.exists():
            shutil.copy2(app_js_src, docs_dir / "app.js")

    # 4. Copy screenshots if any exist
    src_screenshots = BASE_DIR / "screenshots"
    if src_screenshots.exists():
        for img_file in src_screenshots.glob("*.png"):
            dest = docs_screenshots_dir / img_file.name
            if not dest.exists():
                try:
                    shutil.copy2(img_file, dest)
                except Exception:
                    pass

    # 5. Add .nojekyll so GitHub Pages does not skip special files
    (docs_dir / ".nojekyll").write_text("", encoding="utf-8")
    print("GitHub Pages docs export complete!")


if __name__ == "__main__":
    export_pages_data()
