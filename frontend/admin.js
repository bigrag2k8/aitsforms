"use strict";

async function apiFetch(url, opts) {
  const r = await fetch(url, opts);
  if (r.status === 401) {
    window.location.href = "/admin/login";
    throw new Error("Session expired");
  }
  return r;
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

async function loadMe() {
  try {
    const me = await (await apiFetch("/api/admin/me")).json();
    document.getElementById("who").textContent = `${me.admin.name} · admin`;
  } catch (e) { /* redirected */ }
}

async function logout() {
  try { await fetch("/api/admin/logout", { method: "POST" }); } catch (e) {}
  window.location.href = "/admin/login";
}

// ----- credential reveal modal -----
function showCreds(title, lines) {
  document.getElementById("cred-title").textContent = title;
  document.getElementById("cred-body").textContent = lines.join("\n");
  document.getElementById("cred-modal").hidden = false;
}
document.getElementById("cred-close").onclick = () =>
  (document.getElementById("cred-modal").hidden = true);

// ----- businesses -----
async function loadBusinesses() {
  const list = await (await apiFetch("/api/admin/businesses")).json();
  const root = document.getElementById("businesses");
  root.innerHTML = "";
  if (!list.length) { root.innerHTML = `<p class="muted">No businesses yet.</p>`; return; }
  for (const b of list) root.appendChild(renderBusiness(b));
}

function renderBusiness(b) {
  const wrap = document.createElement("div");
  wrap.className = "biz";
  const active = !!b.active;
  wrap.innerHTML = `
    <div class="biz-head">
      <div>
        <span class="biz-name">${esc(b.name)}</span>
        <span class="pill ${active ? "on" : "off"}">${active ? "active" : "inactive"}</span>
        <span class="muted small">#${b.id} · ${b.user_count} user(s)</span>
      </div>
      <div class="biz-actions">
        <button class="ghost" data-act="toggle">${active ? "Deactivate" : "Activate"}</button>
        <button class="ghost" data-act="users">Manage users</button>
      </div>
    </div>
    <div class="biz-users" hidden></div>`;

  wrap.querySelector('[data-act="toggle"]').onclick = async () => {
    await apiFetch(`/api/admin/businesses/${b.id}/active`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active: !active }),
    });
    loadBusinesses();
  };
  const usersEl = wrap.querySelector(".biz-users");
  wrap.querySelector('[data-act="users"]').onclick = () => {
    usersEl.hidden = !usersEl.hidden;
    if (!usersEl.hidden) loadUsers(b.id, usersEl);
  };
  return wrap;
}

async function loadUsers(businessId, el) {
  const users = await (await apiFetch(`/api/admin/businesses/${businessId}/users`)).json();
  el.innerHTML =
    (users.length
      ? users.map((u) => `
        <div class="user-row">
          <span>${esc(u.name)} &lt;${esc(u.email)}&gt;</span>
          <button class="ghost small" data-reset="${u.id}">Reset password</button>
        </div>`).join("")
      : `<p class="muted small">No users yet.</p>`) +
    `<div class="row-inline add-user">
        <input data-f="email" type="email" placeholder="email@example.com" />
        <input data-f="name" placeholder="Full name" />
        <button class="primary narrow" data-add="${businessId}">Add user</button>
     </div>`;

  el.querySelectorAll("[data-reset]").forEach((btn) => {
    btn.onclick = async () => {
      if (!confirm("Reset this user's password?")) return;
      const r = await (await apiFetch(`/api/admin/users/${btn.dataset.reset}/reset-password`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
      })).json();
      showCreds("New password", [`Password: ${r.password}`]);
    };
  });

  el.querySelector("[data-add]").onclick = async () => {
    const email = el.querySelector('[data-f="email"]').value.trim();
    const name = el.querySelector('[data-f="name"]').value.trim();
    if (!email || !name) { alert("Email and name are required"); return; }
    const r = await apiFetch("/api/admin/users", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ business_id: businessId, email, name }),
    });
    if (!r.ok) { const d = await r.json().catch(() => ({})); alert(d.detail || "Failed"); return; }
    const u = await r.json();
    showCreds("New user created", [`Email: ${u.email}`, `Password: ${u.password}`]);
    loadUsers(businessId, el);
    loadBusinesses();
  };
}

document.getElementById("btn-add-business").onclick = async () => {
  const inp = document.getElementById("new-business-name");
  const name = inp.value.trim();
  if (!name) return;
  await apiFetch("/api/admin/businesses", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  inp.value = "";
  loadBusinesses();
};
document.getElementById("btn-logout").onclick = logout;

loadMe();
loadBusinesses();
