"use strict";

const SCALARS = [
  "district", "crs", "parcel", "pid", "county",
  "owner_name", "owner_marital", "owner_interest", "owner_phone",
  "mail_addr1", "mail_addr2", "prop_addr1", "prop_addr2",
  "fee_description",
  "mortgages_name", "mortgages_date", "mortgages_amount",
  "leases_name", "leases_type", "leases_term",
  "defects",
  "township", "school_district",
  "cauv_comments",
  "cover_from", "cover_to", "sign_datetime", "agent_name",
  "update_from", "update_to", "update_datetime", "update_agent_name", "update_comments",
];
const TAX_COLS = ["aud_par_no", "land", "building", "total", "taxes"];
const CHAIN_COLS = [
  "grantor", "grantee", "date_signed", "date_recorded",
  "volume_page", "conveyance_fee", "instrument_type", "description",
];
const EASEMENT_COLS = ["name", "type"];

let currentJobId = null;

// ---------------------------------------------------------------- dates
// Fields rendered as native pickers. Internally a date input holds ISO
// (YYYY-MM-DD / YYYY-MM-DDTHH:MM); we store & output MM/DD/YYYY[, h:mm AM/PM].
const DATE_KEYS = new Set([
  "cover_from", "cover_to", "update_from", "update_to", "mortgages_date", "date_signed",
]);
const DATETIME_KEYS = new Set(["sign_datetime", "update_datetime", "date_recorded"]);

function dateKind(key) {
  if (DATE_KEYS.has(key)) return false;     // date only
  if (DATETIME_KEYS.has(key)) return true;  // date + time
  return null;                              // not a date field
}
const pad = (n) => String(n).padStart(2, "0");

function displayToISO(val, isDateTime) {
  if (!val) return "";
  val = String(val).trim();
  if (/^\d{4}-\d{2}-\d{2}/.test(val)) return isDateTime ? val.slice(0, 16) : val.slice(0, 10);
  const m = val.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})(?:[ T]+(\d{1,2}):(\d{2})\s*([AaPp][Mm])?)?/);
  if (!m) return "";
  let [, mo, d, y, h, mi, ap] = m;
  if (y.length === 2) y = "20" + y;
  let iso = `${y}-${pad(mo)}-${pad(d)}`;
  if (isDateTime) {
    let H = h == null ? 0 : parseInt(h, 10);
    if (ap) { ap = ap.toUpperCase(); if (ap === "PM" && H < 12) H += 12; if (ap === "AM" && H === 12) H = 0; }
    iso += `T${pad(H)}:${mi || "00"}`;
  }
  return iso;
}

function isoToDisplay(iso, isDateTime) {
  if (!iso) return "";
  if (isDateTime) {
    const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
    if (!m) return "";
    const [, y, mo, d, H, mi] = m;
    let h = parseInt(H, 10); const ap = h >= 12 ? "PM" : "AM"; h = h % 12 || 12;
    return `${mo}/${d}/${y} ${h}:${mi} ${ap}`;
  }
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[2]}/${m[3]}/${m[1]}` : "";
}

// stored value -> what a form control should display
function storedToInput(key, stored) {
  const k = dateKind(key);
  return k === null ? (stored || "") : displayToISO(stored || "", k);
}
// form control value -> what we store/output
function inputToStored(key, raw) {
  const k = dateKind(key);
  return k === null ? raw.trim() : isoToDisplay(raw, k);
}

// ---------------------------------------------------------------- repeaters
// Columns that use an auto-expanding text area instead of a single-line input.
// "name" here is the Easement Name & Address column.
const EXPANDABLE_COLS = new Set(["grantor", "grantee", "description", "name"]);

function autoGrow(el) {
  el.style.height = "auto";
  el.style.height = el.scrollHeight + "px";
}

function repeaterRow(cols, values) {
  const tr = document.createElement("tr");
  for (const c of cols) {
    const td = document.createElement("td");
    let inp;
    if (EXPANDABLE_COLS.has(c)) {
      inp = document.createElement("textarea");
      inp.rows = 1;
      inp.className = "grow";
      inp.addEventListener("input", () => autoGrow(inp));
    } else {
      inp = document.createElement("input");
      const k = dateKind(c);
      if (k === false) inp.type = "date";
      else if (k === true) inp.type = "datetime-local";
    }
    inp.dataset.col = c;
    inp.value = storedToInput(c, values && values[c]);
    td.appendChild(inp);
    tr.appendChild(td);
  }
  const tdx = document.createElement("td");
  const del = document.createElement("button");
  del.type = "button";
  del.className = "row-del";
  del.textContent = "✕";
  del.onclick = () => tr.remove();
  tdx.appendChild(del);
  tr.appendChild(tdx);
  return tr;
}
function appendRow(tableId, cols, v) {
  const tr = repeaterRow(cols, v);
  document.querySelector(`#${tableId} tbody`).appendChild(tr);
  // Size to content after layout/CSS has settled (avoids a pre-style mis-measure).
  requestAnimationFrame(() => tr.querySelectorAll("textarea").forEach(autoGrow));
}
function addTaxRow(v) { appendRow("tax-table", TAX_COLS, v); }
function addChainRow(v) { appendRow("chain-table", CHAIN_COLS, v); }
function addEasementRow(v) { appendRow("easements-table", EASEMENT_COLS, v); }

function collectRows(tableId, cols) {
  const out = [];
  for (const tr of document.querySelectorAll(`#${tableId} tbody tr`)) {
    const obj = {};
    let any = false;
    tr.querySelectorAll("input, textarea").forEach((inp) => {
      const v = inputToStored(inp.dataset.col, inp.value);
      obj[inp.dataset.col] = v;
      if (v) any = true;
    });
    if (any) out.push(obj);
  }
  return out;
}

// ---------------------------------------------------------------- form <-> data
function collect() {
  const job = {};
  for (const id of SCALARS) job[id] = inputToStored(id, document.getElementById(id).value);
  job.report_type = document.querySelector("input[name=report_type]:checked").value;
  job.cauv = document.getElementById("cauv").checked;
  job.taxes = collectRows("tax-table", TAX_COLS);
  job.chain = collectRows("chain-table", CHAIN_COLS);
  job.easements = collectRows("easements-table", EASEMENT_COLS);
  return job;
}

async function loadCounties() {
  try {
    const r = await apiFetch("/api/counties");
    const counties = await r.json();
    const sel = document.getElementById("county");
    const current = sel.value;
    sel.innerHTML =
      `<option value="">— select county —</option>` +
      counties.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
    setCounty(current);
  } catch (e) {
    /* leave the placeholder-only select in place */
  }
}

function setCounty(v) {
  const sel = document.getElementById("county");
  if (v && !Array.from(sel.options).some((o) => o.value === v)) {
    sel.add(new Option(v, v)); // keep a saved value even if not in the list
  }
  sel.value = v || "";
}

function fill(data) {
  for (const id of SCALARS) document.getElementById(id).value = storedToInput(id, data[id]);
  setCounty(data.county || "");
  // Resize any scalar auto-grow textareas to the loaded content.
  requestAnimationFrame(() =>
    document.querySelectorAll(".form-wrap > * textarea.grow").forEach((el) => {
      if (!el.closest("table.repeater")) autoGrow(el);
    })
  );
  const rt = data.report_type || "42year";
  const radio = document.querySelector(`input[name=report_type][value="${rt}"]`);
  if (radio) radio.checked = true;
  document.getElementById("cauv").checked = !!data.cauv;
  document.querySelector("#tax-table tbody").innerHTML = "";
  document.querySelector("#chain-table tbody").innerHTML = "";
  document.querySelector("#easements-table tbody").innerHTML = "";
  (data.taxes && data.taxes.length ? data.taxes : [{}]).forEach(addTaxRow);
  (data.chain && data.chain.length ? data.chain : [{}]).forEach(addChainRow);
  // Migrate legacy single-entry easement fields to the new repeater shape.
  let eas = data.easements;
  if ((!eas || !eas.length) && (data.easements_name || data.easements_type)) {
    eas = [{ name: data.easements_name || "", type: data.easements_type || "" }];
  }
  (eas && eas.length ? eas : [{}]).forEach(addEasementRow);
}

function newJob() {
  currentJobId = null;
  document.getElementById("title-form").reset();
  fill({});
  document.getElementById("current-job").textContent = "New (unsaved) job";
  document.getElementById("result").innerHTML = "";
  const s = document.getElementById("save-status");
  if (s) { s.textContent = ""; s.className = "muted small"; }
  renderActive();
}

// ---------------------------------------------------------------- API
async function save() {
  const btn = document.getElementById("btn-save");
  const status = document.getElementById("save-status");
  btn.disabled = true;
  const label0 = btn.textContent;
  btn.textContent = "Saving…";
  try {
    const r = await apiFetch("/api/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: currentJobId, job: collect() }),
    });
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    currentJobId = data.job_id;
    document.getElementById("current-job").textContent = "Job: " + data.label;
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    status.textContent = `Saved at ${hh}:${mm}`;
    status.className = "muted small";
    await loadJobs();
  } catch (e) {
    status.textContent = `Could not save: ${String(e.message || e)}`;
    status.className = "small banner err";
  } finally {
    btn.disabled = false;
    btn.textContent = label0;
  }
}

async function generate() {
  const btn = document.getElementById("btn-generate");
  btn.disabled = true;
  btn.textContent = "Generating…";
  const res = document.getElementById("result");
  res.innerHTML = "";
  try {
    const r = await apiFetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: currentJobId, job: collect() }),
    });
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    currentJobId = data.job_id;
    document.getElementById("current-job").textContent = "Job: " + data.label;
    renderResult(data);
    await loadJobs();
  } catch (e) {
    res.innerHTML = `<div class="banner err">Error: ${escapeHtml(String(e))}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Generate Forms";
  }
}

function renderResult(data) {
  const f = data.files;
  const fileRow = (label, url) =>
    url ? `<div class="file"><span>${label}</span><a href="${url}">Download</a></div>` : "";
  let html = `<div class="banner ok">Forms generated.</div>`;
  html += `<div class="group">RE 46 — Title Report</div>`;
  html += fileRow("Word (.docx)", f.re46_docx);
  html += `<div class="group">RE 46-1 — Title Chain</div>`;
  html += fileRow("Word (.docx)", f.chain_docx);
  document.getElementById("result").innerHTML = html;
}

async function loadJobs() {
  const r = await apiFetch("/api/jobs");
  const jobs = await r.json();
  const ul = document.getElementById("jobs-list");
  ul.innerHTML = "";
  for (const j of jobs) {
    const li = document.createElement("li");
    li.dataset.id = j.id;
    li.innerHTML =
      `<span class="jx" title="Delete">✕</span>` +
      `<div class="jl">${escapeHtml(j.label || j.id)}</div>` +
      `<div class="jd">${(j.updated_at || "").replace("T", " ")}</div>`;
    li.querySelector(".jx").onclick = (ev) => { ev.stopPropagation(); deleteJob(j.id); };
    li.onclick = () => openJob(j.id);
    ul.appendChild(li);
  }
  renderActive();
}

function renderActive() {
  document.querySelectorAll("#jobs-list li").forEach((li) =>
    li.classList.toggle("active", li.dataset.id === currentJobId));
}

async function openJob(id) {
  const r = await apiFetch("/api/jobs/" + id);
  if (!r.ok) return;
  const job = await r.json();
  currentJobId = id;
  fill(job.data);
  document.getElementById("current-job").textContent = "Job: " + (job.label || id);
  document.getElementById("result").innerHTML = "";
  const s = document.getElementById("save-status");
  if (s) { s.textContent = ""; s.className = "muted small"; }
  renderActive();
}

async function deleteJob(id) {
  if (!confirm("Delete this saved job?")) return;
  await apiFetch("/api/jobs/" + id, { method: "DELETE" });
  if (currentJobId === id) newJob();
  await loadJobs();
}

function escapeHtml(s) {
  return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// ---------------------------------------------------------------- auth/session
// Any 401 means the session ended — bounce to the login page.
async function apiFetch(url, opts) {
  const r = await fetch(url, opts);
  if (r.status === 401) {
    window.location.href = "/login";
    throw new Error("Session expired");
  }
  return r;
}

async function loadMe() {
  try {
    const r = await apiFetch("/api/me");
    const me = await r.json();
    document.getElementById("who").textContent = `${me.user.name} · ${me.business.name}`;
    return me;
  } catch (e) { return null; }
}

function showForcedPwChange() {
  document.getElementById("pw-modal").hidden = false;
  document.getElementById("pw-new").focus();
}

async function submitPwChange() {
  const np = document.getElementById("pw-new").value;
  const cf = document.getElementById("pw-confirm").value;
  const err = document.getElementById("pw-error");
  err.hidden = true;
  if (np.length < 8) { err.textContent = "Password must be at least 8 characters."; err.hidden = false; return; }
  if (np !== cf) { err.textContent = "Passwords do not match."; err.hidden = false; return; }
  const btn = document.getElementById("pw-submit");
  btn.disabled = true; btn.textContent = "Saving…";
  try {
    const r = await apiFetch("/api/change-password", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_password: np }),
    });
    if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.detail || "Failed"); }
    window.location.reload();
  } catch (e) {
    err.textContent = String(e.message || e); err.hidden = false;
    btn.disabled = false; btn.textContent = "Save & continue";
  }
}

async function logout() {
  try { await fetch("/api/logout", { method: "POST" }); } catch (e) { /* ignore */ }
  window.location.href = "/login";
}

// ---------------------------------------------------------------- view toggle
function showForm(which) {
  document.getElementById("view-re46").hidden = which !== "re46";
  document.getElementById("view-chain").hidden = which !== "chain";
}

// ---------------------------------------------------------------- wire up
document.addEventListener("click", (e) => {
  const add = e.target.dataset && e.target.dataset.add;
  if (add === "tax") addTaxRow();
  if (add === "chain") addChainRow();
  if (add === "easement") addEasementRow();
});
document.getElementById("form-select").onchange = (e) => showForm(e.target.value);
document.getElementById("btn-save").onclick = save;
document.getElementById("btn-generate").onclick = generate;
document.getElementById("btn-new").onclick = newJob;
document.getElementById("btn-logout").onclick = logout;
document.getElementById("pw-submit").onclick = submitPwChange;

// Wire static (non-repeater) auto-grow textareas (e.g. easement Name & Address).
document.querySelectorAll("textarea.grow").forEach((el) => {
  if (!el.closest("table.repeater")) {
    el.addEventListener("input", () => autoGrow(el));
  }
});

showForm(document.getElementById("form-select").value);
(async () => {
  const me = await loadMe();
  if (!me) return; // bounced to /login
  if (me.must_change_password) { showForcedPwChange(); return; }
  // Each step is isolated so one failure can't stop the others — in particular
  // the Saved Jobs sidebar (loadJobs) must always load.
  try { loadCounties(); } catch (e) { console.error("loadCounties failed", e); }
  try { newJob(); } catch (e) { console.error("newJob failed", e); }
  try { loadJobs(); } catch (e) { console.error("loadJobs failed", e); }
})();
