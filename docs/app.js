// ============================================================================
// GEEX MODERN ADMIN & CUSTOMER PORTAL CONTROLLER - LEAD HUNTER AI
// ============================================================================

let currentLeads = [];
let activeModalLeadId = null;
let activeChatLeadId = null;
let activeCustomerLeadId = null;
let groupedConversations = [];
let seenHotAlertIds = new Set();
let currentStatusFilter = "ALL";
let currentPriorityFilter = "ALL";

document.addEventListener("DOMContentLoaded", () => {
  // Auto-open Customer Panel if visiting /customer or ?panel=customer
  const params = new URLSearchParams(window.location.search);
  if (window.location.pathname.includes("/customer") || params.get("panel") === "customer") {
    switchWorkspace("customer");
  }
  if (params.get("lead_id")) {
    activeCustomerLeadId = parseInt(params.get("lead_id"), 10);
  }

  refreshDashboard();
  loadSettingsAndKnowledge();
  loadGlobalPresets();
  refreshAutoPilotState();
  setInterval(refreshDashboard, 2500);
  setInterval(refreshAutoPilotState, 5000);
});

// ----------------------------------------------------------------------------
// WORKSPACE / PANEL SWITCHING (ADMIN vs CUSTOMER vs INBOX vs EOD vs SETTINGS)
// ----------------------------------------------------------------------------
function switchWorkspace(viewName) {
  const views = ["admin", "customer", "chats", "eod", "settings"];
  views.forEach((v) => {
    const sec = document.getElementById(`view-${v}`);
    const navBtn = document.getElementById(`nav-${v}`);
    if (sec) {
      if (v === viewName) sec.classList.remove("hidden");
      else sec.classList.add("hidden");
    }
    if (navBtn) {
      if (v === viewName) {
        navBtn.className =
          "w-full text-left px-2.5 py-1.5 rounded-lg text-xs font-extrabold text-[#9b51e0] bg-purple-50 transition flex items-center justify-between";
      } else {
        navBtn.className =
          "w-full text-left px-2.5 py-1.5 rounded-lg text-xs font-medium text-slate-600 hover:text-[#9b51e0] transition flex items-center justify-between";
      }
    }
  });

  // Update Top Role Switcher Pills & Header Title
  const topAdmin = document.getElementById("top-pill-admin");
  const topCust = document.getElementById("top-pill-customer");
  const titleEl = document.getElementById("page-main-title");
  const subEl = document.getElementById("page-main-subtitle");

  if (viewName === "customer") {
    topCust.className = "px-3.5 py-1.5 rounded-full text-xs font-bold bg-[#9b51e0] text-white transition";
    topAdmin.className = "px-3.5 py-1.5 rounded-full text-xs font-bold text-slate-600 hover:text-slate-900 transition";
    titleEl.textContent = "Customer Self-Service Portal";
    subEl.textContent = "Welcome to Zai Ebad Digital — Inspect Your Free Website Audit, Live Mockup & Packages";
    populateCustomerPortalLeadSelector();
  } else {
    topAdmin.className = "px-3.5 py-1.5 rounded-full text-xs font-bold bg-[#9b51e0] text-white transition";
    topCust.className = "px-3.5 py-1.5 rounded-full text-xs font-bold text-slate-600 hover:text-slate-900 transition";
    const titles = {
      admin: ["Admin Command Center", "Welcome to Geex Modern Autonomous Lead Hunter Dashboard"],
      chats: ["24/7 AI Sales Inbox", "Autonomous Gmail IMAP, WhatsApp Web & Customer Portal Conversations"],
      eod: ["End-of-Day Analytics", "Executive Daily Summary Reports & Outreach Delivery Logs"],
      settings: ["Knowledge Base & .env", "Configure Zero-Cost AI Keys, Gmail SMTP/IMAP & Agency Pricing Rules"],
    };
    if (titles[viewName]) {
      titleEl.textContent = titles[viewName][0];
      subEl.textContent = titles[viewName][1];
    }
  }

  if (viewName === "chats") loadConversations();
  if (viewName === "eod") loadEodReports();
  if (viewName === "settings") loadSettingsAndKnowledge();
}

function openMorningHunterModal() {
  switchWorkspace("admin");
  const locInput = document.getElementById("input-location");
  if (locInput) {
    locInput.scrollIntoView({ behavior: "smooth", block: "center" });
    locInput.focus();
  }
}

let currentSearchQuery = "";

function setLeadFilter(statusVal, priorityVal, btnEl) {
  currentStatusFilter = statusVal;
  currentPriorityFilter = priorityVal;
  document.querySelectorAll(".lead-tab").forEach((b) => {
    b.className = "lead-tab geex-tab-inactive px-3.5 py-1.5 rounded-xl text-xs font-bold transition flex items-center gap-1.5";
  });
  if (btnEl) {
    btnEl.className = "lead-tab geex-tab-active px-3.5 py-1.5 rounded-xl text-xs font-bold transition flex items-center gap-1.5";
  }
  applyCurrentFiltersAndRender();
}

function handleLeadSearch(val) {
  currentSearchQuery = (val || "").trim().toLowerCase();
  applyCurrentFiltersAndRender();
}

function clearLeadSearch() {
  const el = document.getElementById("lead-search-input");
  if (el) el.value = "";
  currentSearchQuery = "";
  applyCurrentFiltersAndRender();
}

function applyCurrentFiltersAndRender() {
  let filtered = currentLeads || [];

  // Filter by Status Tab
  if (currentStatusFilter && currentStatusFilter !== "ALL") {
    if (currentStatusFilter === "EMAIL_SENT") {
      filtered = filtered.filter((l) => Boolean(l.email_sent));
    } else if (currentStatusFilter === "WA_SENT") {
      filtered = filtered.filter((l) => Boolean(l.whatsapp_sent));
    } else if (currentStatusFilter === "HIGH_SCORE") {
      filtered = filtered.filter((l) => Number(l.audit_score || 0) >= 70);
    } else if (currentStatusFilter === "HOT_LEAD") {
      filtered = filtered.filter((l) => Boolean(l.is_hot_lead) || l.status === "HOT_LEAD");
    } else {
      filtered = filtered.filter((l) => l.status === currentStatusFilter);
    }
  }

  // Filter by Priority
  if (currentPriorityFilter && currentPriorityFilter !== "ALL") {
    if (currentPriorityFilter === "HIGH_PRIORITY") {
      filtered = filtered.filter(
        (l) => l.priority === "HIGH_PRIORITY" || l.priority === "HIGH" || !l.has_website
      );
    } else {
      filtered = filtered.filter((l) => l.priority === currentPriorityFilter);
    }
  }

  // Filter by Live Search Text
  if (currentSearchQuery) {
    filtered = filtered.filter((l) => {
      const bname = (l.business_name || "").toLowerCase();
      const loc = (l.location || "").toLowerCase();
      const cat = (l.category || "").toLowerCase();
      const em = (l.email || "").toLowerCase();
      const ph = (l.phone || "").toLowerCase();
      const addr = (l.address || "").toLowerCase();
      return (
        bname.includes(currentSearchQuery) ||
        loc.includes(currentSearchQuery) ||
        cat.includes(currentSearchQuery) ||
        em.includes(currentSearchQuery) ||
        ph.includes(currentSearchQuery) ||
        addr.includes(currentSearchQuery)
      );
    });
  }

  renderGeexLeadsList(filtered);
}

// ----------------------------------------------------------------------------
// REAL-TIME DASHBOARD POLLING (SUPPORTS LOCALHOST, RENDER & GITHUB PAGES)
// ----------------------------------------------------------------------------
const IS_STATIC_PAGES =
  window.location.hostname.includes("github.io") ||
  window.location.protocol === "file:" ||
  window.location.pathname.includes("/docs");

async function refreshDashboard() {
  try {
    let data = null;

    if (IS_STATIC_PAGES) {
      try {
        const resp = await fetch("./data/dashboard.json?t=" + Date.now());
        if (resp.ok) {
          data = await resp.json();
        }
      } catch (e) {
        console.warn("Static data fetch:", e);
      }
    }

    if (!data) {
      const searchParam = currentSearchQuery ? `&search=${encodeURIComponent(currentSearchQuery)}` : "";
      const resp = await fetch(
        `/api/dashboard?status=${currentStatusFilter}&priority=${currentPriorityFilter}${searchParam}`
      );
      if (!resp.ok) return;
      data = await resp.json();
    }

    updateKpisAndQuotas(data.stats);
    updateSystemState(data.state);
    renderLiveLogs(data.logs);
    currentLeads = data.leads || [];
    applyCurrentFiltersAndRender();
    renderRecentAvatars(currentLeads);

    if (IS_STATIC_PAGES && data.autopilot) {
      updateStaticAutoPilotState(data.autopilot);
    }
  } catch (err) {
    console.warn("Poll notice:", err);
  }
}

function updateStaticAutoPilotState(autopilotState) {
  const curEl = document.getElementById("autopilot-cur-target");
  const nextEl = document.getElementById("autopilot-next-target");
  const doneEl = document.getElementById("autopilot-emails-done");
  const targetEl = document.getElementById("autopilot-emails-target");
  const badge = document.getElementById("autopilot-badge");
  const ping = document.getElementById("autopilot-dot-ping");
  const dot = document.getElementById("autopilot-dot");

  if (curEl) curEl.textContent = `${autopilotState.current_city || "Global Rotation"} • ${autopilotState.current_category || "General"}`;
  if (nextEl) nextEl.textContent = "Next 4-Hour Cloud AutoPilot Schedule";
  if (badge) {
    badge.textContent = "ONLINE & 24/7 AUTONOMOUS (GITHUB ACTIONS)";
    badge.className = "px-2 py-0.5 text-[10px] font-bold rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30";
  }
  if (ping) ping.style.display = "inline-flex";
  if (dot) dot.className = "relative inline-flex rounded-full h-3 w-3 bg-emerald-500";
}

function updateKpisAndQuotas(stats) {
  if (!stats) return;
  const setTxt = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  };

  setTxt("kpi-today-leads", stats.today_leads ?? 0);
  setTxt("kpi-total-leads", stats.total_leads ?? 0);
  setTxt("kpi-high-priority", stats.high_priority ?? 0);
  setTxt("kpi-emails-today", stats.emails_today ?? 0);
  setTxt("kpi-email-limit", stats.daily_email_limit ?? 40);
  setTxt("kpi-wa-today", stats.whatsapps_today ?? 0);
  setTxt("kpi-wa-limit", stats.daily_whatsapp_limit ?? 35);
  setTxt("kpi-replies-today", stats.replies_today ?? 0);
  setTxt("kpi-total-replies", stats.total_replies ?? 0);
  setTxt("kpi-hot-leads", stats.hot_leads ?? 0);
  setTxt("kpi-outreach-combined", (stats.emails_today || 0) + (stats.whatsapps_today || 0) + (stats.total_replies || 0));

  // Header notification badges
  setTxt("badge-top-replies", stats.total_replies ?? 0);
  setTxt("badge-top-hot", stats.hot_leads ?? 0);

  const sideHot = document.getElementById("sidebar-hot-badge");
  if (sideHot) {
    if (stats.hot_leads > 0) {
      sideHot.textContent = stats.hot_leads;
      sideHot.classList.remove("hidden");
    } else {
      sideHot.classList.add("hidden");
    }
  }

  // Estimated Pipeline Value on the Geex Credit Card ($850 per lead + $1,450 per hot lead, base $4,500)
  const pipelineVal = 4500 + (stats.total_leads || 0) * 650 + (stats.hot_leads || 0) * 1450;
  setTxt("card-pipeline-value", "$ " + pipelineVal.toLocaleString());

  // Dynamic 7-Day Trend Blue Bars (Sun=0..Sat=6) for Leads Scraped
  const dowNames = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
  const leadsDow = stats.leads_dow || {};
  const maxLeadsDow = Math.max(1, ...Object.values(leadsDow).map(Number));
  const curDow = stats.current_dow ?? new Date().getDay();

  for (let i = 0; i < 7; i++) {
    const val = Number(leadsDow[i] || 0);
    const bar = document.getElementById(`blue-bar-${i}`);
    if (bar) {
      const pct = Math.max(12, Math.round((val / maxLeadsDow) * 92));
      bar.style.height = `${pct}%`;
      bar.title = `${dowNames[i]}: ${val} Leads Scraped`;
      if (i === curDow) {
        bar.classList.add("ring-2", "ring-sky-400", "shadow-md");
      } else {
        bar.classList.remove("ring-2", "ring-sky-400", "shadow-md");
      }
    }
  }

  // Dynamic 7-Day Trend Orange Bars (Sun=0..Sat=6) for Outreach Sent
  const outreachDow = stats.outreach_dow || {};
  const maxOutreachDow = Math.max(1, ...Object.values(outreachDow).map(Number));
  for (let i = 0; i < 7; i++) {
    const val = Number(outreachDow[i] || 0);
    const bar = document.getElementById(`orange-bar-${i}`);
    if (bar) {
      const pct = Math.max(12, Math.round((val / maxOutreachDow) * 92));
      bar.style.height = `${pct}%`;
      bar.title = `${dowNames[i]}: ${val} Outreach Dispatched`;
      if (i === curDow) {
        bar.classList.add("ring-2", "ring-amber-400", "shadow-md");
      } else {
        bar.classList.remove("ring-2", "ring-amber-400", "shadow-md");
      }
    }
  }

  // Dynamic Growth Percentages
  if (stats.lead_growth) {
    setTxt("trend-leads-growth", `^ ${stats.lead_growth}`);
  }
  if (stats.outreach_growth) {
    setTxt("trend-outreach-growth", `^ ${stats.outreach_growth}`);
  }

  // Dynamic Filter Tab Badges & Table Counter
  const fc = stats.filter_counts || {};
  setTxt("cnt-tab-all", fc.all ?? stats.total_leads ?? 0);
  setTxt("cnt-tab-noweb", fc.high_priority ?? stats.high_priority ?? 0);
  setTxt("cnt-tab-hot", fc.hot ?? stats.hot_leads ?? 0);
  setTxt("cnt-tab-email", fc.email_sent ?? 0);
  setTxt("cnt-tab-wa", fc.wa_sent ?? 0);
  setTxt("cnt-tab-score", fc.high_score ?? 0);
  setTxt("badge-total-leads-table", stats.total_leads ?? 0);

  // Progress Bars in "Automation Quotas & Channels"
  const emailPct = Math.min(100, Math.max(8, Math.round(((stats.emails_today || 0) / (stats.daily_email_limit || 40)) * 100)));
  const waPct = Math.min(100, Math.max(8, Math.round(((stats.whatsapps_today || 0) / (stats.daily_whatsapp_limit || 35)) * 100)));
  const highPct = Math.min(100, Math.max(12, (stats.high_priority || 1) * 18));
  const repPct = Math.min(100, Math.max(12, (stats.total_replies || 1) * 20));

  const setWidth = (id, pct) => {
    const el = document.getElementById(id);
    if (el) el.style.width = `${pct}%`;
  };
  setWidth("bar-quota-email", emailPct);
  setWidth("bar-quota-wa", waPct);
  setWidth("bar-quota-high", highPct);
  setWidth("bar-quota-replies", repPct);
}

function updateSystemState(state) {
  if (!state) return;

  const badge = document.getElementById("campaign-stage-badge");
  const startBtn = document.getElementById("btn-start-campaign");
  const stopBtn = document.getElementById("btn-stop-campaign");
  const countdownPill = document.getElementById("countdown-pill");
  const headerStatus = document.getElementById("header-hunter-status");

  if (badge) badge.textContent = state.campaign_running ? state.current_stage : "24/7 **** **** AUTO";
  if (headerStatus) {
    headerStatus.textContent = state.campaign_running ? "Hunting Active..." : "Start Hunter";
  }

  if (state.campaign_running) {
    startBtn?.classList.add("opacity-60", "pointer-events-none");
    stopBtn?.classList.remove("hidden");
  } else {
    startBtn?.classList.remove("opacity-60", "pointer-events-none");
    stopBtn?.classList.add("hidden");
  }

  if (state.next_outreach_countdown > 0) {
    countdownPill?.classList.remove("hidden");
    if (countdownPill) countdownPill.textContent = `Cooldown: ${state.next_outreach_countdown}s`;
  } else {
    countdownPill?.classList.add("hidden");
  }

  const txtWa = document.getElementById("txt-wa");
  if (txtWa) {
    txtWa.textContent = state.whatsapp_status?.connected ? "WhatsApp: Active" : "WhatsApp QR";
  }

  const alerts = state.hot_lead_alerts || [];
  if (alerts.length > 0) {
    const latest = alerts[alerts.length - 1];
    if (!seenHotAlertIds.has(latest.id)) {
      seenHotAlertIds.add(latest.id);
      if (latest.is_deal_won) {
        showDealWonBanner(latest);
      } else {
        showHotLeadBanner(latest);
      }
    }
  }
}

function showDealWonBanner(alertObj) {
  const container = document.getElementById("deal-won-alert-container");
  const title = document.getElementById("deal-won-title");
  const desc = document.getElementById("deal-won-desc");
  const time = document.getElementById("deal-won-time");
  if (title) title.textContent = `🎉 DEAL CLOSED: ${alertObj.business_name} (${alertObj.channel})`;
  if (desc) desc.textContent = `"${alertObj.client_message}" • Immediate action: Check inbox or WhatsApp to initiate project deliverables!`;
  if (time) time.textContent = alertObj.timestamp || "";
  container?.classList.remove("hidden");
  activeChatLeadId = alertObj.lead_id;
}

function dismissDealWonAlert() {
  document.getElementById("deal-won-alert-container")?.classList.add("hidden");
}

function showHotLeadBanner(alertObj) {
  const container = document.getElementById("hot-lead-alert-container");
  const txt = document.getElementById("hot-lead-alert-text");
  if (txt) {
    txt.textContent = `${alertObj.business_name} (${alertObj.channel}): "${alertObj.client_message}"`;
  }
  container?.classList.remove("hidden");
  activeChatLeadId = alertObj.lead_id;
}

function dismissHotLeadAlert() {
  document.getElementById("hot-lead-alert-container")?.classList.add("hidden");
}

async function refreshAutoPilotState() {
  try {
    const resp = await fetch("/api/autopilot/state");
    if (!resp.ok) return;
    const data = await resp.json();
    if (!data.ok) return;
    const st = data.state || {};
    const tgt = data.next_target || {};
    const stats = data.stats || {};

    const curEl = document.getElementById("autopilot-cur-target");
    const nextEl = document.getElementById("autopilot-next-target");
    const doneEl = document.getElementById("autopilot-emails-done");
    const targetEl = document.getElementById("autopilot-emails-target");
    const badge = document.getElementById("autopilot-badge");
    const ping = document.getElementById("autopilot-dot-ping");
    const dot = document.getElementById("autopilot-dot");

    if (curEl) curEl.textContent = `${st.current_city || tgt.location || "Toronto, ON"} • ${st.current_category || tgt.category || "General"}`;
    if (nextEl) nextEl.textContent = `${tgt.location || "Next Rotating City"} • ${tgt.category || "Next Niche"}`;
    if (doneEl) doneEl.textContent = stats.emails_today ?? 0;
    if (targetEl) targetEl.textContent = stats.daily_limit ?? 60;

    const isEnabled = Boolean(st.is_enabled);
    if (badge) {
      badge.textContent = isEnabled ? "ONLINE & 24/7 AUTONOMOUS" : "PAUSED";
      badge.className = isEnabled
        ? "px-2 py-0.5 text-[10px] font-bold rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
        : "px-2 py-0.5 text-[10px] font-bold rounded-full bg-slate-500/20 text-slate-300 border border-slate-500/30";
    }
    if (ping) ping.style.display = isEnabled ? "inline-flex" : "none";
    if (dot) dot.className = isEnabled ? "relative inline-flex rounded-full h-3 w-3 bg-emerald-500" : "relative inline-flex rounded-full h-3 w-3 bg-slate-500";
  } catch (e) {
    console.debug("AutoPilot state poll notice:", e);
  }
}

async function triggerAutoPilotNow() {
  const btn = document.getElementById("btn-autopilot-run");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = "<span>⏳</span><span>Dispatching...</span>";
  }
  try {
    const resp = await fetch("/api/autopilot/run-now", { method: "POST" });
    const data = await resp.json();
    alert(data.message || "AutoPilot cycle initiated!");
    refreshAutoPilotState();
    refreshDashboard();
  } catch (err) {
    alert("Error launching cycle: " + err);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = "<span>⚡</span><span>Run AutoPilot Cycle</span>";
    }
  }
}

async function toggleAutoPilotMode() {
  try {
    const resp = await fetch("/api/autopilot/toggle", { method: "POST" });
    const data = await resp.json();
    refreshAutoPilotState();
  } catch (err) {
    alert("Error toggling AutoPilot: " + err);
  }
}

// ----------------------------------------------------------------------------
// GEEX TRANSACTION-STYLE LEAD LIST & RECENT AVATAR ROW
// ----------------------------------------------------------------------------
function renderGeexLeadsList(leads) {
  const container = document.getElementById("leads-table-body");
  if (!container) return;

  if (!leads || leads.length === 0) {
    container.innerHTML = `
      <div class="py-12 text-center text-xs text-slate-400">
        No leads in this filter yet. Click <strong>"🚀 Start Finding Clients"</strong> on the right card to launch Google Maps & Web Scraping!
      </div>
    `;
    return;
  }

  const avatarColors = [
    "from-purple-500 to-indigo-500",
    "from-pink-500 to-rose-500",
    "from-emerald-500 to-teal-500",
    "from-sky-500 to-blue-600",
    "from-amber-500 to-orange-500",
  ];

  container.innerHTML = leads
    .map((lead, idx) => {
      const isHigh = lead.priority === "HIGH_PRIORITY" || !lead.has_website;
      const isHot = lead.is_hot_lead || lead.status === "HOT_LEAD";

      // Geex left rounded square icon (soft pink for urgent/no-website, soft mint for contacted/hot)
      const arrowBg = isHigh ? "bg-[#ffe6e6] text-rose-500" : "bg-[#def7ec] text-emerald-600";
      const arrowIcon = isHot ? "🔥" : isHigh ? "↓" : "↑";

      const initials = (lead.business_name || "BZ")
        .split(" ")
        .slice(0, 2)
        .map((w) => w[0])
        .join("")
        .toUpperCase();
      const grad = avatarColors[idx % avatarColors.length];

      const rightMetric = isHot
        ? `<span class="text-emerald-500 font-extrabold text-sm">🔥 HOT LEAD</span>`
        : isHigh
        ? `<span class="text-rose-500 font-extrabold text-sm">No Website</span>`
        : `<span class="text-emerald-500 font-extrabold text-sm">Score ${lead.audit_score}%</span>`;

      const handleText = lead.email || lead.phone || lead.website || "Local Prospect";
      const cleanPhone = (lead.phone || "").replace(/\D/g, "");
      const waText = encodeURIComponent(lead.draft_whatsapp_msg || `Hi ${lead.business_name} team, quick question regarding your mobile site.`);
      const waLink = cleanPhone ? `https://wa.me/${cleanPhone}?text=${waText}` : null;

      return `
        <div class="py-3.5 px-2 hover:bg-[#faf9fd] rounded-2xl transition grid grid-cols-1 md:grid-cols-12 items-center gap-3">
          <!-- Left: Pastel Square + Business Name & Location (5 cols) -->
          <div class="md:col-span-5 flex items-center gap-3.5">
            <div class="w-11 h-11 rounded-2xl ${arrowBg} flex items-center justify-center font-extrabold text-sm shrink-0">
              ${arrowIcon}
            </div>
            <div class="min-w-0">
              <div class="font-extrabold text-sm text-slate-800 truncate">${escapeHtml(lead.business_name)}</div>
              <div class="text-[11px] text-slate-400 truncate">
                ★ ${lead.rating || "4.7"} (${lead.reviews_count || 0}) • ${escapeHtml(lead.location)}
              </div>
            </div>
          </div>

          <!-- Middle: Circular Avatar + Category & Contact Handle (4 cols) -->
          <div class="md:col-span-4 flex items-center gap-3">
            <div class="w-10 h-10 rounded-full bg-gradient-to-tr ${grad} text-white font-extrabold text-xs flex items-center justify-center shrink-0 shadow-sm">
              ${escapeHtml(initials)}
            </div>
            <div class="min-w-0">
              <div class="font-bold text-xs text-slate-800 truncate">${escapeHtml(lead.category)}</div>
              <div class="text-[11px] text-slate-400 truncate">${escapeHtml(handleText)}</div>
            </div>
          </div>

          <!-- Right: Metric + Action Pills (3 cols) -->
          <div class="md:col-span-4 flex items-center justify-end gap-1.5 flex-wrap">
            <div class="text-right mr-1 hidden sm:block">
              ${rightMetric}
              <div class="flex items-center justify-end gap-1 mt-0.5">
                ${lead.email_sent ? '<span class="px-1.5 py-0.2 rounded bg-emerald-100 text-emerald-700 text-[9px] font-bold">✓ Email</span>' : ''}
                ${lead.whatsapp_sent ? '<span class="px-1.5 py-0.2 rounded bg-teal-100 text-teal-700 text-[9px] font-bold">✓ WA</span>' : ''}
              </div>
            </div>
            ${waLink ? `<a href="${waLink}" target="_blank" title="1-Click Direct WhatsApp Pitch to Client" class="px-2.5 py-1.5 rounded-xl bg-teal-50 hover:bg-teal-600 text-teal-700 hover:text-white text-[11px] font-bold transition">📲 WA</a>` : ''}
            ${lead.website ? `<a href="${escapeHtml(lead.website)}" target="_blank" title="Visit Live Website" class="px-2 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-[11px] font-bold transition">🌐 Site</a>` : ''}
            <a href="/api/leads/${lead.id}/email-preview" target="_blank" title="Preview Professional HTML Email + Screenshot"
              class="px-2.5 py-1.5 rounded-xl bg-indigo-50 hover:bg-indigo-600 text-indigo-700 hover:text-white text-[11px] font-bold transition">
              📧 Email
            </a>
            <button onclick="openCustomerPortalForLead(${lead.id})" title="Open in Customer Panel"
              class="px-2.5 py-1.5 rounded-xl bg-emerald-50 hover:bg-emerald-500 text-emerald-700 hover:text-white text-[11px] font-bold transition">
              👤 Client
            </button>
            <button onclick="openAuditModal(${lead.id})"
              class="px-3 py-1.5 rounded-xl bg-[#efe5fc] hover:bg-[#9b51e0] text-[#9b51e0] hover:text-white text-[11px] font-bold transition">
              🔍 Audit
            </button>
            <button onclick="deleteLeadDirect(${lead.id}, event)" title="Delete Lead"
              class="px-2 py-1.5 rounded-xl hover:bg-rose-100 text-slate-400 hover:text-rose-600 text-xs font-bold transition">
              🗑
            </button>
          </div>
        </div>
      `;
    })
    .join("");
}

async function deleteLeadDirect(leadId, event) {
  if (event) event.stopPropagation();
  if (!confirm("Are you sure you want to delete this lead?")) return;
  try {
    const res = await fetch(`/api/leads/${leadId}`, { method: "DELETE" });
    if (res.ok) {
      currentLeads = currentLeads.filter((l) => l.id !== leadId);
      applyCurrentFiltersAndRender();
      refreshDashboard();
    }
  } catch (err) {
    console.error("Delete error:", err);
  }
}

function renderRecentAvatars(leads) {
  const row = document.getElementById("recent-avatars-row");
  if (!row) return;

  const topLeads = (leads || []).slice(0, 4);
  const colors = [
    "from-purple-600 to-pink-500",
    "from-emerald-500 to-teal-600",
    "from-amber-500 to-orange-500",
    "from-sky-500 to-indigo-600",
  ];

  const avatarsHtml = topLeads
    .map((l, i) => {
      const init = (l.business_name || "CL")
        .split(" ")
        .slice(0, 2)
        .map((w) => w[0])
        .join("")
        .toUpperCase();
      return `
        <button onclick="openCustomerPortalForLead(${l.id})" title="${escapeHtml(l.business_name)} (Click to view Customer Portal)"
          class="w-12 h-12 rounded-full p-0.5 bg-gradient-to-tr from-[#9b51e0] to-pink-500 hover:scale-105 transition shadow">
          <div class="w-full h-full rounded-full bg-gradient-to-tr ${colors[i % colors.length]} text-white font-extrabold text-xs flex items-center justify-center border-2 border-white">
            ${escapeHtml(init)}
          </div>
        </button>
      `;
    })
    .join("");

  row.innerHTML = `
    ${avatarsHtml}
    <button onclick="openAddLeadModal()" title="Add or Message New Prospect"
      class="w-12 h-12 rounded-full bg-[#3b384c] hover:bg-slate-900 text-white flex items-center justify-center shadow-md transition">
      ✈️
    </button>
  `;
}

// ----------------------------------------------------------------------------
// CUSTOMER PANEL (SELF-SERVICE PORTAL FOR CLIENTS)
// ----------------------------------------------------------------------------
function openCustomerPortalForLead(leadId) {
  if (!leadId) return;
  activeCustomerLeadId = leadId;
  closeAuditModal();
  switchWorkspace("customer");
  populateCustomerPortalLeadSelector();
  renderCustomerPortalData(leadId);
}

function populateCustomerPortalLeadSelector() {
  const sel = document.getElementById("customer-lead-selector");
  if (!sel) return;

  if (!activeCustomerLeadId && currentLeads.length > 0) {
    activeCustomerLeadId = currentLeads[0].id;
  }

  sel.innerHTML =
    `<option value="">-- Select Your Business Profile --</option>` +
    currentLeads
      .map(
        (l) =>
          `<option value="${l.id}" ${l.id === activeCustomerLeadId ? "selected" : ""}>${escapeHtml(
            l.business_name
          )} (${escapeHtml(l.location)})</option>`
      )
      .join("");

  if (activeCustomerLeadId) {
    renderCustomerPortalData(activeCustomerLeadId);
  }
}

function onSelectCustomerPortalLead() {
  const val = parseInt(document.getElementById("customer-lead-selector").value, 10);
  if (val) {
    activeCustomerLeadId = val;
    renderCustomerPortalData(val);
  }
}

async function renderCustomerPortalData(leadId) {
  let lead = currentLeads.find((l) => l.id === leadId);
  if (!lead) {
    try {
      const resp = await fetch(`/api/leads/${leadId}`);
      if (resp.ok) lead = await resp.json();
    } catch (e) {
      console.warn("Could not fetch customer portal lead:", e);
    }
  }
  if (!lead) return;

  document.getElementById("cust-card-bname").textContent = lead.business_name;
  document.getElementById("cust-book-bname").value = lead.business_name || "";
  document.getElementById("cust-book-email").value =
    lead.email && !lead.email.endsWith(".local") ? lead.email : "";
  document.getElementById("cust-book-phone").value = lead.phone || "";
  document.getElementById("cust-live-mockup-btn").href = `/preview/${lead.id}`;
  document.getElementById("cust-audit-score").textContent = `${lead.audit_score || 15}/100`;

  const report = lead.audit_report || {};
  const issues = report.issues_found || [
    "No official website or mobile ordering system attached",
    "Missing direct commission-free online booking/ordering flow",
  ];
  const solutions = report.recommended_solutions || [
    "Launch a fast mobile-first website & Local Google SEO",
    "Add 0% commission online ordering / appointment booking",
  ];

  document.getElementById("cust-issues-list").innerHTML = issues
    .slice(0, 3)
    .map((i) => `<div class="p-3 rounded-xl bg-rose-50 text-rose-700 font-medium">• ${escapeHtml(i)}</div>`)
    .join("");

  document.getElementById("cust-solutions-list").innerHTML = solutions
    .slice(0, 3)
    .map((s) => `<div class="p-3 rounded-xl bg-emerald-50 text-emerald-800 font-medium">✓ ${escapeHtml(s)}</div>`)
    .join("");
}

function selectCustomerPackage(pkgName) {
  const el = document.getElementById("cust-book-pkg");
  if (el) {
    el.value = pkgName;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

async function runCustomerSelfAudit() {
  const business_name = document.getElementById("cust-audit-name").value.trim();
  const category = document.getElementById("cust-audit-category").value.trim() || "Local Business";
  const website = document.getElementById("cust-audit-web").value.trim();
  if (!business_name) {
    alert("Please enter your Business Name to run the free AI audit!");
    return;
  }

  const resp = await fetch("/api/customer/instant-audit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      business_name,
      category,
      location: "Your Area",
      website,
    }),
  });
  const data = await resp.json();
  if (data.lead) {
    activeCustomerLeadId = data.lead.id;
    await refreshDashboard();
    populateCustomerPortalLeadSelector();
    renderCustomerPortalData(data.lead.id);
  }
}

async function submitCustomerPortalOrder() {
  const business_name = document.getElementById("cust-book-bname").value.trim() || "Valued Client";
  const customer_email = document.getElementById("cust-book-email").value.trim();
  const customer_phone = document.getElementById("cust-book-phone").value.trim();
  const selected_package = document.getElementById("cust-book-pkg").value.trim();
  const preferred_call_time = document.getElementById("cust-book-time").value.trim() || "Flexible this week";
  const project_notes = document.getElementById("cust-book-notes").value.trim();

  const resp = await fetch("/api/customer/order", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      lead_id: activeCustomerLeadId || 0,
      business_name,
      customer_email,
      customer_phone,
      selected_package,
      preferred_call_time,
      project_notes,
    }),
  });
  const data = await resp.json();
  if (data.ok) {
    await refreshDashboard();
    alert(
      `🎉 Thank you, ${business_name}!\n\nYour package selection (${selected_package}) and discovery call request (${preferred_call_time}) have been confirmed. Zai Ebad Digital has received your priority booking!`
    );
  }
}

async function sendCustomerPortalChat() {
  const input = document.getElementById("cust-chat-input");
  const msg = input.value.trim();
  if (!msg) return;

  const targetLeadId = activeCustomerLeadId || (currentLeads[0] && currentLeads[0].id);
  const box = document.getElementById("cust-chat-messages");

  box.innerHTML += `
    <div class="p-3 rounded-2xl bg-[#9b51e0] text-white ml-8 font-medium">
      ${escapeHtml(msg)}
    </div>
  `;
  input.value = "";
  box.scrollTop = box.scrollHeight;

  if (!targetLeadId) {
    box.innerHTML += `
      <div class="p-3 rounded-2xl bg-[#f4f3f9] text-slate-700 mr-8">
        Our websites start at $399–$699 (5–7 days) and Online Ordering systems start at $799. Enter your business name on the left to run a personalized audit!
      </div>
    `;
    return;
  }

  const resp = await fetch("/api/sales-agent/simulate-reply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      lead_id: targetLeadId,
      channel: "EMAIL",
      message_text: msg,
    }),
  });
  const data = await resp.json();
  const aiReply = data.result?.ai_reply || "Thanks for reaching out! Let's hop on a quick 10-minute call.";

  box.innerHTML += `
    <div class="p-3 rounded-2xl bg-[#f4f3f9] text-slate-700 mr-6 whitespace-pre-wrap">
      ${escapeHtml(aiReply)}
    </div>
  `;
  box.scrollTop = box.scrollHeight;
  await refreshDashboard();
}

// ----------------------------------------------------------------------------
// LIVE LOGS, CAMPAIGN & MODALS
// ----------------------------------------------------------------------------
function renderLiveLogs(logs) {
  const box = document.getElementById("live-logs-box");
  if (!box || !logs || logs.length === 0) return;

  box.innerHTML = logs
    .map((item) => {
      const timeOnly = (item.created_at || "").split(" ")[1] || item.created_at;
      const color =
        item.level === "HOT_LEAD"
          ? "text-rose-600 font-bold"
          : item.level === "SUCCESS"
          ? "text-emerald-600 font-semibold"
          : "text-slate-600";
      return `<div><span class="text-slate-400">[${timeOnly}]</span> <strong class="text-purple-600">${escapeHtml(
        item.module
      )}:</strong> <span class="${color}">${escapeHtml(item.message)}</span></div>`;
    })
    .join("");
}

// ----------------------------------------------------------------------------
// WORLDWIDE CLIENT HUNTING PRESETS & CASCADING SELECTORS
// ----------------------------------------------------------------------------
let globalPresetsData = { locations: {}, categories: {}, hot_presets: [] };

async function loadGlobalPresets() {
  try {
    const resp = await fetch("/api/presets/locations-categories");
    if (!resp.ok) return;
    globalPresetsData = await resp.json();

    // Populate Hot Presets container
    const presetsContainer = document.getElementById("hot-presets-container");
    if (presetsContainer && globalPresetsData.hot_presets?.length > 0) {
      presetsContainer.innerHTML = globalPresetsData.hot_presets
        .map(
          (p) => `
          <button type="button" onclick="applyPreset('${escapeHtml(p.location)}', '${escapeHtml(p.category)}')"
            class="shrink-0 px-2.5 py-1 rounded-lg bg-[#f4f3f9] hover:bg-purple-100 text-[11px] font-bold text-slate-700 transition">
            ${escapeHtml(p.label)}
          </button>
        `
        )
        .join("");
    }

    // Populate Country dropdown
    const countrySel = document.getElementById("select-country");
    if (countrySel && globalPresetsData.locations) {
      countrySel.innerHTML = Object.keys(globalPresetsData.locations)
        .map((k) => {
          const loc = globalPresetsData.locations[k];
          return `<option value="${k}" ${k === "CA" ? "selected" : ""}>${loc.flag} ${loc.country}</option>`;
        })
        .join("") + `<option value="CUSTOM">🌐 Custom Location</option>`;
      onGlobalCountryChange();
    }

    // Populate Category Group dropdown
    const catGroupSel = document.getElementById("select-cat-group");
    if (catGroupSel && globalPresetsData.categories) {
      catGroupSel.innerHTML = Object.keys(globalPresetsData.categories)
        .map((k) => {
          const grp = globalPresetsData.categories[k];
          return `<option value="${k}" ${k === "food_dining" ? "selected" : ""}>${grp.icon} ${grp.group}</option>`;
        })
        .join("") + `<option value="CUSTOM">🌐 Custom Category</option>`;
      onGlobalCatGroupChange();
    }
  } catch (err) {
    console.warn("Could not load global presets:", err);
  }
}

function onGlobalCountryChange() {
  const countrySel = document.getElementById("select-country");
  const citySel = document.getElementById("select-city");
  const locInput = document.getElementById("input-location");
  if (!countrySel || !citySel) return;

  const key = countrySel.value;
  if (key === "CUSTOM") {
    citySel.innerHTML = `<option value="CUSTOM">Type custom location below</option>`;
    if (locInput) locInput.focus();
    return;
  }

  const countryData = globalPresetsData.locations?.[key];
  if (!countryData || !countryData.cities) return;

  citySel.innerHTML = countryData.cities
    .map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`)
    .join("");

  if (countryData.cities.length > 0 && locInput) {
    locInput.value = countryData.cities[0];
  }
}

function onGlobalCityChange() {
  const citySel = document.getElementById("select-city");
  const locInput = document.getElementById("input-location");
  if (citySel && locInput && citySel.value !== "CUSTOM") {
    locInput.value = citySel.value;
  }
}

function onGlobalCatGroupChange() {
  const groupSel = document.getElementById("select-cat-group");
  const catSel = document.getElementById("select-category");
  const catInput = document.getElementById("input-category");
  if (!groupSel || !catSel) return;

  const key = groupSel.value;
  if (key === "CUSTOM") {
    catSel.innerHTML = `<option value="CUSTOM">Type custom niche below</option>`;
    if (catInput) catInput.focus();
    return;
  }

  const groupData = globalPresetsData.categories?.[key];
  if (!groupData || !groupData.niches) return;

  catSel.innerHTML = groupData.niches
    .map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`)
    .join("");

  if (groupData.niches.length > 0 && catInput) {
    catInput.value = groupData.niches[0];
  }
}

function onGlobalCategoryChange() {
  const catSel = document.getElementById("select-category");
  const catInput = document.getElementById("input-category");
  if (catSel && catInput && catSel.value !== "CUSTOM") {
    catInput.value = catSel.value;
  }
}

function applyPreset(location, category) {
  const locInput = document.getElementById("input-location");
  const catInput = document.getElementById("input-category");
  if (locInput) {
    locInput.value = location;
    locInput.classList.add("ring-2", "ring-purple-500");
    setTimeout(() => locInput.classList.remove("ring-2", "ring-purple-500"), 800);
  }
  if (catInput) {
    catInput.value = category;
    catInput.classList.add("ring-2", "ring-purple-500");
    setTimeout(() => catInput.classList.remove("ring-2", "ring-purple-500"), 800);
  }

  const citySel = document.getElementById("select-city");
  if (citySel) {
    for (let opt of citySel.options) {
      if (opt.value === location) {
        citySel.value = location;
        break;
      }
    }
  }

  const catSel = document.getElementById("select-category");
  if (catSel) {
    for (let opt of catSel.options) {
      if (opt.value === category) {
        catSel.value = category;
        break;
      }
    }
  }
}

async function startCampaign() {
  const location = document.getElementById("input-location").value.trim() || "Toronto, Canada";
  const category = document.getElementById("input-category").value.trim() || "Restaurants";
  const dailyLimit = parseInt(document.getElementById("input-limit").value || "6", 10);
  const fastMode = document.getElementById("input-delay-mode").value === "fast";
  const autoSendEl = document.getElementById("input-autosend-mode");
  const autoSend = autoSendEl ? autoSendEl.value === "true" : true;

  await fetch("/api/campaign/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      location,
      category,
      daily_limit: dailyLimit,
      fast_demo_delay: fastMode,
      auto_send: autoSend,
    }),
  });
  refreshDashboard();
}

async function stopCampaign() {
  await fetch("/api/campaign/stop", { method: "POST" });
  refreshDashboard();
}

let modalDesktopUrl = "";
let modalMobileUrl = "";

function switchScreenshotTab(tab) {
  const shotImg = document.getElementById("modal-screenshot-img");
  const shotFull = document.getElementById("modal-screenshot-full");
  const tabDesk = document.getElementById("tab-shot-desktop");
  const tabMob = document.getElementById("tab-shot-mobile");
  const labelEl = document.getElementById("label-shot-active");

  if (tab === "mobile" && modalMobileUrl) {
    if (shotImg) shotImg.src = modalMobileUrl + "?t=" + Date.now();
    if (shotFull) shotFull.href = modalMobileUrl;
    if (labelEl) labelEl.textContent = "📱 Mobile Viewport Preview (390x844)";
    if (tabDesk) tabDesk.className = "px-3 py-1 rounded-lg bg-slate-800 text-slate-300 text-[11px] font-bold hover:bg-slate-700";
    if (tabMob) tabMob.className = "px-3 py-1 rounded-lg bg-purple-600 text-white text-[11px] font-bold";
  } else if (modalDesktopUrl) {
    if (shotImg) shotImg.src = modalDesktopUrl + "?t=" + Date.now();
    if (shotFull) shotFull.href = modalDesktopUrl;
    if (labelEl) labelEl.textContent = "💻 Desktop Viewport Preview (1280x800)";
    if (tabDesk) tabDesk.className = "px-3 py-1 rounded-lg bg-purple-600 text-white text-[11px] font-bold";
    if (tabMob) tabMob.className = "px-3 py-1 rounded-lg bg-slate-800 text-slate-300 text-[11px] font-bold hover:bg-slate-700";
  }
}

async function sendOwnerReportForCurrentLead() {
  if (!activeModalLeadId) return;
  const btn = document.getElementById("btn-owner-report");
  const origText = btn ? btn.innerHTML : "";
  if (btn) btn.innerHTML = "<span>⏳ Sending Dossier...</span>";

  try {
    const resp = await fetch(`/api/leads/${activeModalLeadId}/send-owner-report`, { method: "POST" });
    const data = await resp.json();
    if (data.ok) {
      alert("✅ Success! Executive Lead Audit Dossier & Screenshots have been dispatched to your personal email.");
      const ownerPill = document.getElementById("modal-owner-sent-pill");
      if (ownerPill) ownerPill.classList.remove("hidden");
      await refreshDashboard();
    } else {
      alert("⚠️ Could not send email: " + (data.error || "Please check .env Gmail credentials"));
    }
  } catch (err) {
    alert("Error sending report: " + err);
  } finally {
    if (btn) btn.innerHTML = origText;
  }
}

async function openAuditModal(leadId) {
  activeModalLeadId = leadId;
  let lead = currentLeads.find((l) => l.id === leadId);
  if (!lead) {
    try {
      const resp = await fetch(`/api/leads/${leadId}`);
      if (resp.ok) lead = await resp.json();
    } catch (e) {
      console.warn("Could not fetch lead details:", e);
    }
  }
  if (!lead) return;

  document.getElementById("modal-lead-name").textContent = lead.business_name;
  document.getElementById("modal-lead-meta").textContent = `${lead.category} • ${lead.location} • ★ ${lead.rating} (${lead.reviews_count} reviews)`;

  const report = lead.audit_report || {};
  document.getElementById("modal-audit-summary").textContent = report.summary || "";
  document.getElementById("modal-audit-issues").innerHTML = (report.issues_found || [])
    .map((i) => `<li>${escapeHtml(i)}</li>`)
    .join("");
  document.getElementById("modal-audit-solutions").innerHTML = (report.recommended_solutions || [])
    .map((s) => `<li>${escapeHtml(s)}</li>`)
    .join("");
  document.getElementById("modal-audit-impact").textContent =
    "📈 Impact: " + (report.estimated_revenue_impact || "+35% direct conversion");

  document.getElementById("modal-email-subject").value = lead.draft_email_subject || "";
  document.getElementById("modal-email-body").value = lead.draft_email_body || "";
  document.getElementById("modal-wa-body").value = lead.draft_whatsapp_msg || "";

  document.getElementById("modal-mockup-link").href = `/preview/${lead.id}`;
  const emailPrevLink = document.getElementById("modal-email-preview-link");
  if (emailPrevLink) emailPrevLink.href = `/api/leads/${lead.id}/email-preview`;

  const shotBox = document.getElementById("modal-screenshot-box");
  const shotImg = document.getElementById("modal-screenshot-img");
  const shotMobileImg = document.getElementById("modal-screenshot-mobile-img");
  const shotFull = document.getElementById("modal-screenshot-full");
  const ownerPill = document.getElementById("modal-owner-sent-pill");

  const desktopShot = lead.screenshot_desktop || report.screenshot_desktop_url || report.screenshot_url || "";
  const mobileShot = lead.screenshot_mobile || report.screenshot_mobile_url || "";
  const mapsShot = lead.maps_screenshot || report.maps_screenshot_url || "";
  const primaryShot = desktopShot || mapsShot || report.screenshot_url || "";

  modalDesktopUrl = desktopShot || primaryShot;
  modalMobileUrl = mobileShot || "";

  if (ownerPill) {
    if (lead.owner_report_sent) ownerPill.classList.remove("hidden");
    else ownerPill.classList.add("hidden");
  }

  if (primaryShot && shotBox && shotImg) {
    shotImg.src = primaryShot + "?t=" + Date.now();
    if (shotMobileImg) {
      if (mobileShot) {
        shotMobileImg.src = mobileShot + "?t=" + Date.now();
        shotMobileImg.parentElement.classList.remove("hidden");
      } else {
        shotMobileImg.parentElement.classList.add("hidden");
      }
    }
    if (shotFull) shotFull.href = primaryShot;
    shotBox.classList.remove("hidden");
    switchScreenshotTab("desktop");
  } else if (shotBox) {
    shotBox.classList.add("hidden");
  }

  document.getElementById("modal-edit-email").value = lead.email || "";
  document.getElementById("modal-edit-phone").value = lead.phone || "";
  document.getElementById("modal-edit-website").value = lead.website || "";

  const modal = document.getElementById("audit-modal");
  modal.classList.remove("hidden");
  modal.classList.add("flex");
}

function closeAuditModal() {
  const modal = document.getElementById("audit-modal");
  modal.classList.add("hidden");
  modal.classList.remove("flex");
}

async function sendManualOutreach(channel) {
  if (!activeModalLeadId) return;
  const subject = document.getElementById("modal-email-subject").value;
  const body =
    channel === "EMAIL"
      ? document.getElementById("modal-email-body").value
      : document.getElementById("modal-wa-body").value;

  await fetch("/api/outreach/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      lead_id: activeModalLeadId,
      channel,
      subject,
      message_body: body,
    }),
  });
  await refreshDashboard();
  alert(`${channel} outreach processed!`);
}

async function simulateReplyFromModal() {
  if (!activeModalLeadId) return;
  const msg = document.getElementById("modal-sim-reply").value.trim();
  if (!msg) return;

  await fetch("/api/sales-agent/simulate-reply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      lead_id: activeModalLeadId,
      channel: "EMAIL",
      message_text: msg,
    }),
  });
  closeAuditModal();
  activeChatLeadId = activeModalLeadId;
  switchWorkspace("chats");
  await refreshDashboard();
}

// ----------------------------------------------------------------------------
// 24/7 AI INBOX, EOD, SETTINGS & HELPERS
// ----------------------------------------------------------------------------
async function loadConversations() {
  const resp = await fetch("/api/conversations");
  if (!resp.ok) return;
  const data = await resp.json();
  groupedConversations = data.conversations || [];

  const listEl = document.getElementById("chat-threads-list");
  if (groupedConversations.length === 0) {
    listEl.innerHTML = `<p class="text-xs text-slate-400 p-6 text-center">No conversations yet.</p>`;
    return;
  }

  if (!activeChatLeadId && groupedConversations.length > 0) {
    activeChatLeadId = groupedConversations[0].id;
  }

  listEl.innerHTML = groupedConversations
    .map((lead) => {
      const isSelected = lead.id === activeChatLeadId;
      const hotBadge = lead.is_hot_lead
        ? `<span class="px-2 py-0.5 rounded-full bg-rose-500 text-white text-[10px] font-bold">🔥 HOT</span>`
        : "";
      return `
        <div onclick="selectChatThread(${lead.id})"
          class="p-3.5 rounded-2xl cursor-pointer transition ${
            isSelected ? "bg-[#efe5fc] text-[#9b51e0]" : "bg-white hover:bg-purple-50/50 text-slate-700"
          }">
          <div class="flex items-center justify-between">
            <span class="font-extrabold text-xs truncate">${escapeHtml(lead.business_name)}</span>
            ${hotBadge}
          </div>
          <div class="text-[11px] opacity-75 mt-0.5">${escapeHtml(lead.category)} • ${escapeHtml(lead.location)}</div>
        </div>
      `;
    })
    .join("");

  renderActiveChatMessages();
}

function selectChatThread(leadId) {
  activeChatLeadId = leadId;
  loadConversations();
}

function renderActiveChatMessages() {
  const thread = groupedConversations.find((c) => c.id === activeChatLeadId);
  const box = document.getElementById("chat-messages-box");
  if (!thread || !box) return;

  document.getElementById("chat-active-title").textContent = `${thread.business_name} (${thread.category})`;
  document.getElementById("chat-active-subtitle").textContent = `${thread.email || ""} • ${thread.phone || ""}`;

  box.innerHTML = (thread.messages || [])
    .map((m) => {
      const isClient = m.sender === "CLIENT";
      return `
        <div class="flex flex-col ${isClient ? "items-start" : "items-end"}">
          <div class="max-w-[80%] rounded-2xl p-3.5 text-xs ${
            isClient ? "bg-white text-slate-800 shadow-sm" : "bg-[#9b51e0] text-white shadow-sm"
          }">
            <div class="text-[10px] opacity-75 mb-1 font-bold">
              ${isClient ? "👤 CLIENT" : "🤖 24/7 AI AGENT"} (${escapeHtml(m.channel)}) • ${escapeHtml(m.detected_intent)}
            </div>
            <div class="whitespace-pre-wrap leading-relaxed">${escapeHtml(m.message_text)}</div>
          </div>
        </div>
      `;
    })
    .join("");
  box.scrollTop = box.scrollHeight;
}

async function simulateClientReplyFromChat() {
  const targetLeadId = activeChatLeadId || (currentLeads[0] && currentLeads[0].id);
  if (!targetLeadId) return;
  const channel = document.getElementById("sim-channel").value;
  const text = document.getElementById("sim-message-input").value.trim();
  if (!text) return;

  document.getElementById("sim-message-input").value = "";
  await fetch("/api/sales-agent/simulate-reply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lead_id: targetLeadId, channel, message_text: text }),
  });
  await loadConversations();
  await refreshDashboard();
}

async function pollRepliesNow() {
  await fetch("/api/sales-agent/poll", { method: "POST" });
  await refreshDashboard();
}

function openWhatsAppModal() {
  const modal = document.getElementById("whatsapp-modal");
  modal.classList.remove("hidden");
  modal.classList.add("flex");
  refreshWhatsAppStatus();
}

function closeWhatsAppModal() {
  const modal = document.getElementById("whatsapp-modal");
  modal.classList.add("hidden");
  modal.classList.remove("flex");
}

async function launchWhatsAppSession() {
  const resp = await fetch("/api/whatsapp/connect", { method: "POST" });
  const data = await resp.json();
  renderWaModal(data.whatsapp);
}

async function refreshWhatsAppStatus() {
  const resp = await fetch("/api/whatsapp/status");
  const data = await resp.json();
  renderWaModal(data.whatsapp);
}

function renderWaModal(wa) {
  if (!wa) return;
  document.getElementById("wa-modal-status").textContent = wa.status_text || "";
  const img = document.getElementById("wa-qr-img");
  const ph = document.getElementById("wa-qr-placeholder");
  if (wa.qr_base64) {
    img.src = wa.qr_base64;
    img.classList.remove("hidden");
    ph.classList.add("hidden");
  } else {
    img.classList.add("hidden");
    ph.classList.remove("hidden");
  }
}

async function loadEodReports() {
  const resp = await fetch("/api/eod-reports");
  if (!resp.ok) return;
  const data = await resp.json();
  if (data.reports?.length > 0) {
    document.getElementById("eod-markdown-preview").textContent = data.reports[0].summary_markdown;
  }
  const listEl = document.getElementById("eod-outreach-list");
  listEl.innerHTML = (data.outreach_logs || [])
    .map(
      (l) => `
      <div class="p-3 rounded-xl bg-white flex items-center justify-between">
        <div>
          <div class="font-bold text-slate-800">${escapeHtml(l.business_name || "Lead")} (${escapeHtml(l.channel)})</div>
          <div class="text-[11px] text-slate-400">${escapeHtml(l.recipient)}</div>
        </div>
        <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-700">${escapeHtml(l.delivery_status)}</span>
      </div>
    `
    )
    .join("");
}

async function generateEodNow() {
  const resp = await fetch("/api/eod-reports/generate", { method: "POST" });
  const data = await resp.json();
  if (data.report?.summary_markdown) {
    document.getElementById("eod-markdown-preview").textContent = data.report.summary_markdown;
  }
  await loadEodReports();
}

async function loadSettingsAndKnowledge() {
  const resp = await fetch("/api/settings");
  if (!resp.ok) return;
  const data = await resp.json();
  const env = data.env || {};
  Object.keys(env).forEach((k) => {
    const el = document.getElementById(`env-${k}`);
    if (el) el.value = env[k];
  });
  document.getElementById("knowledge-textarea").value = data.knowledge_base || "";
}

async function saveEnvSettings() {
  const keys = [
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "GEMINI_COMPLEX_MODEL",
    "GEMINI_FAST_MODEL",
    "GMAIL_ADDRESS",
    "GMAIL_APP_PASSWORD",
    "MY_PERSONAL_EMAIL",
    "SEND_LEAD_REPORTS_TO_OWNER",
    "AGENCY_NAME",
    "SENDER_NAME",
    "AGENCY_OWNER_WHATSAPP",
    "CALENDAR_BOOKING_LINK",
    "DAILY_EMAIL_LIMIT",
    "DAILY_WHATSAPP_LIMIT",
    "MIN_OUTREACH_DELAY_SECONDS",
    "MAX_OUTREACH_DELAY_SECONDS",
  ];
  const updates = {};
  keys.forEach((k) => {
    const el = document.getElementById(`env-${k}`);
    if (el) updates[k] = el.value.trim();
  });
  await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ updates }),
  });
  await refreshDashboard();
  alert("Saved .env settings!");
}

async function saveKnowledgeBase() {
  const content = document.getElementById("knowledge-textarea").value;
  await fetch("/api/knowledge", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  alert("Updated agency_knowledge.txt!");
}

async function runFollowUpSequence() {
  const resp = await fetch("/api/outreach/followup", { method: "POST" });
  const data = await resp.json();
  await refreshDashboard();
  alert(`Follow-up #2 sent to ${data.sent_count || 0} leads!`);
}

async function runLiveDiagnostics() {
  const resp = await fetch("/api/diagnostics", { method: "POST" });
  const data = await resp.json();
  alert(
    `Live Connection Status:\n• AI Brain: ${data.ai_ok ? "✅ OK" : "❌ FAIL"}\n• Gmail SMTP: ${
      data.smtp_ok ? "✅ OK" : "❌ FAIL"
    }\n• Gmail IMAP: ${data.imap_ok ? "✅ OK" : "❌ FAIL"}`
  );
}

async function saveLeadContactChanges() {
  if (!activeModalLeadId) return;
  const email = document.getElementById("modal-edit-email").value.trim();
  const phone = document.getElementById("modal-edit-phone").value.trim();
  const website = document.getElementById("modal-edit-website").value.trim();
  await fetch(`/api/leads/${activeModalLeadId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, phone, website }),
  });
  await fetch(`/api/leads/${activeModalLeadId}/reaudit`, { method: "POST" });
  await openAuditModal(activeModalLeadId);
  await refreshDashboard();
}

async function deleteCurrentLead() {
  if (!activeModalLeadId) return;
  await fetch(`/api/leads/${activeModalLeadId}`, { method: "DELETE" });
  closeAuditModal();
  await refreshDashboard();
}

function openAddLeadModal() {
  const modal = document.getElementById("add-lead-modal");
  modal.classList.remove("hidden");
  modal.classList.add("flex");
}

function closeAddLeadModal() {
  const modal = document.getElementById("add-lead-modal");
  modal.classList.add("hidden");
  modal.classList.remove("flex");
}

async function submitCustomLead() {
  const business_name = document.getElementById("custom-bname").value.trim();
  const category = document.getElementById("custom-cat").value.trim();
  const location = document.getElementById("custom-loc").value.trim();
  const email = document.getElementById("custom-email").value.trim();
  const phone = document.getElementById("custom-phone").value.trim();
  const website = document.getElementById("custom-website").value.trim();
  if (!business_name) return;

  closeAddLeadModal();
  await fetch("/api/leads/custom", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ business_name, category, location, email, phone, website }),
  });
  await refreshDashboard();
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
