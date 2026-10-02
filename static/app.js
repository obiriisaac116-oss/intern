/* =====================================================================
   Internship Tracker — single-page frontend
   ===================================================================== */
"use strict";

// ─────────────────────────────────────────────
// Utilities
// ─────────────────────────────────────────────

function initials(name) {
  return (name || "").trim().split(/\s+/).map(w => w[0]).join("").toUpperCase().slice(0, 2) || "?";
}
function fmtTime(iso) {
  if (!iso) return "—";
  return new Date(iso.replace(" ", "T")).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
function fmtDate(iso) {
  if (!iso) return null;
  const [y, m, d] = iso.split("-");
  const mo = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${mo[+m - 1]} ${+d}, ${y}`;
}
function esc(s) {
  if (s == null) return "";
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
                  .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}
async function api(method, path, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.error || `Error ${res.status}`);
  return json;
}

// ─────────────────────────────────────────────
// Toast
// ─────────────────────────────────────────────

function toast(msg, type = "info") {
  const icons = { success: "✓", error: "✕", info: "ℹ" };
  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
  el.innerHTML = `<span class="toast-icon">${icons[type]}</span><span>${esc(msg)}</span>`;
  document.getElementById("toast-container").appendChild(el);
  setTimeout(() => {
    el.classList.add("toast-out");
    el.addEventListener("animationend", () => el.remove(), { once: true });
  }, 3200);
}

// ─────────────────────────────────────────────
// Live clock
// ─────────────────────────────────────────────

function updateClock() {
  const el = document.getElementById("nav-clock");
  if (el) el.textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
updateClock();
setInterval(updateClock, 1000);

// ─────────────────────────────────────────────
// Intern card rendering — TIME LEFT as hero
// ─────────────────────────────────────────────

function heroColor(p) {
  if (!p.end_date || p.status === "unknown") return "ic-hero-new";
  if (p.status === "ended")    return "ic-hero-ended";
  if (p.status === "upcoming") return "ic-hero-ok";
  // active — color by urgency
  const d = p.days_remaining ?? 9999;
  if (d <= 7)  return "ic-hero-urgent";
  if (d <= 21) return "ic-hero-soon";
  return "ic-hero-ok";
}

function heroBlock(p) {
  // No dates at all
  if (!p.start_date && !p.end_date) {
    return `<div class="ic-no-dates">No internship dates set</div>`;
  }

  const cal = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>`;

  const startLabel = p.start_date ? fmtDate(p.start_date) : "—";
  const endLabel   = p.end_date   ? fmtDate(p.end_date)   : "No end set";

  let statusBadge = "";
  if      (p.status === "active")   statusBadge = `<span class="status-badge status-active">● Active</span>`;
  else if (p.status === "ended")    statusBadge = `<span class="status-badge status-ended">Ended</span>`;
  else if (p.status === "upcoming") statusBadge = `<span class="status-badge status-upcoming">Upcoming</span>`;

  // Hero number: days remaining (or days in for upcoming, or ended)
  let heroNum = "—", heroUnit = "", heroSub = "";
  if (p.status === "active") {
    heroNum  = p.days_remaining ?? "—";
    heroUnit = "days left";
    heroSub  = p.weeks_remaining != null ? `${p.weeks_remaining} wks · ${p.months_remaining} mo` : "";
  } else if (p.status === "upcoming") {
    heroNum  = p.days_remaining ?? "—";
    heroUnit = "days until start";
    heroSub  = p.weeks_remaining != null ? `${p.weeks_remaining} wks away` : "";
  } else if (p.status === "ended") {
    heroNum  = p.days_elapsed ?? "—";
    heroUnit = "days completed";
    heroSub  = "Internship ended";
  }

  const cls = heroColor(p);

  // Progress
  let progressHtml = "";
  if (p.pct_complete != null) {
    const pct   = Math.min(100, Math.max(0, p.pct_complete));
    const color = p.status === "ended" ? "var(--text3)"
                : pct > 75             ? "var(--red)"
                : pct > 40             ? "var(--amber)"
                                       : "var(--accent)";
    progressHtml = `
      <div class="ic-progress">
        <div class="ic-progress-bar"><div class="ic-progress-fill" style="width:${pct}%;background:${color}"></div></div>
        <span class="ic-progress-pct">${pct}%</span>
      </div>`;
  }

  // Stat boxes
  const statsArr = [];
  if (p.days_elapsed    != null) statsArr.push({ n: p.days_elapsed,    l: "Days in" });
  if (p.days_remaining  != null && p.status !== "ended") statsArr.push({ n: p.days_remaining,  l: "Days left" });
  if (p.weeks_remaining != null && p.status !== "ended") statsArr.push({ n: p.weeks_remaining, l: "Wks left" });
  if (p.months_remaining!= null && p.status !== "ended") statsArr.push({ n: p.months_remaining,l: "Mo left" });

  const statsHtml = statsArr.length ? `
    <div class="ic-stats">
      ${statsArr.map(s => `
        <div class="ic-stat">
          <span class="ic-stat-num">${s.n}</span>
          <span class="ic-stat-lbl">${s.l}</span>
        </div>`).join("")}
    </div>` : "";

  return `
    <div class="ic-hero">
      <span class="ic-hero-num ${cls}">${heroNum}</span>
      <span class="ic-hero-unit">${heroUnit}</span>
      ${heroSub ? `<span class="ic-hero-sub">${esc(heroSub)}</span>` : ""}
    </div>
    <div class="ic-dates">
      <span class="ic-date">${cal} ${esc(startLabel)}</span>
      <span style="color:var(--text3);font-size:.7rem">→</span>
      <span class="ic-date">${cal} ${esc(endLabel)}</span>
      ${statusBadge}
    </div>
    ${statsHtml}
    ${progressHtml}`;
}

function renderInternCards(list) {
  const el = document.getElementById("intern-cards");
  document.getElementById("stat-total-num").textContent = list.length;

  if (!list.length) {
    el.innerHTML = `<p class="loading-text">No interns registered yet. Use the form above to add one.</p>`;
    return;
  }

  // Sort: active first (by least days remaining), then upcoming, then ended/unknown
  const order = { active: 0, upcoming: 1, ended: 2, unknown: 3 };
  const sorted = [...list].sort((a, b) => {
    const oa = order[a.status] ?? 3, ob = order[b.status] ?? 3;
    if (oa !== ob) return oa - ob;
    return (a.days_remaining ?? 9999) - (b.days_remaining ?? 9999);
  });

  el.innerHTML = sorted.map((p, i) => `
    <div class="intern-card" style="animation-delay:${i * 30}ms">
      <div class="ic-top">
        <div class="ic-avatar">${initials(p.name)}</div>
        <div class="ic-info">
          <div class="ic-name">${esc(p.name)}</div>
          <div class="ic-reg">Registered ${p.created_at ? p.created_at.slice(0,10) : "—"}</div>
        </div>
        <div class="ic-right">
          <span class="visit-badge">${p.visit_count} visit${p.visit_count !== 1 ? "s" : ""}</span>
          <button class="btn-remove" data-id="${p.id}" data-name="${esc(p.name)}" title="Remove intern">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>
          </button>
        </div>
      </div>
      ${heroBlock(p)}
    </div>`).join("");

  el.querySelectorAll(".btn-remove").forEach(btn => {
    btn.addEventListener("click", async () => {
      if (!confirm(`Remove "${btn.dataset.name}"? This also deletes all their check-in history.`)) return;
      try {
        await api("DELETE", `/api/interns/${btn.dataset.id}`);
        toast(`${btn.dataset.name} removed`, "info");
        loadPage();
      } catch (err) { toast(err.message, "error"); }
    });
  });
}

// ─────────────────────────────────────────────
// Load / filter interns
// ─────────────────────────────────────────────

let _allInterns = [];

async function loadInterns(q = "") {
  try {
    _allInterns = await api("GET", "/api/interns");
    filterInterns(q);
  } catch (e) {
    document.getElementById("intern-cards").innerHTML =
      `<p style="color:var(--red);grid-column:1/-1;padding:16px 0;font-size:.85rem">${esc(e.message)}</p>`;
  }
}

function filterInterns(q) {
  if (!q) { renderInternCards(_allInterns); return; }
  const lq = q.toLowerCase();
  renderInternCards(_allInterns.filter(p => p.name.toLowerCase().includes(lq)));
}

document.getElementById("intern-search").addEventListener("input", function () {
  filterInterns(this.value.trim());
});

// ─────────────────────────────────────────────
// Check-in / Register — unified flow
// ─────────────────────────────────────────────

const checkinInput   = document.getElementById("checkin-input");
const lookupResult   = document.getElementById("lookup-result");
const confirmBtn     = document.getElementById("confirm-checkin-btn");
const clearBtn       = document.getElementById("clear-input-btn");
const registerPanel  = document.getElementById("register-panel");
const addInternBtn   = document.getElementById("add-intern-btn");
const saveOnlyBtn    = document.getElementById("save-only-btn");
const addInternError = document.getElementById("add-intern-error");

let selectedIntern = null, lookupTimer = null;
let pendingNewName = "";   // name typed when no match found

function resetEntry() {
  checkinInput.value = "";
  clearBtn.classList.add("hidden");
  lookupResult.classList.add("hidden");
  lookupResult.innerHTML = "";
  confirmBtn.classList.add("hidden");
  registerPanel.classList.add("hidden");
  addInternError.textContent = "";
  document.getElementById("new-intern-start").value = "";
  document.getElementById("new-intern-end").value   = "";
  delete registerPanel.dataset.renewId;
  selectedIntern = null;
  pendingNewName = "";
}

checkinInput.addEventListener("input", () => {
  clearTimeout(lookupTimer);
  const q = checkinInput.value.trim();
  clearBtn.classList.toggle("hidden", !q);
  selectedIntern = null;
  confirmBtn.classList.add("hidden");
  registerPanel.classList.add("hidden");
  addInternError.textContent = "";

  if (!q) { lookupResult.classList.add("hidden"); lookupResult.innerHTML = ""; return; }
  lookupTimer = setTimeout(() => doLookup(q), 180);
});

clearBtn.addEventListener("click", () => { resetEntry(); checkinInput.focus(); });

checkinInput.addEventListener("keydown", e => {
  if (e.key === "Enter" && selectedIntern && !selectedIntern.is_here) { e.preventDefault(); doConfirmCheckin(); }
});

async function doLookup(q) {
  try {
    const results = await api("GET", `/api/lookup?q=${encodeURIComponent(q)}`);
    renderLookup(results, q);
  } catch (e) {
    lookupResult.innerHTML = `<p style="color:var(--red);font-size:.82rem;padding:6px 0">${esc(e.message)}</p>`;
    lookupResult.classList.remove("hidden");
  }
}

function renderLookup(results, q) {
  confirmBtn.classList.add("hidden");

  if (!results.length) {
    // Name not found — show inline register panel
    lookupResult.innerHTML = `
      <div class="lookup-none">
        <span class="lookup-none-text"><strong>${esc(q)}</strong> isn't registered yet.</span>
      </div>`;
    lookupResult.classList.remove("hidden");
    pendingNewName = q;
    showRegisterPanel("new");
    return;
  }

  registerPanel.classList.add("hidden");
  lookupResult.innerHTML = results.map(p => {
    const pillCls  = p.is_here ? "pill-here"  : (p.visit_status === "new" ? "pill-new" : "pill-returning");
    const pillText = p.is_here ? "Here now"   : (p.visit_status === "new" ? "First time" : `${p.visit_count}× visits`);
    // Show "Ended" badge if their period is over
    const endedBadge = (p.status === "ended")
      ? `<span class="match-pill pill-ended">Period ended</span>` : "";
    return `
      <div class="lookup-match" data-id="${p.id}">
        <div class="match-avatar">${initials(p.name)}</div>
        <div class="match-body">
          <div class="match-name">${esc(p.name)}</div>
          <div class="match-msg">${esc(p.visit_message)}</div>
        </div>
        ${endedBadge || `<span class="match-pill ${pillCls}">${pillText}</span>`}
      </div>`;
  }).join("");
  lookupResult.classList.remove("hidden");

  lookupResult.querySelectorAll(".lookup-match").forEach(el => {
    el.addEventListener("click", () => selectIntern(results.find(r => r.id === parseInt(el.dataset.id))));
  });
  if (results.length === 1) selectIntern(results[0]);
}

function selectIntern(intern) {
  selectedIntern = intern;
  lookupResult.querySelectorAll(".lookup-match").forEach(el => {
    el.classList.toggle("selected", parseInt(el.dataset.id) === intern.id);
  });

  // Already here today
  if (intern.is_here) {
    confirmBtn.textContent = `${intern.name} is already here`;
    confirmBtn.disabled = true;
    confirmBtn.classList.remove("hidden");
    registerPanel.classList.add("hidden");
    return;
  }

  // Internship period has ended — ask for new dates before checking in
  if (intern.status === "ended") {
    confirmBtn.classList.add("hidden");
    pendingNewName = intern.name;
    showRegisterPanel("renew", intern);
    return;
  }

  // Normal check-in
  registerPanel.classList.add("hidden");
  confirmBtn.innerHTML = `
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>
    Check in ${esc(intern.name)}`;
  confirmBtn.disabled = false;
  confirmBtn.classList.remove("hidden");
}

// mode = "new" | "renew"
function showRegisterPanel(mode, intern = null) {
  const head     = registerPanel.querySelector(".register-panel-head span");
  const startEl  = document.getElementById("new-intern-start");
  const endEl    = document.getElementById("new-intern-end");
  addInternError.textContent = "";
  startEl.value = "";
  endEl.value   = "";

  if (mode === "renew") {
    head.textContent = `${intern.name}'s period ended — enter new dates to check in again`;
    registerPanel.dataset.renewId = intern.id;
  } else {
    head.textContent = "New intern — set dates then save";
    delete registerPanel.dataset.renewId;
  }

  registerPanel.classList.remove("hidden");
}

confirmBtn.addEventListener("click", doConfirmCheckin);

async function doConfirmCheckin() {
  if (!selectedIntern || selectedIntern.is_here) return;
  await doCheckinById(selectedIntern.id, selectedIntern.name);
}

async function doCheckinById(id, name) {
  try {
    await api("POST", "/api/checkin", { intern_id: id });
    resetEntry();
    await refreshTodayPanels();
    loadInterns();
    toast(`${name} checked in`, "success");
  } catch (err) { toast(err.message, "error"); }
}

// Save & check in (for new intern OR renew)
addInternBtn.addEventListener("click", () => saveNewIntern(true));
// Save only (no check-in)
saveOnlyBtn.addEventListener("click", () => saveNewIntern(false));

async function saveNewIntern(andCheckin) {
  const start   = document.getElementById("new-intern-start").value || null;
  const end     = document.getElementById("new-intern-end").value   || null;
  const renewId = registerPanel.dataset.renewId;   // set when renewing
  const name    = pendingNewName.trim();
  addInternError.textContent = "";

  if (!name) return;
  if (!start) { addInternError.textContent = "Start date is required."; return; }

  const btn = andCheckin ? addInternBtn : saveOnlyBtn;
  btn.disabled = true;
  const origHtml = btn.innerHTML;
  btn.innerHTML = "Saving…";

  try {
    let internId;

    if (renewId) {
      // Returning intern — update their dates via renew endpoint
      const updated = await api("POST", `/api/interns/${renewId}/renew`, { start_date: start, end_date: end });
      internId = updated.id;
      if (andCheckin) {
        await api("POST", "/api/checkin", { intern_id: internId });
        toast(`${name} renewed & checked in`, "success");
      } else {
        toast(`${name}'s internship renewed`, "success");
      }
    } else {
      // Brand-new intern
      const intern = await api("POST", "/api/interns", { name, start_date: start, end_date: end });
      internId = intern.id;
      if (andCheckin) {
        await api("POST", "/api/checkin", { intern_id: internId });
        toast(`${name} registered & checked in`, "success");
      } else {
        toast(`${name} registered`, "success");
      }
    }

    resetEntry();
    await refreshTodayPanels();
    loadInterns();
  } catch (err) {
    addInternError.textContent = err.message;
    btn.disabled = false;
    btn.innerHTML = origHtml;
  }
}

// ─────────────────────────────────────────────
// Today panels
// ─────────────────────────────────────────────

async function refreshTodayPanels() {
  try {
    const [here, left] = await Promise.all([api("GET", "/api/here"), api("GET", "/api/left")]);
    renderHere(here);
    renderLeft(left);
    document.getElementById("stat-here-num").textContent = here.length;
    document.getElementById("here-count").textContent    = here.length;
    document.getElementById("left-count").textContent    = left.length;
  } catch (e) { console.error(e); }
}

function renderHere(list) {
  const el = document.getElementById("here-list");
  if (!list.length) { el.innerHTML = `<p class="empty-state">Nobody here yet</p>`; return; }
  el.innerHTML = list.map(p => `
    <div class="person-row">
      <div class="row-avatar">${initials(p.name)}</div>
      <div class="row-info">
        <div class="row-name">${esc(p.name)}</div>
        <div class="row-meta">
          <span class="row-time">In ${fmtTime(p.checked_in_at)}</span>
          <span class="row-dot">·</span>
          <span class="row-visits">${p.visit_count} visit${p.visit_count !== 1 ? "s" : ""}</span>
        </div>
      </div>
      <button class="btn-checkout" data-cid="${p.checkin_id}" data-name="${esc(p.name)}">Check out</button>
    </div>`).join("");

  el.querySelectorAll(".btn-checkout").forEach(btn => {
    btn.addEventListener("click", async () => {
      btn.disabled = true; btn.textContent = "…";
      try {
        await api("POST", `/api/checkout/${btn.dataset.cid}`);
        await refreshTodayPanels();
        toast(`${btn.dataset.name} checked out`, "info");
      } catch (err) {
        toast(err.message, "error");
        btn.disabled = false; btn.textContent = "Check out";
      }
    });
  });
}

function renderLeft(list) {
  const el = document.getElementById("left-list");
  if (!list.length) { el.innerHTML = `<p class="empty-state">Nobody has left yet</p>`; return; }
  el.innerHTML = list.map(p => `
    <div class="person-row">
      <div class="row-avatar" style="background:linear-gradient(135deg,#6a7a9a,#8a9ac0)">${initials(p.name)}</div>
      <div class="row-info">
        <div class="row-name">${esc(p.name)}</div>
        <div class="row-meta">
          <span class="row-time">${fmtTime(p.checked_in_at)}</span>
          <span class="time-arrow">→</span>
          <span class="row-time">${fmtTime(p.checked_out_at)}</span>
        </div>
      </div>
    </div>`).join("");
}

document.getElementById("checkout-all-btn").addEventListener("click", async () => {
  const n = document.getElementById("here-list").querySelectorAll(".person-row").length;
  if (!n) { toast("Nobody is here to check out", "info"); return; }
  try {
    await api("POST", "/api/checkout/all");
    await refreshTodayPanels();
    toast("Everyone checked out", "success");
  } catch (err) { toast(err.message, "error"); }
});

// ─────────────────────────────────────────────
// Boot
// ─────────────────────────────────────────────

async function loadPage() {
  await Promise.all([loadInterns(), refreshTodayPanels()]);
}

loadPage();
setInterval(refreshTodayPanels, 30_000);
