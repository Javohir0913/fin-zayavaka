(() => {
  "use strict";
  const tg = window.Telegram && window.Telegram.WebApp;
  const app = document.getElementById("app");

  // ------------------------------------------------------------ storage
  const store = {
    get(k) { try { return localStorage.getItem("xr_" + k); } catch (_) { return null; } },
    set(k, v) { try { localStorage.setItem("xr_" + k, v); } catch (_) { /* private mode */ } },
  };

  const S = {
    me: null,
    lang: "uz",
    themePref: store.get("theme") || "auto",
    period: store.get("period") || "month",
    list: null,
    acts: {},
    renderId: 0,
    pendingCount: 0,
  };

  // ------------------------------------------------------------ i18n
  function pickLang() {
    const saved = store.get("lang");
    if (saved && I18N[saved]) return saved;
    const code = ((tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.language_code) || navigator.language || "uz").slice(0, 2);
    return I18N[code] ? code : (code === "be" || code === "uk" || code === "kk" ? "ru" : "uz");
  }
  S.lang = pickLang();
  const t = (k, vars) => {
    let s = (I18N[S.lang] && I18N[S.lang][k]) || I18N.uz[k] || k;
    if (vars) for (const [a, b] of Object.entries(vars)) s = s.replace("{" + a + "}", b);
    return s;
  };
  const LOCALE = { uz: "uz-UZ", ru: "ru-RU", en: "en-US" };

  // ------------------------------------------------------------ format
  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  function fmt(n, digits) {
    if (n == null || isNaN(n)) return "—";
    const d = digits != null ? digits : (Math.abs(n) >= 1000 || Number.isInteger(n) ? 0 : 2);
    return new Intl.NumberFormat(S.lang === "en" ? "en-US" : "ru-RU", { maximumFractionDigits: d, minimumFractionDigits: 0 }).format(n).replace(/ /g, " ");
  }
  function fmtShort(n) {
    if (n == null || isNaN(n)) return "—";
    const u = { uz: ["ming", "mln", "mlrd"], ru: ["тыс", "млн", "млрд"], en: ["K", "M", "B"] }[S.lang];
    const sep = S.lang === "en" ? "" : " ";
    const a = Math.abs(n);
    if (a >= 1e9) return fmt(n / 1e9, 1) + sep + u[2];
    if (a >= 1e6) return fmt(n / 1e6, 1) + sep + u[1];
    if (a >= 1e4) return fmt(n / 1e3, 0) + sep + u[0];
    return fmt(n);
  }
  function parseD(iso) {
    if (!iso) return null;
    const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
    return new Date(y, m - 1, d);
  }
  const UZ_M = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"];
  const UZ_MS = ["yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek"];
  const UZ_WD = ["Yak", "Dush", "Sesh", "Chor", "Pay", "Jum", "Shan"];
  function fmtDate(iso, opts) {
    const d = parseD(iso);
    if (!d) return "—";
    opts = opts || { day: "numeric", month: "short", year: "numeric" };
    if (S.lang === "uz") { // brauzerlarda o'zbekcha oy nomlari ko'pincha yo'q
      let s = d.getDate() + " " + (opts.month === "long" ? UZ_M : UZ_MS)[d.getMonth()];
      if (opts.year) s += " " + d.getFullYear();
      if (opts.weekday) s = UZ_WD[d.getDay()] + ", " + s;
      return s;
    }
    return new Intl.DateTimeFormat(LOCALE[S.lang], opts).format(d);
  }
  function monthShort(d) { return S.lang === "uz" ? UZ_MS[d.getMonth()] : new Intl.DateTimeFormat(LOCALE[S.lang], { month: "short" }).format(d); }
  function fmtDT(s) {
    if (!s) return "—";
    const [dp, tp] = s.split(" ");
    return fmtDate(dp, { day: "numeric", month: "short" }) + (tp ? ", " + tp.slice(0, 5) : "");
  }
  function todayIso() { return (S.me && S.me.today) || new Date().toISOString().slice(0, 10); }
  function addDays(iso, n) {
    const d = parseD(iso); d.setDate(d.getDate() + n);
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }
  function daysFromToday(iso) { return Math.round((parseD(iso) - parseD(todayIso())) / 864e5); }
  function dueLabel(iso, status) {
    if (status && status !== "pending" && status !== "approved") return "";
    const n = daysFromToday(iso);
    if (n < 0 && status === "approved") return ""; // tasdiqlangan va sanasi o'tgan — ogohlantirish shart emas
    if (n === 0) return t("today_l");
    if (n === 1) return t("tomorrow_l");
    if (n > 1) return t("days_left", { n });
    return t("days_ago", { n: -n });
  }
  function hours(h) {
    if (h == null) return "—";
    if (h < 1) return Math.max(1, Math.round(h * 60)) + " " + t("m_unit");
    if (h < 48) return fmt(h, 1) + " " + t("h_unit");
    return fmt(h / 24, 1) + " " + t("d_unit");
  }
  const initials = (name) => esc((name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "?");

  // ------------------------------------------------------------ icons (lucide-style)
  const P = {
    home: '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
    list: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    calendar: '<rect x="3" y="4.5" width="18" height="16.5" rx="2.5"/><path d="M3 9.5h18M8 2.5v4M16 2.5v4"/>',
    grid: '<rect x="3.5" y="3.5" width="7" height="7" rx="2"/><rect x="13.5" y="3.5" width="7" height="7" rx="2"/><rect x="3.5" y="13.5" width="7" height="7" rx="2"/><rect x="13.5" y="13.5" width="7" height="7" rx="2"/>',
    check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    x: '<path d="M6 6l12 12M18 6 6 18"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    alert: '<path d="M12 3 2.5 20h19z"/><path d="M12 10v4.5M12 17.5v.01"/>',
    file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
    clip: '<path d="m21 11.5-8.6 8.6a5 5 0 0 1-7.1-7.1l8.6-8.6a3.3 3.3 0 0 1 4.7 4.7l-8.6 8.6a1.7 1.7 0 0 1-2.4-2.4l8-8"/>',
    send: '<path d="M21 3 10 14M21 3l-7 18-4-7-7-4z"/>',
    edit: '<path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
    trash: '<path d="M4 7h16M10 11v6M14 11v6M5.5 7l1 13h11l1-13M9 7V4h6v3"/>',
    up: '<path d="M12 19V5M6 11l6-6 6 6"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6.5 6.5 0 0 1 3.5 6"/>',
    sliders: '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    coins: '<circle cx="9" cy="9" r="6"/><path d="M15.5 9.2A6 6 0 1 1 9.2 15.5"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    chev: '<path d="m9 6 6 6-6 6"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
    refresh: '<path d="M20 11a8 8 0 0 0-14.6-4.5L3 9M4 13a8 8 0 0 0 14.6 4.5L21 15"/><path d="M3 4v5h5M21 20v-5h-5"/>',
    download: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
    wallet: '<path d="M3 7a2 2 0 0 1 2-2h13v4"/><path d="M3 7v11a2 2 0 0 0 2 2h15V9H5a2 2 0 0 1-2-2z"/><path d="M16 14.5h.01"/>',
    trend: '<path d="m3 17 6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    percent: '<path d="M19 5 5 19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/>',
    hash: '<path d="M5 9h14M5 15h14M10 3 8 21M16 3l-2 18"/>',
    ban: '<circle cx="12" cy="12" r="9"/><path d="m5.7 5.7 12.6 12.6"/>',
    undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    lock: '<rect x="4.5" y="10.5" width="15" height="10.5" rx="2.5"/><path d="M8 10.5V7a4 4 0 0 1 8 0v3.5"/>',
    inbox: '<path d="M3 13h5l1.5 3h5L16 13h5"/><path d="M5.5 5h13L21 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-6z"/>',
    telegram: '<path d="M21 4 3 11l6 2.5M21 4l-3 16-9-6.5M21 4 9 13.5V19l3-3.5"/>',
  };
  const ic = (name, extra) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" ${extra || ""}>${P[name] || ""}</svg>`;

  const STATUS_COLOR = { approved: "var(--success)", pending: "var(--warning)", rejected: "var(--danger)", cancelled: "var(--neutral)" };
  const STATUS_ICON = { approved: "check", pending: "clock", rejected: "x", cancelled: "ban" };
  const HIST = { created: ["plus", "bg-primary"], edited: ["edit", "bg-primary"], approved: ["check", "bg-success"], rejected: ["x", "bg-danger"], cancelled: ["ban", "s-cancelled"], reopened: ["undo", "bg-warning"] };
  const badge = (st) => `<span class="badge s-${st}">${t("st_" + st)}</span>`;
  const can = (p) => !!(S.me && S.me.perms.includes(p));

  // ------------------------------------------------------------ telegram + theme
  function haptic(kind) {
    try {
      if (!tg || !tg.HapticFeedback) return;
      if (kind === "success" || kind === "error" || kind === "warning") tg.HapticFeedback.notificationOccurred(kind);
      else if (kind === "select") tg.HapticFeedback.selectionChanged();
      else tg.HapticFeedback.impactOccurred(kind || "light");
    } catch (_) { /* old client */ }
  }
  function applyTheme() {
    let mode = S.themePref;
    if (mode === "auto") {
      mode = tg && tg.colorScheme ? tg.colorScheme : (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    }
    document.documentElement.dataset.theme = mode;
    const bg = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim();
    const surface = getComputedStyle(document.documentElement).getPropertyValue("--surface").trim();
    try {
      if (tg) {
        tg.setHeaderColor && tg.setHeaderColor(bg);
        tg.setBackgroundColor && tg.setBackgroundColor(bg);
        tg.setBottomBarColor && tg.setBottomBarColor(surface);
      }
    } catch (_) { /* unsupported */ }
  }

  // ------------------------------------------------------------ api
  class ApiErr extends Error { constructor(code, msg, status) { super(code); this.code = code; this.msg = msg; this.status = status; } }
  async function api(method, path, body, isForm) {
    const headers = { Authorization: "tma " + (tg ? tg.initData : "") };
    let payload;
    if (body !== undefined) {
      if (isForm) payload = body;
      else { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
    }
    let res;
    try { res = await fetch(path, { method, headers, body: payload }); }
    catch (_) { throw new ApiErr("network"); }
    let data = null;
    try { data = await res.json(); } catch (_) { /* non-json */ }
    if (!res.ok) throw new ApiErr((data && data.error) || "server", data && data.message, res.status);
    return data;
  }
  function errText(e) {
    if (!e || !e.code) return t("err_generic");
    if (e.code === "network") return t("err_network");
    const k = "e_" + e.code;
    const s = t(k, { m: e.msg || "" });
    return s === k ? t("err_generic") : s;
  }

  // ------------------------------------------------------------ ui helpers
  let toastTimer;
  function toast(text, isErr) {
    document.querySelectorAll(".toast").forEach((n) => n.remove());
    const el = document.createElement("div");
    el.className = "toast" + (isErr ? " err" : "");
    el.innerHTML = ic(isErr ? "alert" : "check", 'width="18" height="18"') + `<span>${esc(text)}</span>`;
    document.body.appendChild(el);
    haptic(isErr ? "error" : "success");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.remove(), 2600);
  }
  function sheet(html, onMount) {
    closeSheet();
    const ov = document.createElement("div"); ov.className = "overlay"; ov.id = "ov";
    const sh = document.createElement("div"); sh.className = "sheet"; sh.id = "sh";
    sh.innerHTML = `<div class="grab"></div>${html}`;
    ov.onclick = closeSheet;
    document.body.append(ov, sh);
    if (onMount) onMount(sh);
    return sh;
  }
  function closeSheet() { ["ov", "sh"].forEach((id) => { const n = document.getElementById(id); if (n) n.remove(); }); }
  function confirmSheet(text, okLabel, danger) {
    return new Promise((resolve) => {
      sheet(`<h3>${esc(text)}</h3><div class="btn-row mt16"><button class="btn btn-ghost" id="cN">${t("cancel")}</button><button class="btn ${danger ? "btn-danger" : "btn-primary"}" id="cY">${esc(okLabel)}</button></div>`, (sh) => {
        sh.querySelector("#cN").onclick = () => { closeSheet(); resolve(false); };
        sh.querySelector("#cY").onclick = () => { closeSheet(); resolve(true); };
      });
    });
  }
  function busy(btn, on) { if (!btn) return; btn.disabled = on; if (on) { btn.dataset.html = btn.innerHTML; btn.innerHTML = '<span class="spinner" style="margin:0;width:18px;height:18px;border-color:rgba(255,255,255,.35);border-top-color:#fff"></span>'; } else if (btn.dataset.html) btn.innerHTML = btn.dataset.html; }
  const skeleton = (n) => Array.from({ length: n || 4 }, () => '<div class="skel" style="height:74px;margin-bottom:10px"></div>').join("");

  function tabbar(active) {
    const tab = (id, icon, label, href, dot) => `<button class="tab ${active === id ? "on" : ""}" data-go="${href}">${ic(icon)}<span>${label}</span>${dot ? `<span class="dotc">${dot > 99 ? "99+" : dot}</span>` : ""}</button>`;
    return `<nav class="tabbar"><div class="in">
      ${tab("home", "home", t("tab_home"), "#/home")}
      ${tab("requests", "list", t("tab_requests"), "#/requests", can("decide") ? S.pendingCount : 0)}
      <button class="fab" data-go="#/new" aria-label="${t("new_request")}">${ic("plus")}</button>
      ${tab("due", "calendar", t("tab_due"), "#/due")}
      ${tab("more", "grid", t("tab_more"), "#/more")}
    </div></nav>`;
  }

  function itemHtml(r, showAuthor) {
    const due = dueLabel(r.needed_date, r.status);
    const overdue = r.status === "pending" && daysFromToday(r.needed_date) < 0;
    const meta = [showAuthor ? esc(r.author_name || "") : null, fmtDate(r.needed_date, { day: "numeric", month: "short" }) + (due ? ` · <span class="${overdue ? "due-warn" : ""}">${esc(due)}</span>` : "")].filter(Boolean).join(" · ");
    return `<button class="item" data-go="#/r/${r.id}">
      <div class="cur bg-${{ approved: "success", pending: "warning", rejected: "danger", cancelled: "primary" }[r.status]}" ${r.status === "cancelled" ? 'style="background:var(--neutral-soft);color:var(--neutral)"' : ""}>${esc(r.currency)}</div>
      <div class="mid"><div class="t">${esc(r.title)}</div><div class="m">#${r.id} · ${meta}</div></div>
      <div class="r"><div class="amt num">${fmt(r.amount)}</div>${badge(r.status)}</div>
    </button>`;
  }

  // ------------------------------------------------------------ router
  const routes = [
    [/^#\/home$/, screenHome, true],
    [/^#\/requests$/, screenRequests, true],
    [/^#\/r\/(\d+)$/, screenDetail, false],
    [/^#\/new$/, screenForm, false],
    [/^#\/edit\/(\d+)$/, screenForm, false],
    [/^#\/due$/, screenDue, true],
    [/^#\/more$/, screenMore, true],
    [/^#\/admin\/users$/, screenUsers, false],
    [/^#\/admin\/fields$/, screenFields, false],
    [/^#\/admin\/currencies$/, screenCurrencies, false],
    [/^#\/admin\/audit$/, screenAudit, false],
  ];
  async function route() {
    closeSheet();
    const h = location.hash || "#/home";
    const id = ++S.renderId;
    S.acts = {};
    for (const [re, fn, top] of routes) {
      const m = h.match(re);
      if (m) {
        if (tg && tg.BackButton) { top ? tg.BackButton.hide() : tg.BackButton.show(); }
        window.scrollTo(0, 0);
        try { await fn(id, ...m.slice(1)); }
        catch (e) { if (id === S.renderId) renderError(e); }
        return;
      }
    }
    location.replace("#/home");
  }
  const alive = (id) => id === S.renderId;
  function renderError(e) {
    if (e && e.code === "pending" || e && e.code === "blocked") return boot();
    app.innerHTML = `<div class="center-screen"><div><div class="ill bg-danger">${ic("alert")}</div><h2>${esc(errText(e))}</h2><button class="btn btn-ghost mt16" data-act="retry">${ic("refresh")} ${t("back")}</button></div></div>`;
    S.acts.retry = () => history.length > 1 ? history.back() : route();
  }

  document.addEventListener("click", (ev) => {
    const go = ev.target.closest("[data-go]");
    if (go) { haptic("light"); const to = go.dataset.go; if (location.hash === to) route(); else location.hash = to; return; }
    const act = ev.target.closest("[data-act]");
    if (act && S.acts[act.dataset.act]) { S.acts[act.dataset.act](act, ev); }
  });

  // ------------------------------------------------------------ HOME
  async function screenHome(id) {
    const name = esc((S.me.user.full_name || "").split(" ")[0]);
    const head = `<div class="topbar"><div style="display:flex;gap:12px;align-items:center"><div class="avatar">${initials(S.me.user.full_name)}</div><div><div class="sub">${t("hello")} 👋</div><h1 style="font-size:20px">${name}</h1></div></div>
      <button class="btn btn-ghost btn-sm" data-go="#/more" aria-label="${t("settings")}">${ic("globe", 'width="16" height="16"')} ${S.lang.toUpperCase()}</button></div>`;
    if (!can("analytics")) return homeSimple(id, head);
    // Kesh: avval oxirgi ma'lumotni darhol ko'rsatamiz, keyin fonda yangilaymiz
    S.dash = S.dash || {};
    const cached = S.dash[S.period];
    const screen = app.querySelector(".screen.home");
    if (cached) renderHome(cached);
    else if (screen) { // davr almashtirildi: sahifani skeletonga aylantirmay, faqat xiralashtiramiz
      screen.classList.add("loading");
      screen.querySelectorAll("#period button").forEach((b) => b.classList.toggle("on", b.dataset.p === S.period));
    } else {
      app.innerHTML = `<div class="screen home">${head}${periodSeg()}<div class="mt16 skel" style="height:170px;border-radius:24px"></div><div class="mt16">${skeleton(3)}</div></div>${tabbar("home")}`;
      bindPeriod();
    }
    const fresh = await api("GET", "/api/dashboard?period=" + S.period);
    S.dash[fresh.period] = fresh;
    if (!alive(id)) return;
    renderHome(fresh);

    function renderHome(d) {
    const pend = d.pending_total || 0;
    S.pendingCount = pend;
    const c = d.count;
    const decided = c.approved + c.rejected;
    app.innerHTML = `<div class="screen home">${head}
      ${pend ? `<button class="card pad item" style="margin-bottom:14px" data-act="toPending"><div class="cur bg-warning">${ic("clock", 'width="20" height="20"')}</div><div class="mid"><div class="t">${t("pending_review")}</div><div class="m">${t("to_review", { n: pend })}</div></div>${ic("chev", 'class="chev" width="18" height="18" style="color:var(--muted)"')}</button>` : ""}
      ${periodSeg()}
      <div class="hero mt16">
        <div class="label">${t("approved")} · ${esc(d.base)} ${t("in_base")}</div>
        <div class="big num">${fmt(d.base_sum.approved)}<small>${esc(d.base)}</small></div>
        <div class="label" style="font-size:12px">${d.rate_date ? t("rate_cbu") + " · " + esc(d.rate_date) : ""}</div>
        <div class="row">
          <div class="pill"><span>${t("pending")}</span><b class="num">${fmtShort(d.base_sum.pending)}</b></div>
          <div class="pill"><span>${t("rejected")}</span><b class="num">${fmtShort(d.base_sum.rejected)}</b></div>
          <div class="pill"><span>${t("kpi_requests")}</span><b class="num">${d.total}</b></div>
        </div>
      </div>
      <div class="alert-row mt12">
        <button class="card alert" data-go="#/due"><div class="ic bg-primary">${ic("calendar")}</div><div><div class="t">${t("upcoming_7")}</div><div class="v num">${d.upcoming_count} <small class="muted" style="font-size:12px;font-weight:600">· ${fmtShort(d.upcoming_sum)}</small></div></div></button>
        <button class="card alert" data-go="#/due"><div class="ic ${d.overdue_count ? "bg-danger" : "bg-success"}">${ic(d.overdue_count ? "alert" : "check")}</div><div><div class="t">${t("overdue_pending")}</div><div class="v num">${d.overdue_count}</div></div></button>
      </div>
      <div class="kpis mt12">
        ${kpi("hash", "bg-primary", t("kpi_requests"), d.total)}
        ${kpi("percent", "bg-success", t("kpi_approval"), d.approval_rate == null ? "—" : Math.round(d.approval_rate) + "<small>%</small>", decided ? `${c.approved}/${decided}` : "")}
        ${kpi("clock", "bg-warning", t("kpi_avg_time"), hours(d.avg_decide_hours))}
        ${kpi("wallet", "bg-primary", t("kpi_avg_amount"), d.avg_amount == null ? "—" : fmtShort(d.avg_amount) + `<small>${esc(d.base)}</small>`)}
      </div>
      ${d.total ? `
      <div class="section"><div class="card chart-card"><h3>${t("dynamics")} <small>${esc(d.base)}</small></h3>${barChart(d.series)}
        <div class="legend">${["approved", "pending", "rejected"].map((s) => `<span><i style="background:${STATUS_COLOR[s]}"></i>${t(s)}</span>`).join("")}</div></div></div>
      <div class="section"><div class="card chart-card"><h3>${t("by_status")}</h3>${donut(c)}</div></div>
      ${d.by_currency.length ? `<div class="section"><div class="card chart-card"><h3>${t("by_currency")}</h3>${d.by_currency.map(curRow).join("")}</div></div>` : ""}
      ${d.top.length ? `<div class="section"><div class="card chart-card"><h3>${t("top_requesters")} <small>${esc(d.base)}</small></h3>${hbars(d.top.map((x) => ({ label: x.name, amount: x.amount, count: x.count })))}</div></div>` : ""}
      ${d.breakdowns.map((b) => `<div class="section"><div class="card chart-card"><h3>${esc(b.field)} <small>${esc(d.base)}</small></h3>${hbars(b.items.map((x) => ({ label: b.type === "bool" ? t(x.label === "yes" ? "yes" : x.label === "no" ? "no" : x.label) : x.label, amount: x.amount, count: x.count })))}</div></div>`).join("")}
      ${d.missing_rates.length ? `<p class="muted mt12" style="font-size:12px">⚠️ ${esc(t("missing_rates", { m: d.missing_rates.join(", ") }))}</p>` : ""}
      ` : `<div class="empty card mt16"><div class="ill">${ic("inbox")}</div><b>${t("empty_list")}</b></div>`}
      <button class="btn btn-ghost mt16" data-act="export">${ic("download")} ${t("export_excel")}</button>
    </div>${tabbar("home")}`;
    bindPeriod();
    S.acts.toPending = () => { S.list = { scope: "all", status: "pending", q: "" }; location.hash = "#/requests"; };
    S.acts.export = async (btn) => {
      busy(btn, true);
      try { await api("POST", "/api/export", { period: S.period }); toast(t("export_sent")); }
      catch (e) { toast(errText(e), true); }
      busy(btn, false);
    };
    }
  }
  function periodSeg() {
    return `<div class="seg" id="period">${["today", "week", "month", "pmonth", "year", "all"].map((p) => `<button class="${S.period === p ? "on" : ""}" data-p="${p}">${t("p_" + p)}</button>`).join("")}</div>`;
  }
  function bindPeriod() {
    const seg = document.getElementById("period");
    if (seg) seg.onclick = (e) => {
      const b = e.target.closest("[data-p]"); if (!b || b.dataset.p === S.period) return;
      haptic("select"); S.period = b.dataset.p; store.set("period", S.period);
      screenHome(++S.renderId).catch((er) => toast(errText(er), true)); // butun sahifani qayta chizmasdan
    };
    const on = seg && seg.querySelector(".on"); if (on) on.scrollIntoView({ inline: "center", block: "nearest" });
  }
  const kpi = (icon, cls, k, v, sub) => `<div class="card kpi"><div class="k"><span class="ic ${cls}">${ic(icon)}</span>${k}</div><div class="v num">${v}</div>${sub ? `<div class="muted" style="font-size:12px">${sub}</div>` : ""}</div>`;

  function barChart(series) {
    if (!series.length) return "";
    const keys = ["approved", "pending", "rejected"];
    const totals = series.map((s) => keys.reduce((a, k) => a + (s[k] || 0), 0));
    const max = Math.max(...totals, 1);
    const n = series.length;
    const every = Math.ceil(n / 8);
    const lbl = (k) => k.length === 7 ? monthShort(parseD(k + "-01")) : String(parseD(k).getDate());
    return `<div class="bars">${series.map((s, i) => totals[i] ? `<div class="b" title="${esc(s.key)}: ${fmt(totals[i])}">${keys.map((k) => s[k] ? `<span style="height:${(s[k] / max) * 100}%;background:${STATUS_COLOR[k]}"></span>` : "").join("")}</div>` : '<div class="b empty-b"></div>').join("")}</div>
      <div class="xlabels">${series.map((s, i) => `<span>${i % every === 0 || i === n - 1 ? lbl(s.key) : ""}</span>`).join("")}</div>`;
  }
  function donut(c) {
    const keys = ["approved", "pending", "rejected", "cancelled"];
    const total = keys.reduce((a, k) => a + c[k], 0) || 1;
    const R = 52, C = 2 * Math.PI * R;
    let off = 0;
    const segs = keys.filter((k) => c[k]).map((k) => {
      const len = (c[k] / total) * C;
      const gap = keys.filter((x) => c[x]).length > 1 ? 2.5 : 0;
      const s = `<circle cx="66" cy="66" r="${R}" fill="none" stroke="${STATUS_COLOR[k]}" stroke-width="16" stroke-dasharray="${Math.max(len - gap, 0.1)} ${C}" stroke-dashoffset="${-off}" stroke-linecap="butt"/>`;
      off += len; return s;
    }).join("");
    return `<div class="donut-wrap"><svg viewBox="0 0 132 132"><g transform="rotate(-90 66 66)"><circle cx="66" cy="66" r="${R}" fill="none" stroke="var(--surface-3)" stroke-width="16"/>${segs}</g>
      <text x="66" y="63" text-anchor="middle" font-size="24" font-weight="800" fill="var(--text)">${total === 1 && !keys.some((k) => c[k]) ? 0 : total}</text>
      <text x="66" y="81" text-anchor="middle" font-size="11" font-weight="600" fill="var(--muted)">${esc(t("kpi_requests"))}</text></svg>
      <div class="donut-legend">${keys.map((k) => `<div class="li"><i style="background:${STATUS_COLOR[k]}"></i><span>${t(k)}</span><b class="num">${c[k]}</b></div>`).join("")}</div></div>`;
  }
  function curRow(r) {
    const tot = r.approved + r.pending + r.rejected || 1;
    return `<div class="cur-row" style="flex-wrap:wrap"><div class="code">${esc(r.code)}</div>
      <div class="vals">${["approved", "pending", "rejected"].map((k) => `<div>${t(k)}<b class="num c-${k}">${fmtShort(r[k])}</b></div>`).join("")}</div>
      <div class="stack" style="flex-basis:100%">${["approved", "pending", "rejected"].map((k) => `<span style="width:${(r[k] / tot) * 100}%;background:${STATUS_COLOR[k]}"></span>`).join("")}</div></div>`;
  }
  function hbars(items) {
    const max = Math.max(...items.map((x) => x.amount), 1);
    return items.slice(0, 8).map((x) => `<div class="hbar"><div class="top"><span>${esc(x.label)}</span><b class="num">${fmtShort(x.amount)}</b></div>
      <div class="track"><div class="fill" style="width:${Math.max((x.amount / max) * 100, 1.5)}%"></div></div><div class="sub">${t("n_requests", { n: x.count })}</div></div>`).join("");
  }

  async function homeSimple(id, head) {
    app.innerHTML = `<div class="screen">${head}<div class="skel" style="height:170px;border-radius:24px"></div><div class="mt16">${skeleton(3)}</div></div>${tabbar("home")}`;
    const [sum, list] = await Promise.all([api("GET", "/api/summary"), api("GET", "/api/requests?scope=my&status=all")]);
    if (!alive(id)) return;
    app.innerHTML = `<div class="screen">${head}
      <div class="hero">
        <div class="label">${t("approved_this_month")}</div>
        <div class="big num">${fmt(sum.approved_month)}<small>${esc(sum.base)}</small></div>
        <div class="row">
          <div class="pill"><span>${t("pending")}</span><b class="num">${sum.counts.pending}</b></div>
          <div class="pill"><span>${t("approved")}</span><b class="num">${sum.counts.approved}</b></div>
          <div class="pill"><span>${t("rejected")}</span><b class="num">${sum.counts.rejected}</b></div>
        </div>
      </div>
      <button class="btn btn-primary mt16" data-go="#/new">${ic("plus")} ${t("new_request")}</button>
      <div class="section"><div class="section-h"><h2>${t("recent")}</h2>${list.total > 5 ? `<button class="link" data-go="#/requests">${t("see_all")}</button>` : ""}</div>
        ${list.items.length ? `<div class="list">${list.items.slice(0, 5).map((r) => itemHtml(r, false)).join("")}</div>` : `<div class="empty card"><div class="ill">${ic("inbox")}</div><b>${t("empty_list")}</b>${t("empty_hint")}</div>`}
      </div></div>${tabbar("home")}`;
  }

  // ------------------------------------------------------------ REQUESTS
  async function screenRequests(id) {
    if (!S.list) S.list = { scope: can("view_all") ? "all" : "my", status: "all", q: "" };
    const L = S.list;
    if (L.scope === "all" && !can("view_all")) L.scope = "my";
    app.innerHTML = `<div class="screen">
      <div class="topbar"><h1>${t("tab_requests")}</h1></div>
      ${can("view_all") ? `<div class="seg" id="scope"><button class="${L.scope === "all" ? "on" : ""}" data-s="all">${t("all_requests")}</button><button class="${L.scope === "my" ? "on" : ""}" data-s="my">${t("my_requests")}</button></div>` : ""}
      <label class="search">${ic("search")}<input id="q" type="search" placeholder="${esc(t("search"))}" value="${esc(L.q)}" enterkeyhint="search"></label>
      <div class="chips" id="stf"></div>
      <div class="list mt12" id="lst">${skeleton(5)}</div>
      <div id="more"></div>
    </div>${tabbar("requests")}`;
    const scope = document.getElementById("scope");
    if (scope) scope.onclick = (e) => { const b = e.target.closest("[data-s]"); if (!b || b.dataset.s === L.scope) return; haptic("select"); L.scope = b.dataset.s; route(); };
    let tm;
    document.getElementById("q").oninput = (e) => { clearTimeout(tm); tm = setTimeout(() => { L.q = e.target.value; load(true); }, 300); };
    document.getElementById("stf").onclick = (e) => { const b = e.target.closest("[data-st]"); if (!b) return; haptic("select"); L.status = b.dataset.st; load(true); };
    let items = [];
    async function load(reset) {
      const offset = reset ? 0 : items.length;
      const myId = S.renderId;
      if (reset) document.getElementById("lst").innerHTML = skeleton(4);
      const d = await api("GET", `/api/requests?scope=${L.scope}&status=${L.status}&q=${encodeURIComponent(L.q)}&offset=${offset}`);
      if (!alive(id) || myId !== S.renderId) return;
      items = reset ? d.items : items.concat(d.items);
      if (L.scope === "all" && L.status === "pending" && !L.q) S.pendingCount = d.total;
      document.getElementById("stf").innerHTML = ["all", "pending", "approved", "rejected", "cancelled"].map((s) => `<button class="chip ${L.status === s ? "on" : ""}" data-st="${s}">${t(s)} <span class="cnt">${d.counts[s]}</span></button>`).join("");
      document.getElementById("lst").innerHTML = items.length ? items.map((r) => itemHtml(r, L.scope === "all")).join("")
        : `<div class="empty card"><div class="ill">${ic(L.q ? "search" : "inbox")}</div><b>${t("empty_list")}</b>${L.scope === "my" && !L.q ? t("empty_hint") : ""}</div>`;
      document.getElementById("more").innerHTML = items.length < d.total ? `<button class="btn btn-ghost mt12" data-act="more">${t("load_more")}</button>` : "";
    }
    S.acts.more = async (b) => { busy(b, true); try { await load(false); } catch (e) { toast(errText(e), true); busy(b, false); } };
    await load(true);
  }

  // ------------------------------------------------------------ DETAIL
  async function screenDetail(id, rid) {
    app.innerHTML = `<div class="screen no-tabs"><div class="skel" style="height:190px"></div><div class="skel mt12" style="height:220px"></div></div>`;
    const d = await api("GET", "/api/requests/" + rid);
    if (!alive(id)) return;
    const r = d.request;
    const fields = d.fields;
    const extraRows = fields.filter((f) => f.type !== "file" && r.extra[f.id] !== undefined).map((f) => row(f.name, fieldValue(f, r.extra[f.id]))).join("");
    const files = fields.filter((f) => f.type === "file" && r.extra[f.id]);
    const due = dueLabel(r.needed_date, r.status);
    const overdue = r.status === "pending" && daysFromToday(r.needed_date) < 0;
    const actions = [];
    if (r.can.decide) actions.push(`<button class="btn btn-danger" data-act="reject">${ic("x")} ${t("reject")}</button><button class="btn btn-success" data-act="approve">${ic("check")} ${t("approve")}</button>`);
    const sec = [];
    if (r.can.edit) sec.push(`<button class="btn btn-ghost btn-sm" data-go="#/edit/${r.id}">${ic("edit")} ${t("edit")}</button>`);
    if (r.can.cancel) sec.push(`<button class="btn btn-ghost btn-sm" data-act="cancel" style="color:var(--danger)">${ic("ban")} ${t("cancel_request")}</button>`);
    if (r.can.reopen) sec.push(`<button class="btn btn-ghost btn-sm" data-act="reopen">${ic("undo")} ${t("reopen")}</button>`);

    app.innerHTML = `<div class="screen ${actions.length ? "no-tabs" : ""}">
      <div class="card detail-head">
        <div class="id">#${r.id} · ${badge(r.status)}</div>
        <div class="amt num">${fmt(r.amount)}<small>${esc(r.currency)}</small></div>
        ${r.base_amount != null && r.currency !== S.me.base ? `<div class="eq num">≈ ${fmt(r.base_amount)} ${esc(S.me.base)}</div>` : ""}
        <div class="ttl">${esc(r.title)}</div>
      </div>
      ${sec.length ? `<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px">${sec.join("")}</div>` : ""}
      ${r.status === "rejected" && r.reject_reason ? `<div class="note bg-danger"><b>${t("reason")}:</b> ${esc(r.reject_reason)}</div>` : ""}
      <div class="card rows mt12">
        ${row(t("needed_date"), `${fmtDate(r.needed_date)}${due ? `<div style="font-size:12.5px;font-weight:600" class="${overdue ? "due-warn" : "muted"}">${esc(due)}</div>` : ""}`)}
        ${row(t("author"), esc(r.author_name || "—") + (r.author_username ? `<div class="muted" style="font-size:12.5px">@${esc(r.author_username)}</div>` : ""))}
        ${row(t("created"), fmtDT(r.created_at))}
        ${r.decided_at && r.status !== "cancelled" ? row(t("decided_by"), esc(r.decider_name || "—") + `<div class="muted" style="font-size:12.5px">${fmtDT(r.decided_at)}</div>`) : ""}
        ${r.comment ? row(t("comment"), esc(r.comment)) : ""}
        ${extraRows}
      </div>
      ${files.length ? `<div class="section"><div class="section-h"><h2>${t("files")}</h2></div><div class="card">${files.map((f) => `
        <div class="file">${r.extra[f.id].kind === "photo" ? `<img data-img="/api/requests/${r.id}/file/${f.id}" alt="">` : `<div class="fi bg-primary">${ic("file")}</div>`}
        <div class="n">${esc(r.extra[f.id].name || f.name)}<small>${esc(f.name)}</small></div>
        <button class="btn btn-ghost btn-sm" data-act="sendfile" data-f="${f.id}">${ic("send")}</button></div>`).join("")}</div></div>` : ""}
      <div class="section"><div class="section-h"><h2>${t("history")}</h2></div><div class="card timeline">
        ${d.history.map((h) => { const [icn, cls] = HIST[h.action] || ["clock", "bg-primary"]; return `<div class="tl"><div class="dot ${cls}">${ic(icn)}</div><div style="min-width:0"><div class="a">${t("h_" + h.action)}</div><div class="b">${esc(h.by || "—")} · ${fmtDT(h.at)}</div>${h.details ? `<div class="d">${esc(h.details)}</div>` : ""}</div></div>`; }).join("")}
      </div></div>
    </div>
    ${actions.length ? `<div class="actions"><div class="in">${actions.join("")}</div></div>` : ""}`;

    document.querySelectorAll("[data-img]").forEach(async (img) => {
      try {
        const res = await fetch(img.dataset.img, { headers: { Authorization: "tma " + tg.initData } });
        if (res.ok) img.src = URL.createObjectURL(await res.blob());
      } catch (_) { /* ignore */ }
    });
    const done = (msg) => { toast(msg); route(); };
    S.acts.approve = async (b) => {
      if (!(await confirmSheet(t("confirm_approve"), t("approve")))) return;
      busy(b, true);
      try { await api("POST", `/api/requests/${r.id}/approve`); done(t("st_approved")); } catch (e) { busy(b, false); toast(errText(e), true); if (e.code === "already_decided") route(); }
    };
    S.acts.reject = () => {
      sheet(`<h3>${t("reject_reason")}</h3><textarea class="input" id="rr" placeholder="${esc(t("reject_reason_ph"))}" maxlength="500"></textarea>
        <div class="btn-row mt16"><button class="btn btn-ghost" id="rN">${t("cancel")}</button><button class="btn btn-danger" id="rY">${ic("x")} ${t("reject")}</button></div>`, (sh) => {
        sh.querySelector("#rN").onclick = closeSheet;
        sh.querySelector("#rY").onclick = async (ev) => {
          const b = ev.currentTarget; busy(b, true);
          try { await api("POST", `/api/requests/${r.id}/reject`, { reason: sh.querySelector("#rr").value }); closeSheet(); done(t("st_rejected")); }
          catch (e) { busy(b, false); toast(errText(e), true); }
        };
        setTimeout(() => sh.querySelector("#rr").focus(), 250);
      });
    };
    S.acts.cancel = async () => {
      if (!(await confirmSheet(t("confirm_cancel"), t("cancel_request"), true))) return;
      try { await api("POST", `/api/requests/${r.id}/cancel`); done(t("st_cancelled")); } catch (e) { toast(errText(e), true); }
    };
    S.acts.reopen = async () => {
      try { await api("POST", `/api/requests/${r.id}/reopen`); done(t("h_reopened")); } catch (e) { toast(errText(e), true); }
    };
    S.acts.sendfile = async (b) => {
      busy(b, true);
      try { await api("POST", `/api/requests/${r.id}/file/${b.dataset.f}/send`); toast(t("sent_to_chat")); } catch (e) { toast(errText(e), true); }
      busy(b, false);
    };
  }
  const row = (k, v) => `<div class="rowi"><div class="k">${esc(k)}</div><div class="v">${v}</div></div>`;
  function fieldValue(f, v) {
    if (v == null || v === "") return "—";
    if (f.type === "number") return `<span class="num">${fmt(v)}</span>`;
    if (f.type === "date") return fmtDate(v);
    if (f.type === "bool") return v ? `<span class="c-approved">${t("yes")}</span>` : `<span class="c-rejected">${t("no")}</span>`;
    return esc(v);
  }

  // ------------------------------------------------------------ FORM
  async function screenForm(id, rid) {
    const editing = !!rid;
    let r = null;
    let fields = S.me.fields;
    if (editing) {
      app.innerHTML = `<div class="screen no-tabs"><div class="skel" style="height:420px"></div></div>`;
      const d = await api("GET", "/api/requests/" + rid);
      if (!alive(id)) return;
      r = d.request;
      if (!r.can.edit) { toast(t("e_not_editable"), true); history.back(); return; }
      fields = d.fields.filter((f) => f.active || r.extra[f.id] !== undefined);
    } else {
      const me = await api("GET", "/api/me"); // maydonlar/valyutalar o'zgargan bo'lishi mumkin
      if (!alive(id)) return;
      S.me = me; fields = me.fields;
    }
    const F = {
      title: r ? r.title : "",
      amount: r ? r.amount : "",
      currency: r ? r.currency : (store.get("cur") && S.me.currencies.includes(store.get("cur")) ? store.get("cur") : S.me.currencies[0]),
      needed_date: r ? r.needed_date : "",
      comment: r ? r.comment : "",
      extra: r ? JSON.parse(JSON.stringify(r.extra)) : {},
    };
    const curs = S.me.currencies.includes(F.currency) ? S.me.currencies : [F.currency, ...S.me.currencies];
    const today = todayIso();
    const quick = [["d_today", 0], ["d_tomorrow", 1], ["d_3", 3], ["d_7", 7]];

    app.innerHTML = `<div class="screen no-tabs">
      <div class="topbar"><h1>${editing ? t("edit_request") + ` <span class="muted">#${r.id}</span>` : t("new_request")}</h1></div>
      <div class="form" id="form">
        <div class="field"><label class="l" for="f_amount">${t("amount")}</label>
          <div class="amount-wrap"><input class="input num" id="f_amount" inputmode="decimal" autocomplete="off" placeholder="0" value="${F.amount !== "" ? esc(fmt(F.amount)) : ""}"><span class="cc" id="ccv">${esc(F.currency)}</span></div>
          <div class="opts" id="curs">${curs.map((c) => `<button type="button" class="opt ${c === F.currency ? "on" : ""}" data-c="${esc(c)}">${esc(c)}</button>`).join("")}</div>
          <div class="err-msg" id="e_amount" hidden></div></div>
        <div class="field"><label class="l" for="f_title">${t("title")}</label>
          <input class="input" id="f_title" maxlength="500" placeholder="${esc(t("title_ph"))}" value="${esc(F.title)}"><div class="err-msg" id="e_title" hidden></div></div>
        <div class="field"><label class="l" for="f_date">${t("needed_date")}</label>
          <div class="opts" id="qd" style="margin:0 0 8px">${quick.map(([k, n]) => `<button type="button" class="opt ${F.needed_date === addDays(today, n) ? "on" : ""}" data-d="${addDays(today, n)}">${t(k)}</button>`).join("")}</div>
          <input class="input" type="date" id="f_date" ${editing ? "" : `min="${today}"`} value="${esc(F.needed_date)}"><div class="err-msg" id="e_date" hidden></div></div>
        <div class="field"><label class="l" for="f_comment">${t("comment")} <span>${t("optional")}</span></label>
          <textarea class="input" id="f_comment" maxlength="1000" placeholder="${esc(t("comment_ph"))}">${esc(F.comment)}</textarea></div>
        ${fields.map((f) => `<div class="field" data-field="${f.id}">${fieldInput(f, F.extra[f.id])}</div>`).join("")}
      </div>
    </div>
    <div class="actions"><div class="in"><button class="btn btn-primary" id="submit">${ic(editing ? "check" : "send")} ${editing ? t("save") : t("submit")}</button></div></div>`;

    const $ = (s) => document.getElementById(s);
    const showErr = (k, msg) => { const el = $("e_" + k); if (el) { el.textContent = msg || ""; el.hidden = !msg; } const inp = $("f_" + k); if (inp) inp.classList.toggle("err", !!msg); };
    $("f_amount").addEventListener("input", (e) => {
      const raw = e.target.value.replace(/[^\d.,]/g, "").replace(",", ".");
      const [i, dec] = raw.split(".");
      const grouped = (i || "").replace(/^0+(?=\d)/, "").replace(/\B(?=(\d{3})+(?!\d))/g, S.lang === "en" ? "," : " ");
      e.target.value = dec !== undefined ? grouped + "." + dec.slice(0, 2) : grouped;
      showErr("amount", "");
    });
    $("curs").onclick = (e) => { const b = e.target.closest("[data-c]"); if (!b) return; haptic("select"); F.currency = b.dataset.c; $("ccv").textContent = F.currency; $("curs").querySelectorAll(".opt").forEach((x) => x.classList.toggle("on", x === b)); };
    $("qd").onclick = (e) => { const b = e.target.closest("[data-d]"); if (!b) return; haptic("select"); $("f_date").value = b.dataset.d; markQuick(); showErr("date", ""); };
    $("f_date").onchange = () => { markQuick(); showErr("date", ""); };
    $("f_title").oninput = () => showErr("title", "");
    function markQuick() { $("qd").querySelectorAll(".opt").forEach((x) => x.classList.toggle("on", x.dataset.d === $("f_date").value)); }

    // custom fields
    $("form").addEventListener("click", (e) => {
      const o = e.target.closest("[data-fo]");
      if (o) {
        const fid = o.closest("[data-field]").dataset.field;
        const f = fields.find((x) => String(x.id) === fid);
        haptic("select");
        let v = f.type === "bool" ? o.dataset.fo === "1" : o.dataset.fo;
        if (F.extra[fid] === v && !f.required) v = undefined; // ikkinchi bosish — tozalash
        if (v === undefined) delete F.extra[fid]; else F.extra[fid] = v;
        o.parentElement.querySelectorAll("[data-fo]").forEach((x) => x.classList.toggle("on", F.extra[fid] !== undefined && String(x.dataset.fo) === String(f.type === "bool" ? (F.extra[fid] ? "1" : "0") : F.extra[fid])));
        fieldErr(fid, "");
      }
      const rm = e.target.closest("[data-rmfile]");
      if (rm) { const fid = rm.dataset.rmfile; delete F.extra[fid]; F.extra["__rm" + fid] = true; rerenderField(fid); }
    });
    $("form").addEventListener("input", (e) => {
      const w = e.target.closest("[data-field]"); if (!w || !e.target.dataset.fi) return;
      const fid = w.dataset.field;
      if (e.target.value === "") delete F.extra[fid]; else F.extra[fid] = e.target.value;
      fieldErr(fid, "");
    });
    $("form").addEventListener("change", async (e) => {
      if (e.target.type !== "file") return;
      const fid = e.target.closest("[data-field]").dataset.field;
      const file = e.target.files[0]; if (!file) return;
      const w = document.querySelector(`[data-field="${fid}"] .upload`);
      if (w) w.innerHTML = `<span class="spinner" style="margin:0"></span> ${t("uploading")}`;
      try {
        const fd = new FormData(); fd.append("file", file, file.name);
        F.extra[fid] = await api("POST", "/api/upload", fd, true);
        delete F.extra["__rm" + fid];
      } catch (er) { toast(errText(er), true); }
      rerenderField(fid);
    });
    function rerenderField(fid) {
      const f = fields.find((x) => String(x.id) === String(fid));
      document.querySelector(`[data-field="${fid}"]`).innerHTML = fieldInput(f, F.extra[fid]);
    }
    function fieldErr(fid, msg) { const el = document.querySelector(`[data-field="${fid}"] .err-msg`); if (el) { el.textContent = msg; el.hidden = !msg; } }

    $("submit").onclick = async (ev) => {
      const btn = ev.currentTarget;
      F.title = $("f_title").value.trim();
      F.amount = parseFloat(($("f_amount").value || "").replace(/[\s,]/g, (m) => (m === "," && S.lang !== "en" ? "." : "")));
      F.needed_date = $("f_date").value;
      F.comment = $("f_comment").value.trim();
      let bad = false;
      if (F.title.length < 3) { showErr("title", t("e_bad_title")); bad = true; }
      if (!(F.amount > 0)) { showErr("amount", t("e_bad_amount")); bad = true; }
      if (!F.needed_date) { showErr("date", t("e_bad_date")); bad = true; }
      else if (!editing && F.needed_date < today) { showErr("date", t("e_past_date")); bad = true; }
      for (const f of fields) {
        if (f.required && f.active && (F.extra[f.id] === undefined || F.extra[f.id] === "")) { fieldErr(f.id, t("e_required", { m: f.name })); bad = true; }
      }
      if (bad) { haptic("error"); const first = document.querySelector(".err-msg:not([hidden])"); if (first) first.scrollIntoView({ behavior: "smooth", block: "center" }); return; }
      const extra = {};
      for (const f of fields) {
        const k = String(f.id);
        if (F.extra[k] !== undefined) extra[k] = f.type === "number" ? parseFloat(String(F.extra[k]).replace(",", ".")) : F.extra[k];
        else if (editing) extra[k] = null;
      }
      const payload = { title: F.title, amount: F.amount, currency: F.currency, needed_date: F.needed_date, comment: F.comment, extra };
      busy(btn, true);
      try {
        if (editing) {
          await api("PATCH", "/api/requests/" + r.id, payload);
          toast(t("saved_ok"));
          history.back();
        } else {
          const res = await api("POST", "/api/requests", payload);
          store.set("cur", F.currency);
          toast(t("created_ok"));
          location.replace("#/r/" + res.request.id);
        }
      } catch (e) {
        busy(btn, false);
        const map = { bad_title: "title", bad_amount: "amount", bad_date: "date", past_date: "date" };
        if (map[e.code]) showErr(map[e.code], errText(e)); else toast(errText(e), true);
      }
    };
    if (!editing) setTimeout(() => $("f_amount").focus(), 300);
  }

  function fieldInput(f, v) {
    const lab = `<label class="l">${esc(f.name)} <span>${f.required ? "" : t("optional")}</span></label>`;
    const err = '<div class="err-msg" hidden></div>';
    switch (f.type) {
      case "choice":
        return lab + `<div class="opts" style="margin:0">${f.options.map((o) => `<button type="button" class="opt ${v === o ? "on" : ""}" data-fo="${esc(o)}">${esc(o)}</button>`).join("")}</div>` + err;
      case "bool":
        return lab + `<div class="opts" style="margin:0"><button type="button" class="opt ${v === true ? "on" : ""}" data-fo="1">${t("yes")}</button><button type="button" class="opt ${v === false ? "on" : ""}" data-fo="0">${t("no")}</button></div>` + err;
      case "number":
        return lab + `<input class="input num" data-fi="1" inputmode="decimal" value="${v != null ? esc(v) : ""}">` + err;
      case "date":
        return lab + `<input class="input" data-fi="1" type="date" value="${v ? esc(v) : ""}">` + err;
      case "file":
        if (v) return lab + `<div class="attached"><div class="fi bg-primary" style="width:36px;height:36px;border-radius:10px;display:grid;place-items:center">${ic(v.kind === "photo" ? "clip" : "file", 'width="18" height="18"')}</div><div class="n">${esc(v.name || "file")}</div><button type="button" class="btn btn-ghost btn-sm" data-rmfile="${f.id}">${ic("trash", 'width="16" height="16"')}</button></div>` + err;
        return lab + `<label class="upload">${ic("clip")} ${t("attach")}<input type="file" hidden accept="image/*,application/pdf,.doc,.docx,.xls,.xlsx"></label>` + err;
      default:
        return lab + `<input class="input" data-fi="1" maxlength="1000" value="${v != null ? esc(v) : ""}">` + err;
    }
  }

  // ------------------------------------------------------------ DUE
  async function screenDue(id) {
    app.innerHTML = `<div class="screen"><div class="topbar"><h1>${t("tab_due")}</h1></div>${skeleton(5)}</div>${tabbar("due")}`;
    const d = await api("GET", "/api/due");
    if (!alive(id)) return;
    const showAuthor = can("view_all");
    const groups = {};
    d.upcoming.forEach((r) => (groups[r.needed_date] = groups[r.needed_date] || []).push(r));
    const totals = (arr) => { const m = {}; arr.forEach((r) => (m[r.currency] = (m[r.currency] || 0) + r.amount)); return Object.entries(m).map(([c, v]) => `${fmtShort(v)} ${esc(c)}`).join(" · "); };
    app.innerHTML = `<div class="screen"><div class="topbar"><h1>${t("tab_due")}</h1></div>
      ${d.overdue.length ? `<div class="day-h"><b class="due-warn">⚠️ ${t("overdue_pending")}</b><span>${d.overdue.length}</span></div><div class="list">${d.overdue.map((r) => itemHtml(r, showAuthor)).join("")}</div>` : ""}
      ${Object.keys(groups).length ? Object.entries(groups).map(([day, arr]) => `<div class="day-h"><b>${fmtDate(day, { weekday: "short", day: "numeric", month: "long" })} <span class="muted" style="font-weight:600">· ${esc(dueLabel(day))}</span></b><span class="num">${totals(arr)}</span></div><div class="list">${arr.map((r) => itemHtml(r, showAuthor)).join("")}</div>`).join("")
        : (d.overdue.length ? "" : `<div class="empty card"><div class="ill">${ic("calendar")}</div><b>${t("nothing_due")}</b></div>`)}
    </div>${tabbar("due")}`;
  }

  // ------------------------------------------------------------ MORE / SETTINGS
  async function screenMore() {
    const u = S.me.user;
    app.innerHTML = `<div class="screen"><div class="topbar"><h1>${t("settings")}</h1></div>
      <div class="card pad" style="display:flex;gap:14px;align-items:center"><div class="avatar" style="width:52px;height:52px;font-size:18px">${initials(u.full_name)}</div>
        <div style="min-width:0"><b style="font-size:17px">${esc(u.full_name)}</b><div class="muted" style="font-size:13px">${u.username ? "@" + esc(u.username) + " · " : ""}${t("r_" + u.role)}</div></div></div>
      <div class="section"><div class="section-h"><h2>${t("language")}</h2></div>
        <div class="seg" id="lang">${[["uz", "O'zbekcha"], ["ru", "Русский"], ["en", "English"]].map(([c, n]) => `<button class="${S.lang === c ? "on" : ""}" data-l="${c}">${n}</button>`).join("")}</div></div>
      <div class="section"><div class="section-h"><h2>${t("theme")}</h2></div>
        <div class="seg" id="theme">${["auto", "light", "dark"].map((m) => `<button class="${S.themePref === m ? "on" : ""}" data-m="${m}">${t("th_" + m)}</button>`).join("")}</div></div>
      ${can("admin") ? `<div class="section"><div class="section-h"><h2>${t("admin")}</h2></div><div class="card menu">
        ${menuItem("#/admin/users", "users", "bg-primary", t("users"), t("change_role"))}
        ${menuItem("#/admin/fields", "sliders", "bg-success", t("fields"), t("fields_hint"))}
        ${menuItem("#/admin/currencies", "coins", "bg-warning", t("currencies"), S.me.currencies.join(", "))}
        ${menuItem("#/admin/audit", "clock", "bg-danger", t("audit"), t("audit_sub"))}
      </div></div>` : ""}
      <p class="muted" style="text-align:center;font-size:12px;margin-top:28px">${t("app_name")} · v1.0</p>
    </div>${tabbar("more")}`;
    document.getElementById("lang").onclick = (e) => { const b = e.target.closest("[data-l]"); if (!b) return; haptic("select"); S.lang = b.dataset.l; store.set("lang", S.lang); document.documentElement.lang = S.lang; route(); };
    document.getElementById("theme").onclick = (e) => { const b = e.target.closest("[data-m]"); if (!b) return; haptic("select"); S.themePref = b.dataset.m; store.set("theme", S.themePref); applyTheme(); route(); };
  }
  const menuItem = (href, icon, cls, title, sub) => `<button class="mi" data-go="${href}"><span class="ic ${cls}" style="display:grid;place-items:center">${ic(icon)}</span><span class="tx"><b>${esc(title)}</b><small>${esc(sub || "")}</small></span>${ic("chev", 'class="chev"')}</button>`;

  // ------------------------------------------------------------ ADMIN: users
  async function screenUsers(id) {
    app.innerHTML = `<div class="screen no-tabs"><div class="topbar"><h1>${t("users")}</h1></div>${skeleton(6)}</div>`;
    const d = await api("GET", "/api/admin/users");
    if (!alive(id)) return;
    const roleCls = { superadmin: "bg-danger", admin: "bg-primary", approver: "bg-success", viewer: "bg-warning", user: "s-cancelled", pending: "bg-danger", blocked: "s-cancelled" };
    app.innerHTML = `<div class="screen no-tabs"><div class="topbar"><h1>${t("users")}</h1><span class="muted">${d.items.length}</span></div>
      <div class="card menu">${d.items.map((u) => `<button class="mi" data-act="role" data-u="${u.id}"><span class="avatar sm">${initials(u.full_name)}</span>
        <span class="tx"><b>${esc(u.full_name || u.id)}</b><small>${u.username ? "@" + esc(u.username) + " · " : ""}${t("n_requests", { n: u.req_count })}</small></span>
        <span class="badge ${roleCls[u.role]}">${t("r_" + u.role)}</span></button>`).join("")}</div></div>`;
    S.acts.role = (b) => {
      const u = d.items.find((x) => String(x.id) === b.dataset.u);
      // Server bilan bir xil qoida (bot/utils.py: role_change_error)
      const lock = u.role === "superadmin" ? "protected" : u.id === S.me.user.id ? "self_role"
        : (u.role === "admin" && !can("manage_admins")) ? "super_only" : null;
      if (lock) { toast(t("e_" + lock), true); return; }
      sheet(`<h3>${esc(u.full_name)}</h3><p>${t("change_role")}</p><div class="card menu">${(S.me.assignable_roles || []).map((r) => `<button class="mi" data-r="${r}"><span class="tx"><b>${t("r_" + r)}</b></span>${u.role === r ? ic("check", 'class="chev" style="color:var(--primary)"') : ""}</button>`).join("")}</div>`, (sh) => {
        sh.onclick = async (e) => {
          const rb = e.target.closest("[data-r]"); if (!rb) return;
          try { await api("POST", `/api/admin/users/${u.id}/role`, { role: rb.dataset.r }); closeSheet(); toast(t("saved_ok")); route(); }
          catch (er) { toast(errText(er), true); }
        };
      });
    };
  }

  // ------------------------------------------------------------ ADMIN: fields
  async function screenFields(id) {
    app.innerHTML = `<div class="screen no-tabs"><div class="topbar"><h1>${t("fields")}</h1></div>${skeleton(4)}</div>`;
    const d = await api("GET", "/api/admin/fields");
    if (!alive(id)) return;
    const typeIcon = { text: "edit", number: "hash", date: "calendar", choice: "list", bool: "check", file: "clip" };
    app.innerHTML = `<div class="screen no-tabs"><div class="topbar"><div><h1>${t("fields")}</h1><div class="sub">${t("fields_hint")}</div></div></div>
      ${d.items.length ? `<div class="card menu">${d.items.map((f) => `<div class="mi" style="cursor:pointer" data-act="edit" data-f="${f.id}">
        <span class="ic ${f.active ? "bg-primary" : "s-cancelled"}" style="display:grid;place-items:center">${ic(typeIcon[f.type])}</span>
        <span class="tx"><b>${esc(f.name)}${f.required ? ' <span class="c-rejected">*</span>' : ""}</b><small>${t("ft_" + f.type)}${f.type === "choice" ? " · " + esc(f.options.join(", ")) : ""}</small></span>
        <label class="toggle" data-stop="1"><input type="checkbox" data-tg="${f.id}" ${f.active ? "checked" : ""}><span></span></label></div>`).join("")}</div>`
        : `<div class="empty card"><div class="ill">${ic("sliders")}</div><b>${t("no_fields")}</b></div>`}
    </div><div class="actions"><div class="in"><button class="btn btn-primary" data-act="add">${ic("plus")} ${t("add_field")}</button></div></div>`;
    app.querySelectorAll("[data-tg]").forEach((cb) => {
      cb.onclick = (e) => e.stopPropagation();
      cb.onchange = async () => {
        haptic("select");
        try { await api("PATCH", `/api/admin/fields/${cb.dataset.tg}`, { active: cb.checked }); route(); } catch (er) { toast(errText(er), true); cb.checked = !cb.checked; }
      };
    });
    app.querySelectorAll("[data-stop]").forEach((x) => (x.onclick = (e) => e.stopPropagation()));
    S.acts.add = () => fieldSheet(null);
    S.acts.edit = (el, ev) => { if (ev.target.closest("[data-stop]")) return; fieldSheet(d.items.find((f) => String(f.id) === el.dataset.f)); };
  }
  function fieldSheet(f) {
    const isNew = !f;
    let type = f ? f.type : "text";
    const types = ["text", "number", "date", "choice", "bool", "file"];
    sheet(`<h3>${isNew ? t("add_field") : esc(f.name)}</h3>
      <div class="form">
        <div class="field"><label class="l">${t("field_name")}</label><input class="input" id="fn" maxlength="60" value="${f ? esc(f.name) : ""}"></div>
        ${isNew ? `<div class="field"><label class="l">${t("field_type")}</label><div class="opts" id="ft" style="margin:0">${types.map((x) => `<button type="button" class="opt ${x === type ? "on" : ""}" data-t="${x}">${t("ft_" + x)}</button>`).join("")}</div></div>` : ""}
        <div class="field" id="fow" ${type === "choice" ? "" : "hidden"}><label class="l">${t("options")}</label><textarea class="input" id="fo" placeholder="${esc(t("options_ph"))}">${f && f.options ? esc(f.options.join("\n")) : ""}</textarea></div>
        <div class="card mi" style="border:1px solid var(--border)"><span class="tx"><b>${t("required")}</b></span><label class="toggle"><input type="checkbox" id="fr" ${f && f.required ? "checked" : ""}><span></span></label></div>
      </div>
      <button class="btn btn-primary mt16" id="fs">${ic("check")} ${t("save")}</button>
      ${isNew ? "" : `<div class="btn-row mt12"><button class="btn btn-ghost" id="fu">${ic("up")} ${t("move_up")}</button><button class="btn btn-danger" id="fd">${ic("trash")} ${t("delete")}</button></div>`}`, (sh) => {
      const ft = sh.querySelector("#ft");
      if (ft) ft.onclick = (e) => { const b = e.target.closest("[data-t]"); if (!b) return; type = b.dataset.t; ft.querySelectorAll(".opt").forEach((x) => x.classList.toggle("on", x === b)); sh.querySelector("#fow").hidden = type !== "choice"; };
      sh.querySelector("#fs").onclick = async (ev) => {
        const body = { name: sh.querySelector("#fn").value.trim(), required: sh.querySelector("#fr").checked };
        if (type === "choice") body.options = sh.querySelector("#fo").value;
        if (isNew) body.type = type;
        busy(ev.currentTarget, true);
        try { await api(isNew ? "POST" : "PATCH", isNew ? "/api/admin/fields" : `/api/admin/fields/${f.id}`, body); closeSheet(); toast(t("saved_ok")); route(); }
        catch (er) { busy(ev.currentTarget, false); toast(errText(er), true); }
      };
      if (!isNew) {
        sh.querySelector("#fu").onclick = async () => { try { await api("PATCH", `/api/admin/fields/${f.id}`, { move: "up" }); closeSheet(); route(); } catch (er) { toast(errText(er), true); } };
        sh.querySelector("#fd").onclick = async () => {
          if (!(await confirmSheet(t("confirm_delete_field"), t("delete"), true))) return;
          try { await api("DELETE", `/api/admin/fields/${f.id}`); toast(t("saved_ok")); route(); } catch (er) { toast(errText(er), true); }
        };
      }
    });
  }

  // ------------------------------------------------------------ ADMIN: audit log
  async function screenAudit(id) {
    const isSuper = can("manage_admins");
    S.audit = S.audit || { entity: "", deleted: "N", q: "" };
    const A = S.audit;
    if (!isSuper) A.deleted = "N";
    const ENT = [["", "ent_all"], ["request", "ent_request"], ["user", "ent_user"], ["field", "ent_field"], ["currency", "ent_currency"]];
    const ENT_ICON = { request: "file", user: "user", field: "sliders", currency: "coins" };
    const ENT_CLS = { request: "bg-primary", user: "bg-warning", field: "bg-success", currency: "bg-warning" };
    app.innerHTML = `<div class="screen no-tabs">
      <div class="topbar"><div><h1>${t("audit")}</h1><div class="sub" id="ahint"></div></div></div>
      ${isSuper ? `<div class="seg" id="adel">${[["N", "a_active"], ["Y", "a_deleted"], ["all", "a_all"]].map(([v, k]) => `<button class="${A.deleted === v ? "on" : ""}" data-v="${v}">${t(k)}</button>`).join("")}</div>` : ""}
      <label class="search">${ic("search")}<input id="aq" type="search" placeholder="${esc(t("audit_search"))}" value="${esc(A.q)}" enterkeyhint="search"></label>
      <div class="chips" id="aent">${ENT.map(([v, k]) => `<button class="chip ${A.entity === v ? "on" : ""}" data-e="${v}">${t(k)}</button>`).join("")}</div>
      <div class="list mt12" id="alst">${skeleton(5)}</div><div id="amore"></div>
    </div>`;
    let items = [];
    const fieldName = (f) => ({ status: t("f_status"), reject_reason: t("reason"), role: t("role") }[f] || f);
    const val = (v, cls) => v == null || v === "" ? `<span class="muted">—</span>` : `<span class="${cls}">${esc(v)}</span>`;
    function row(r) {
      const target = r.entity === "request" ? `<button class="link" data-go="#/r/${esc(r.entity_id)}">${esc(r.entity_label || "#" + r.entity_id)}</button>` : `<b>${esc(r.entity_label || r.entity_id)}</b>`;
      const change = r.field || r.old_value != null || r.new_value != null
        ? `<div class="chg">${r.field ? `<span class="muted">${esc(fieldName(r.field))}:</span> ` : ""}${r.old_value != null ? val(r.old_value, "old") + ` <span class="muted">→</span> ` : ""}${val(r.new_value, "new")}</div>` : "";
      const del = r.deleted === "Y";
      return `<div class="card aud ${del ? "is-del" : ""}">
        <div class="aud-h"><span class="ic ${ENT_CLS[r.entity] || "bg-primary"}">${ic(ENT_ICON[r.entity] || "clock")}</span>
          <div class="aud-t"><b>${esc(r.actor_name || "—")}</b> <span class="muted">· ${t("act_" + r.action) === "act_" + r.action ? esc(r.action) : t("act_" + r.action)}</span><div class="muted aud-d">${fmtDT(r.created_at)} · ${target}</div></div>
          ${del ? `<span class="badge s-rejected">deleted: Y</span>` : ""}</div>
        ${change}
        ${isSuper ? `<div class="aud-a">${del
          ? `<span class="muted">${t("deleted_at")}: ${fmtDT(r.deleted_at)}</span><button class="btn btn-ghost btn-sm" data-act="flag" data-id="${r.id}" data-v="N">${ic("undo")} ${t("restore")}</button>`
          : `${r.restored_at ? `<span class="muted">${t("restored")}: ${fmtDT(r.restored_at)}</span>` : "<span></span>"}<button class="btn btn-ghost btn-sm" data-act="flag" data-id="${r.id}" data-v="Y" style="color:var(--danger)">${ic("trash")} ${t("mark_deleted")}</button>`}</div>` : ""}
      </div>`;
    }
    async function load(reset) {
      const myId = S.renderId;
      if (reset) { items = []; document.getElementById("alst").innerHTML = skeleton(4); }
      const d = await api("GET", `/api/audit?entity=${A.entity}&deleted=${A.deleted}&q=${encodeURIComponent(A.q)}&offset=${items.length}`);
      if (!alive(id) || myId !== S.renderId) return;
      items = items.concat(d.items);
      document.getElementById("ahint").textContent = t("audit_hint", { n: d.retention_days }) + " · " + d.total;
      document.getElementById("alst").innerHTML = items.length ? items.map(row).join("")
        : `<div class="empty card"><div class="ill">${ic("clock")}</div><b>${t("audit_empty")}</b></div>`;
      document.getElementById("amore").innerHTML = items.length < d.total ? `<button class="btn btn-ghost mt12" data-act="amore">${t("load_more")}</button>` : "";
    }
    const seg = document.getElementById("adel");
    if (seg) seg.onclick = (e) => { const b = e.target.closest("[data-v]"); if (!b) return; haptic("select"); A.deleted = b.dataset.v; seg.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b)); load(true).catch((er) => toast(errText(er), true)); };
    document.getElementById("aent").onclick = (e) => { const b = e.target.closest("[data-e]"); if (!b) return; haptic("select"); A.entity = b.dataset.e; document.querySelectorAll("#aent .chip").forEach((x) => x.classList.toggle("on", x === b)); load(true).catch((er) => toast(errText(er), true)); };
    let tm;
    document.getElementById("aq").oninput = (e) => { clearTimeout(tm); tm = setTimeout(() => { A.q = e.target.value; load(true).catch((er) => toast(errText(er), true)); }, 300); };
    S.acts.amore = async (b) => { busy(b, true); try { await load(false); } catch (er) { busy(b, false); toast(errText(er), true); } };
    S.acts.flag = async (b) => {
      const v = b.dataset.v;
      if (v === "Y" && !(await confirmSheet(t("confirm_mark_deleted"), t("mark_deleted"), true))) return;
      busy(b, true);
      try {
        const res = await api("POST", `/api/audit/${b.dataset.id}/deleted`, { value: v });
        const i = items.findIndex((x) => x.id === res.item.id);
        if (i >= 0) items[i] = res.item;
        if (A.deleted !== "all") items = items.filter((x) => x.deleted === A.deleted);
        document.getElementById("alst").innerHTML = items.length ? items.map(row).join("") : `<div class="empty card"><div class="ill">${ic("clock")}</div><b>${t("audit_empty")}</b></div>`;
        toast(v === "N" ? t("restored") : t("saved_ok"));
      } catch (er) { busy(b, false); toast(errText(er), true); }
    };
    await load(true);
  }

  // ------------------------------------------------------------ ADMIN: currencies
  async function screenCurrencies(id) {
    app.innerHTML = `<div class="screen no-tabs"><div class="topbar"><h1>${t("currencies")}</h1></div>${skeleton(4)}</div>`;
    const d = await api("GET", "/api/admin/currencies");
    if (!alive(id)) return;
    app.innerHTML = `<div class="screen no-tabs"><div class="topbar"><h1>${t("currencies")}</h1></div>
      <div class="card menu">${d.items.map((c) => `<div class="mi"><span class="ic ${c.active ? "bg-warning" : "s-cancelled"}" style="display:grid;place-items:center;font-weight:750;font-size:11px;width:42px">${esc(c.code)}</span>
        <span class="tx"><b>${esc(c.code)}</b><small>${c.active ? t("active") : t("inactive")}</small></span>
        <label class="toggle"><input type="checkbox" data-c="${esc(c.code)}" ${c.active ? "checked" : ""}><span></span></label></div>`).join("")}</div>
      <div class="section"><div class="section-h"><h2>${t("add_currency")}</h2></div>
        <div style="display:flex;gap:10px"><input class="input" id="cc" maxlength="3" placeholder="${esc(t("currency_code"))}" style="text-transform:uppercase"><button class="btn btn-primary" style="width:auto" data-act="add">${ic("plus")}</button></div></div>
    </div>`;
    app.querySelectorAll("[data-c]").forEach((cb) => {
      cb.onchange = async () => {
        haptic("select");
        try { await api("POST", `/api/admin/currencies/${cb.dataset.c}/toggle`); S.me = await api("GET", "/api/me"); route(); }
        catch (er) { toast(errText(er), true); cb.checked = !cb.checked; }
      };
    });
    S.acts.add = async (b) => {
      const code = document.getElementById("cc").value.trim().toUpperCase();
      if (!/^[A-Z]{3}$/.test(code)) { toast(t("e_bad_currency"), true); return; }
      busy(b, true);
      try { await api("POST", "/api/admin/currencies", { code }); S.me = await api("GET", "/api/me"); toast(t("saved_ok")); route(); }
      catch (er) { busy(b, false); toast(errText(er), true); }
    };
  }

  // ------------------------------------------------------------ boot
  function centerScreen(icon, cls, title, text) {
    app.innerHTML = `<div class="center-screen"><div><div class="ill ${cls}">${ic(icon)}</div><h2>${esc(title)}</h2><p>${esc(text)}</p></div></div>`;
  }
  async function boot() {
    document.documentElement.lang = S.lang;
    applyTheme();
    if (!tg || !tg.initData) { centerScreen("telegram", "bg-primary", t("open_in_tg"), t("open_in_tg_hint")); return; }
    app.innerHTML = '<div class="spinner" style="margin-top:40vh"></div>';
    try { S.me = await api("GET", "/api/me"); }
    catch (e) { centerScreen("alert", "bg-danger", errText(e), ""); return; }
    const role = S.me.user.role;
    if (role === "pending") { centerScreen("lock", "bg-warning", t("wait_access"), t("wait_access_hint")); return; }
    if (role === "blocked") { centerScreen("ban", "bg-danger", t("blocked_t"), t("blocked_hint")); return; }
    window.addEventListener("hashchange", route);
    route();
  }

  if (tg) {
    tg.ready();
    tg.expand();
    try { tg.disableVerticalSwipes && tg.disableVerticalSwipes(); } catch (_) { /* old */ }
    tg.onEvent && tg.onEvent("themeChanged", () => { if (S.themePref === "auto") applyTheme(); });
    tg.BackButton && tg.BackButton.onClick(() => { if (document.getElementById("sh")) closeSheet(); else history.back(); });
  }
  if (window.matchMedia) matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (S.themePref === "auto") applyTheme(); });
  boot();
})();
