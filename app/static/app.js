/* Proteoscope front-end.
   Vanilla JS, no build step. Everything renders from the API response — there
   is no client-side science here, only drawing. */

(() => {
  "use strict";

  const API = "";
  const TOKEN_KEY = "proteoscope_token";
  const USER_KEY = "proteoscope_user";

  const state = {
    token: localStorage.getItem(TOKEN_KEY) || null,
    user: JSON.parse(localStorage.getItem(USER_KEY) || "null"),
    result: null,
    savedId: null,
    authMode: "login",
    view: { rotX: -0.35, rotY: 0.6, zoom: 1, dragging: false, lastX: 0, lastY: 0 },
  };

  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  const SS_COLOR = { H: "#ff6b8a", E: "#ffc857", T: "#7c9cff", C: "#4a5a70" };
  const SS_NAME = { H: "helix", E: "sheet", T: "turn", C: "coil" };

  const EXAMPLES = {
    lysozyme:
      ">sp|P00698|LYSC_CHICK Lysozyme C\nMKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVVHSLAKWKR",
    helix:
      ">helix-rich test peptide\n" +
      "MEELLKKLEEALKKLEEALKKLEEALKKLEEALKKLEEALKKLEEALKKLEEALKKLEEALKKLEEALKKLEEALKK",
    sheet:
      ">sheet-rich test peptide\n" +
      "MIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVTIVT",
    mixed:
      ">mixed 244-residue test protein\n" +
      "M" + "A".repeat(20) + "K".repeat(15) + "L".repeat(25) + "G".repeat(10) +
      "V".repeat(20) + "S".repeat(15) + "E".repeat(18) + "F".repeat(12) +
      "P".repeat(8) + "T".repeat(14) + "Y".repeat(10) + "W".repeat(6) +
      "C".repeat(9) + "R".repeat(11) + "N".repeat(7) + "D".repeat(13) +
      "Q".repeat(9) + "H".repeat(5) + "I".repeat(16),
  };

  /* ---------------- API ---------------- */

  async function api(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    const res = await fetch(API + path, { ...options, headers });
    let body = null;
    const text = await res.text();
    if (text) {
      try { body = JSON.parse(text); } catch { body = { detail: text }; }
    }
    if (!res.ok) {
      const detail = body && body.detail ? body.detail : `Request failed (${res.status})`;
      const err = new Error(typeof detail === "string" ? detail : "Request failed");
      err.status = res.status;
      err.body = body;
      throw err;
    }
    return body;
  }

  /* ---------------- auth ---------------- */

  function setSession(token, user) {
    state.token = token;
    state.user = user;
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem(USER_KEY, JSON.stringify(user));
    } else {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    }
    renderAuthSlot();
  }

  function renderAuthSlot() {
    const slot = $("auth-slot");
    slot.innerHTML = "";
    if (state.user) {
      const name = el("span", "auth-user", state.user.full_name || state.user.email);
      const out = el("button", "btn ghost small", "Sign out");
      out.type = "button";
      out.addEventListener("click", () => { setSession(null, null); loadSaved(); });
      slot.append(name, out);
    } else {
      const btn = el("button", "btn ghost small", "Sign in");
      btn.type = "button";
      btn.addEventListener("click", () => openAuth("login"));
      slot.append(btn);
    }
  }

  function openAuth(mode) {
    state.authMode = mode;
    $("auth-modal").hidden = false;
    $("auth-title").textContent = mode === "login" ? "Sign in" : "Create an account";
    $("auth-sub").textContent = mode === "login"
      ? "Save predictions and export them later."
      : "Takes a second. You'll be signed in right away.";
    $("auth-name-field").hidden = mode === "login";
    $("auth-submit").textContent = mode === "login" ? "Sign in" : "Create account";
    $("auth-toggle").textContent = mode === "login" ? "Create an account" : "I already have one";
    $("auth-error").hidden = true;
    $("auth-email").focus();
  }

  function closeAuth() { $("auth-modal").hidden = true; }

  async function submitAuth() {
    const email = $("auth-email").value.trim();
    const password = $("auth-password").value;
    const fullName = $("auth-name").value.trim();
    const errBox = $("auth-error");
    errBox.hidden = true;

    if (!email || !password) {
      errBox.textContent = "Email and password are required.";
      errBox.hidden = false;
      return;
    }

    const btn = $("auth-submit");
    btn.disabled = true;
    try {
      const path = state.authMode === "login" ? "/api/auth/login" : "/api/auth/register";
      const payload = state.authMode === "login"
        ? { email, password }
        : { email, password, full_name: fullName };
      const data = await api(path, { method: "POST", body: JSON.stringify(payload) });
      setSession(data.access_token, data.user);
      closeAuth();
      $("auth-password").value = "";
      loadSaved();
    } catch (e) {
      errBox.textContent = e.message;
      errBox.hidden = false;
    } finally {
      btn.disabled = false;
    }
  }

  /* ---------------- analyze ---------------- */

  async function runPrediction() {
    const sequence = $("sequence").value;
    const errBox = $("input-error");
    errBox.hidden = true;

    if (!sequence.trim()) {
      errBox.textContent = "Paste a protein sequence first.";
      errBox.hidden = false;
      return;
    }

    const wantSave = $("save").checked;
    if (wantSave && !state.token) {
      errBox.textContent = "Sign in first if you want to save this prediction.";
      errBox.hidden = false;
      return;
    }

    const btn = $("run");
    btn.disabled = true;
    btn.querySelector(".spinner").hidden = false;
    btn.querySelector(".btn-label").textContent = "Analyzing…";

    try {
      const data = await api("/api/predictions", {
        method: "POST",
        body: JSON.stringify({
          sequence,
          label: $("label").value.trim(),
          save: wantSave,
          include_profile: true,
        }),
      });
      state.result = data.result;
      state.savedId = data.id || null;
      renderResults(data.result);
      if (data.saved) loadSaved();
    } catch (e) {
      errBox.textContent = e.message;
      errBox.hidden = false;
    } finally {
      btn.disabled = false;
      btn.querySelector(".spinner").hidden = true;
      btn.querySelector(".btn-label").textContent = "Analyze structure";
    }
  }

  /* ---------------- rendering ---------------- */

  function renderResults(r) {
    $("results").hidden = false;
    renderStats(r);
    renderSecondary(r);
    renderViewer(r);
    renderContactMap(r);
    renderProfiles(r);
    renderProps(r);
    renderTable(r);
    updateExportHint();
    $("results").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderStats(r) {
    const grid = $("stat-grid");
    grid.innerHTML = "";
    const stats = [
      { k: "Residues", v: r.sequence.length },
      { k: "Mol. weight", v: (r.properties.molecular_weight_da / 1000).toFixed(1), u: "kDa" },
      { k: "Isoelectric pt", v: r.properties.isoelectric_point },
      { k: "GRAVY", v: r.properties.gravy.toFixed(2) },
      { k: "Helix", v: (r.secondary_structure.helix_fraction * 100).toFixed(0), u: "%" },
      { k: "Sheet", v: (r.secondary_structure.sheet_fraction * 100).toFixed(0), u: "%" },
      { k: "Contacts", v: r.contacts.count },
      { k: "Mean conf.", v: r.structure.mean_confidence.toFixed(2) },
    ];
    for (const s of stats) {
      const box = el("div", "stat");
      box.append(el("div", "k", s.k));
      const v = el("div", "v", String(s.v));
      if (s.u) v.append(el("span", "u", " " + s.u));
      box.append(v);
      grid.append(box);
    }
  }

  function renderSecondary(r) {
    const ss = r.secondary_structure;
    const bar = $("ss-bar");
    bar.innerHTML = "";
    const order = [["H", ss.helix_fraction], ["E", ss.sheet_fraction], ["T", ss.turn_fraction], ["C", ss.coil_fraction]];
    for (const [code, frac] of order) {
      if (frac <= 0) continue;
      const span = el("span", `ss-${SS_NAME[code]}`);
      span.style.width = (frac * 100).toFixed(2) + "%";
      span.title = `${SS_NAME[code]}: ${(frac * 100).toFixed(1)}%`;
      bar.append(span);
    }
    $("ss-legend").textContent =
      `H ${(ss.helix_fraction * 100).toFixed(0)}% · E ${(ss.sheet_fraction * 100).toFixed(0)}% · ` +
      `T ${(ss.turn_fraction * 100).toFixed(0)}% · C ${(ss.coil_fraction * 100).toFixed(0)}%`;

    const segs = $("ss-segments");
    segs.innerHTML = "";
    for (const s of ss.segments) {
      if (s.type === "coil") continue;
      segs.append(el("span", `seg ${s.type}`, `${s.type[0].toUpperCase()}${s.start}–${s.end}`));
    }
  }

  /* ---- 3D viewer ---- */

  function project(p, w, h, view) {
    const cosY = Math.cos(view.rotY), sinY = Math.sin(view.rotY);
    const cosX = Math.cos(view.rotX), sinX = Math.sin(view.rotX);
    let x = p.x * cosY - p.z * sinY;
    let z = p.x * sinY + p.z * cosY;
    let y = p.y * cosX - z * sinX;
    z = p.y * sinX + z * cosX;
    const scale = view.zoom * Math.min(w, h) / 90;
    const persp = 1 / (1 + z / 260);
    return { x: w / 2 + x * scale * persp, y: h / 2 + y * scale * persp, z };
  }

  function renderViewer(r) {
    const canvas = $("viewer");
    const ctx = canvas.getContext("2d");
    const coords = r.structure.coordinates;
    const conf = r.structure.confidence;
    const ss = r.secondary_structure.assignment;
    const bySS = $("color-ss").checked;
    const byConf = $("color-conf").checked;

    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth || 900;
    const h = Math.round(w * 0.58);
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    ctx.clearRect(0, 0, w, h);

    const pts = coords.map((p) => project(p, w, h, state.view));

    // Backbone, drawn back-to-front so nearer segments sit on top.
    const segs = [];
    for (let i = 0; i < pts.length - 1; i++) {
      segs.push({ i, z: (pts[i].z + pts[i + 1].z) / 2 });
    }
    segs.sort((a, b) => a.z - b.z);

    for (const { i } of segs) {
      const a = pts[i], b = pts[i + 1];
      let color;
      if (byConf) {
        color = confColor(conf[i]);
      } else if (bySS) {
        color = SS_COLOR[ss[i]] || SS_COLOR.C;
      } else {
        color = "#4dd4ac";
      }
      ctx.strokeStyle = color;
      ctx.lineWidth = 2.1;
      ctx.globalAlpha = 0.92;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }

    // Residue dots, every 5th, so the trace reads as a chain not a scribble.
    ctx.globalAlpha = 1;
    for (let i = 0; i < pts.length; i += 5) {
      const p = pts[i];
      ctx.fillStyle = byConf ? confColor(conf[i]) : (SS_COLOR[ss[i]] || SS_COLOR.C);
      ctx.beginPath();
      ctx.arc(p.x, p.y, 2.4, 0, Math.PI * 2);
      ctx.fill();
    }

    // Termini markers.
    if (pts.length) {
      ctx.fillStyle = "#4dd4ac";
      ctx.font = "600 11px ui-monospace, monospace";
      ctx.fillText("N", pts[0].x + 6, pts[0].y - 6);
      ctx.fillStyle = "#5aa9f0";
      ctx.fillText("C", pts[pts.length - 1].x + 6, pts[pts.length - 1].y - 6);
    }
  }

  function confColor(c) {
    // Red (low) -> amber -> green (high).
    const t = Math.max(0, Math.min(1, c));
    const r = Math.round(255 * (1 - t) + 77 * t);
    const g = Math.round(107 * (1 - t) + 212 * t);
    const b = Math.round(107 * (1 - t) + 172 * t);
    return `rgb(${r},${g},${b})`;
  }

  function renderContactMap(r) {
    const canvas = $("contactmap");
    const ctx = canvas.getContext("2d");
    const n = r.sequence.length;
    const dpr = window.devicePixelRatio || 1;
    const size = canvas.clientWidth || 520;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.height = size + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    ctx.fillStyle = "#0b0f14";
    ctx.fillRect(0, 0, size, size);

    const pad = 26;
    const plot = size - pad - 8;
    const cell = plot / n;

    // Grid backdrop.
    ctx.strokeStyle = "#1c2634";
    ctx.lineWidth = 1;
    for (let t = 0; t <= 4; t++) {
      const gx = pad + (plot * t) / 4;
      ctx.beginPath(); ctx.moveTo(gx, pad); ctx.lineTo(gx, pad + plot); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(pad, gx); ctx.lineTo(pad + plot, gx); ctx.stroke();
    }

    // Contacts.
    for (const p of r.contacts.pairs) {
      const i = p.i - 1, j = p.j - 1;
      const alpha = 0.35 + 0.65 * p.score;
      ctx.fillStyle = `rgba(77, 212, 172, ${alpha.toFixed(3)})`;
      const s = Math.max(1.4, cell);
      ctx.fillRect(pad + i * cell, pad + j * cell, s, s);
      ctx.fillRect(pad + j * cell, pad + i * cell, s, s);
    }

    // Axes.
    ctx.strokeStyle = "#24303f";
    ctx.strokeRect(pad, pad, plot, plot);
    ctx.fillStyle = "#64748b";
    ctx.font = "10px ui-monospace, monospace";
    ctx.fillText("1", pad - 4, pad + plot + 14);
    ctx.fillText(String(n), pad + plot - 18, pad + plot + 14);
    ctx.save();
    ctx.translate(12, pad + plot);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText("residue j", 0, 0);
    ctx.restore();
    ctx.fillText("residue i", pad + plot / 2 - 24, pad + plot + 14);

    $("contact-hint").textContent = `${r.contacts.count} contacts · density ${r.contacts.density}`;
  }

  function renderProfiles(r) {
    if (!r.profiles) return;
    drawLine($("hydropathy"), r.profiles.hydropathy, "#5aa9f0", 0);
    drawLine($("moment"), r.profiles.hydrophobic_moment, "#4dd4ac", 0);
  }

  function drawLine(canvas, values, color, baseline) {
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth || 520;
    const h = 240;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    if (!values || !values.length) return;
    const pad = 22;
    const min = Math.min(...values, baseline);
    const max = Math.max(...values, baseline);
    const range = max - min || 1;
    const xAt = (i) => pad + (i / (values.length - 1 || 1)) * (w - pad * 2);
    const yAt = (v) => h - pad - ((v - min) / range) * (h - pad * 2);

    // Zero line.
    ctx.strokeStyle = "#24303f";
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(pad, yAt(baseline));
    ctx.lineTo(w - pad, yAt(baseline));
    ctx.stroke();
    ctx.setLineDash([]);

    // Filled area.
    ctx.beginPath();
    ctx.moveTo(xAt(0), yAt(baseline));
    for (let i = 0; i < values.length; i++) ctx.lineTo(xAt(i), yAt(values[i]));
    ctx.lineTo(xAt(values.length - 1), yAt(baseline));
    ctx.closePath();
    ctx.fillStyle = color + "22";
    ctx.fill();

    // Line.
    ctx.beginPath();
    for (let i = 0; i < values.length; i++) {
      const x = xAt(i), y = yAt(values[i]);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.6;
    ctx.stroke();

    // Axis labels.
    ctx.fillStyle = "#64748b";
    ctx.font = "10px ui-monospace, monospace";
    ctx.fillText(max.toFixed(1), 2, pad);
    ctx.fillText(min.toFixed(1), 2, h - pad + 4);
  }

  function renderProps(r) {
    const box = $("props");
    box.innerHTML = "";
    const p = r.properties;
    const rows = [
      ["Length", `${p.length} aa`],
      ["Molecular weight", `${p.molecular_weight_da.toLocaleString()} Da`],
      ["Isoelectric point", p.isoelectric_point],
      ["Net charge (pH 7)", p.net_charge_ph7.toFixed(3)],
      ["GRAVY", p.gravy.toFixed(3)],
      ["Aromaticity", p.aromaticity.toFixed(4)],
      ["Aliphatic index", p.aliphatic_index],
      ["Ext. coeff. 280 nm", `${p.extinction_coefficient_m1cm1.toLocaleString()} M⁻¹cm⁻¹`],
      ["A280 (1 g/L)", p.absorbance_280_1g_per_l],
      ["Radius of gyration", `${r.structure.radius_of_gyration} Å`],
      ["End-to-end distance", `${r.structure.end_to_end_distance} Å`],
      ["Mean confidence", r.structure.mean_confidence.toFixed(3)],
    ];
    for (const [k, v] of rows) {
      const row = el("div", "prop");
      row.append(el("span", "k", k), el("span", "v", String(v)));
      box.append(row);
    }
  }

  function renderTable(r) {
    const table = $("residue-table");
    table.innerHTML = "";
    const thead = el("thead");
    const hr = el("tr");
    for (const h of ["#", "Res", "Name", "SS", "Conf", "x", "y", "z"]) hr.append(el("th", null, h));
    thead.append(hr);
    table.append(thead);

    const tbody = el("tbody");
    const coords = r.structure.coordinates;
    for (let i = 0; i < r.residue_table.length; i++) {
      const row = r.residue_table[i];
      const c = coords[i] || { x: 0, y: 0, z: 0 };
      const tr = el("tr");
      tr.append(el("td", null, String(row.index)));
      tr.append(el("td", null, row.residue));
      tr.append(el("td", null, row.residue_name));
      tr.append(el("td", `ss-cell ${row.ss}`, row.ss));
      tr.append(el("td", null, row.confidence.toFixed(2)));
      tr.append(el("td", null, c.x.toFixed(1)));
      tr.append(el("td", null, c.y.toFixed(1)));
      tr.append(el("td", null, c.z.toFixed(1)));
      tbody.append(tr);
    }
    table.append(tbody);
    $("table-hint").textContent = `${r.residue_table.length} residues`;
  }

  function updateExportHint() {
    const hint = $("export-hint");
    if (state.savedId) {
      hint.textContent = `Saved as #${state.savedId}. Exports are ready.`;
    } else {
      hint.textContent = "Exports need the prediction saved to your account — tick “Save” and re-run.";
    }
  }

  /* ---------------- saved ---------------- */

  async function loadSaved() {
    const list = $("saved-list");
    if (!state.token) {
      list.innerHTML = "";
      list.append(el("p", "hint", "Sign in to see your saved predictions."));
      $("saved-hint").textContent = "";
      return;
    }
    list.innerHTML = "";
    list.append(el("p", "hint", "Loading…"));
    try {
      const rows = await api("/api/predictions?limit=100");
      list.innerHTML = "";
      $("saved-hint").textContent = `${rows.length} saved`;
      if (!rows.length) {
        list.append(el("p", "hint", "Nothing saved yet. Run an analysis and tick “Save”."));
        return;
      }
      for (const row of rows) {
        const item = el("div", "saved-item");
        const meta = el("div", "meta");
        meta.append(el("span", "title", row.label || "Untitled"));
        meta.append(el("span", "sub",
          `${row.length} aa · conf ${row.mean_confidence.toFixed(2)} · ` +
          `${row.contact_count} contacts · ${new Date(row.created_at).toLocaleString()}`));
        const actions = el("div", "row-actions");

        const open = el("button", "btn ghost small", "Open");
        open.type = "button";
        open.addEventListener("click", () => openSaved(row.id));

        const pdb = el("button", "btn ghost small", "PDB");
        pdb.type = "button";
        pdb.addEventListener("click", () => downloadExport(row.id, "pdb"));

        const del = el("button", "btn ghost small", "Delete");
        del.type = "button";
        del.addEventListener("click", () => deleteSaved(row.id));

        actions.append(open, pdb, del);
        item.append(meta, actions);
        list.append(item);
      }
    } catch (e) {
      list.innerHTML = "";
      list.append(el("p", "error", e.message));
    }
  }

  async function openSaved(id) {
    try {
      const data = await api(`/api/predictions/${id}`);
      state.result = data.result;
      state.savedId = data.id;
      switchView("analyze");
      renderResults(data.result);
    } catch (e) {
      alert(e.message);
    }
  }

  async function deleteSaved(id) {
    if (!confirm("Delete this saved prediction? This cannot be undone.")) return;
    try {
      await api(`/api/predictions/${id}`, { method: "DELETE" });
      loadSaved();
    } catch (e) {
      alert(e.message);
    }
  }

  async function downloadExport(id, fmt) {
    try {
      const res = await fetch(`${API}/api/predictions/${id}/export?fmt=${fmt}`, {
        headers: { Authorization: `Bearer ${state.token}` },
      });
      if (!res.ok) throw new Error(`Export failed (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `proteoscope-${id}.${fmt}`;
      document.body.append(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert(e.message);
    }
  }

  /* ---------------- view switching ---------------- */

  function switchView(name) {
    for (const v of ["analyze", "saved", "about"]) {
      $(`view-${v}`).classList.toggle("active", v === name);
      $(`nav-${v}`).classList.toggle("active", v === name);
    }
    if (name === "saved") loadSaved();
  }

  /* ---------------- wiring ---------------- */

  function init() {
    renderAuthSlot();

    $("nav-analyze").addEventListener("click", () => switchView("analyze"));
    $("nav-saved").addEventListener("click", () => switchView("saved"));
    $("nav-about").addEventListener("click", () => switchView("about"));

    $("run").addEventListener("click", runPrediction);
    $("auth-submit").addEventListener("click", submitAuth);
    $("auth-close").addEventListener("click", closeAuth);
    $("auth-toggle").addEventListener("click", () => openAuth(state.authMode === "login" ? "register" : "login"));
    $("auth-modal").addEventListener("click", (e) => { if (e.target.id === "auth-modal") closeAuth(); });
    $("auth-password").addEventListener("keydown", (e) => { if (e.key === "Enter") submitAuth(); });

    document.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const key = chip.dataset.example;
        if (EXAMPLES[key]) $("sequence").value = EXAMPLES[key];
      });
    });

    document.querySelectorAll("[data-export]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (!state.savedId) {
          $("input-error").textContent = "Save the prediction first, then export.";
          $("input-error").hidden = false;
          return;
        }
        downloadExport(state.savedId, btn.dataset.export);
      });
    });

    $("color-ss").addEventListener("change", () => { if (state.result) renderViewer(state.result); });
    $("color-conf").addEventListener("change", () => { if (state.result) renderViewer(state.result); });
    $("reset-view").addEventListener("click", () => {
      state.view.rotX = -0.35; state.view.rotY = 0.6; state.view.zoom = 1;
      if (state.result) renderViewer(state.result);
    });

    // Viewer interaction.
    const canvas = $("viewer");
    const startDrag = (x, y) => { state.view.dragging = true; state.view.lastX = x; state.view.lastY = y; };
    const moveDrag = (x, y) => {
      if (!state.view.dragging) return;
      state.view.rotY += (x - state.view.lastX) * 0.01;
      state.view.rotX += (y - state.view.lastY) * 0.01;
      state.view.rotX = Math.max(-1.5, Math.min(1.5, state.view.rotX));
      state.view.lastX = x; state.view.lastY = y;
      if (state.result) renderViewer(state.result);
    };
    const endDrag = () => { state.view.dragging = false; };

    canvas.addEventListener("mousedown", (e) => startDrag(e.clientX, e.clientY));
    window.addEventListener("mousemove", (e) => moveDrag(e.clientX, e.clientY));
    window.addEventListener("mouseup", endDrag);
    canvas.addEventListener("touchstart", (e) => {
      if (e.touches.length === 1) startDrag(e.touches[0].clientX, e.touches[0].clientY);
    }, { passive: true });
    canvas.addEventListener("touchmove", (e) => {
      if (e.touches.length === 1) { moveDrag(e.touches[0].clientX, e.touches[0].clientY); e.preventDefault(); }
    }, { passive: false });
    canvas.addEventListener("touchend", endDrag);
    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      state.view.zoom = Math.max(0.3, Math.min(4, state.view.zoom * (e.deltaY > 0 ? 0.92 : 1.08)));
      if (state.result) renderViewer(state.result);
    }, { passive: false });

    window.addEventListener("resize", () => {
      if (state.result) {
        renderViewer(state.result);
        renderContactMap(state.result);
        renderProfiles(state.result);
      }
    });

    // Prefill the example so the page is never empty on first load.
    $("sequence").value = EXAMPLES.lysozyme;
  }

  document.addEventListener("DOMContentLoaded", init);
})();
