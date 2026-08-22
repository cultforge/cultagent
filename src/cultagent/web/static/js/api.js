window.CultAgent = (() => {
  async function api(path, opts = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
      ...opts,
    });
    let data = {};
    try { data = await res.json(); } catch (_) {}
    if (!res.ok) {
      const msg = data.error || data.detail || (data.data && data.data.error) || res.statusText;
      throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    }
    return data;
  }

  function toast(el, message, ok = true) {
    if (!el) return;
    el.className = "cf-flash flash " + (ok ? "ok" : "err");
    el.textContent = message;
    el.hidden = false;
  }

  function stateBadge(state) {
    const s = (state || "unknown").toLowerCase();
    let cls = "badge";
    if (s === "running" || s === "online") cls += " ok";
    else if (s === "crashed") cls += " danger";
    else if (s === "starting" || s === "stopping") cls += " warn";
    return `<span class="${cls}">${s}</span>`;
  }

  return { api, toast, stateBadge };
})();
