(function () {
  const { api, toast, stateBadge } = window.CultAgent;

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function flatMetrics(raw) {
    const system = (raw && raw.system) || {};
    const ram = system.ram || {};
    return {
      cpu_percent: system.cpu_percent,
      memory_percent: ram.percent,
    };
  }

  async function refreshHostBadge() {
    const el = document.getElementById("hostMeta");
    if (!el) return;
    try {
      const [s, metricsRaw] = await Promise.all([
        api("/v1/status"),
        api("/v1/metrics").catch(() => null),
      ]);
      const id = s.identity || {};
      const m = flatMetrics(metricsRaw || {});
      const name = id.display_name || "node";
      const status = (id.status || "?").toLowerCase();
      const node = id.cloud_node_id || id.node_id || "local";
      const cpu = m.cpu_percent != null ? `${Math.round(m.cpu_percent)}%` : null;
      const mem = m.memory_percent != null ? `${Math.round(m.memory_percent)}%` : null;

      const online = status === "online" || status === "registered" || status === "active";
      const cloudCls = online ? "ok cloud" : status === "error" ? "err cloud" : "cloud";

      const parts = [];
      parts.push(
        `<span class="cf-pill ${cloudCls}"><span class="dot"></span>${esc(name)} · ${esc(status)}</span>`
      );
      if (cpu != null) {
        parts.push(`<span class="cf-pill"><span class="dot"></span>CPU ${esc(cpu)}</span>`);
      }
      if (mem != null) {
        parts.push(`<span class="cf-pill"><span class="dot"></span>MEM ${esc(mem)}</span>`);
      }
      parts.push(`<span class="cf-pill mono" title="${esc(node)}">${esc(node.length > 18 ? node.slice(0, 16) + "…" : node)}</span>`);
      el.innerHTML = parts.join("");
    } catch (e) {
      el.innerHTML = `<span class="cf-pill err"><span class="dot"></span>panel offline?</span>`;
    }
  }

  document.querySelectorAll("[data-server-action]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.getAttribute("data-server-id");
      const act = btn.getAttribute("data-server-action");
      const flash = document.getElementById("flash");
      btn.disabled = true;
      try {
        const body = act === "start" ? JSON.stringify({ accept_eula: true }) : "{}";
        await api(`/v1/servers/${id}/${act}`, { method: "POST", body });
        toast(flash, `${act} requested`, true);
        setTimeout(() => location.reload(), 600);
      } catch (e) {
        toast(flash, e.message || String(e), false);
      } finally {
        btn.disabled = false;
      }
    });
  });

  document.querySelectorAll("[data-copy]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const sel = btn.getAttribute("data-copy");
      const el = sel ? document.querySelector(sel) : null;
      const text = (el && (el.textContent || "").trim()) || "";
      const flash = document.getElementById("flash");
      if (!text || text === "—") {
        toast(flash, "Nothing to copy", false);
        return;
      }
      try {
        await navigator.clipboard.writeText(text);
        toast(flash, "Copied: " + text, true);
      } catch (e) {
        toast(flash, "Copy failed", false);
      }
    });
  });

  const createForm = document.getElementById("createServerForm");
  if (createForm) {
    createForm.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const flash = document.getElementById("flash");
      const fd = new FormData(createForm);
      const payload = {
        name: fd.get("name"),
        minecraft_version: fd.get("minecraft_version") || null,
        loader: fd.get("loader") || "vanilla",
        port: Number(fd.get("port") || 25565),
        download: fd.get("download") === "on",
        accept_eula: fd.get("accept_eula") === "on",
        auto_start: fd.get("auto_start") === "on",
      };
      const startNow = fd.get("start_now") === "on";
      const submitBtn = createForm.querySelector('button[type="submit"]');
      if (submitBtn) submitBtn.disabled = true;
      try {
        const res = await api("/v1/servers", { method: "POST", body: JSON.stringify(payload) });
        const sid = (res.data && res.data.server_id) || res.server_id;
        if (startNow && sid) {
          try {
            await api(`/v1/servers/${sid}/start`, {
              method: "POST",
              body: JSON.stringify({ accept_eula: true }),
            });
            toast(flash, "Server created — starting…", true);
          } catch (startErr) {
            toast(flash, "Created, but start failed: " + (startErr.message || startErr), false);
            setTimeout(() => {
              location.href = `/panel/servers/${sid}`;
            }, 1200);
            return;
          }
        } else {
          toast(flash, "Server created", true);
        }
        location.href = `/panel/servers/${sid}`;
      } catch (e) {
        toast(flash, e.message || String(e), false);
      } finally {
        if (submitBtn) submitBtn.disabled = false;
      }
    });
  }

  const railToggle = document.getElementById("railToggle");
  if (railToggle) {
    railToggle.addEventListener("click", () => {
      document.body.classList.toggle("rail-open");
    });
    document.addEventListener("click", (e) => {
      if (!document.body.classList.contains("rail-open")) return;
      const rail = document.getElementById("rail");
      if (rail && !rail.contains(e.target) && e.target !== railToggle && !railToggle.contains(e.target)) {
        document.body.classList.remove("rail-open");
      }
    });
  }

  refreshHostBadge();
  setInterval(refreshHostBadge, 15000);

  window.CultPanel = { api, toast, stateBadge };
})();
