const g = id => document.getElementById(id);
const API = (location.origin.replace(/:\d+$/, ':8321'));
const val = id => g(id).value.trim();

function say(msg, good) {
  g("msg").textContent = msg;
  g("msg").style.color = good ? "var(--green)" : "var(--red)";
}

async function req(url, method = "GET", body) {
  const opt = { method, headers: { "Content-Type": "application/json" } };
  if (body) opt.body = JSON.stringify(body);
  const r = await fetch(API + url, opt);
  const data = await r.json().catch(() => null);
  if (!r.ok) throw new Error((data && data.message) || ("HTTP " + r.status));
  return data;
}

async function loadProfiles() {
  try {
    const d = await req("/api/profiles");
    const sel = g("sel");
    sel.innerHTML = "";
    const opt0 = document.createElement("option");
    opt0.value = "";
    opt0.textContent = "— choose existing —";
    sel.appendChild(opt0);
    Object.keys(d.profiles || {}).forEach(n => {
      const o = document.createElement("option");
      o.value = n;
      o.textContent = n + (d.active === n ? " (active)" : "");
      sel.appendChild(o);
    });
  } catch (e) {
    say(e.message, false);
  }
}

g("test").onclick = async () => {
  try {
    const b = { name: val("name") || val("sel"), user: val("user"), host: val("host") };
    if (!b.name || !b.user || !b.host) throw new Error("Fill name/user/host");
    await req("/api/profile/test", "POST", b);
    say("SSH OK ✓", true);
  } catch (e) {
    say(e.message, false);
  }
};

g("save").onclick = async () => {
  try {
    const b = { name: val("name"), user: val("user"), host: val("host") };
    if (!b.name || !b.user || !b.host) throw new Error("Fill name/user/host");
    await req("/api/profile/save", "POST", b);
    await loadProfiles();
    say("Saved ✓", true);
  } catch (e) {
    say(e.message, false);
  }
};

g("login").onclick = async () => {
  try {
    const name = val("sel") || val("name");
    if (!name) throw new Error("Pick or create a profile first");
    await req("/api/login", "POST", { name });
    say("Logging in…", true);
    setTimeout(() => (window.location.href = "/dashboard.html"), 600);
  } catch (e) {
    say(e.message, false);
  }
};

loadProfiles();