(function () {
  const api = (window.CultPanel && window.CultPanel.api) || (window.CultAgent && window.CultAgent.api);
  const toast = (window.CultPanel && window.CultPanel.toast) || (window.CultAgent && window.CultAgent.toast);
  const flash = document.getElementById("flash");
  if (!api) return;

  async function cmd(command, params) {
    return api("/v1/command", {
      method: "POST",
      body: JSON.stringify({ command, params: params || {} }),
    });
  }

  const setupBtn = document.getElementById("playitSetup");
  if (setupBtn) {
    setupBtn.addEventListener("click", async () => {
      setupBtn.disabled = true;
      try {
        const res = await cmd("playit.setup", {
          force: false,
          open_browser: false,
          wait_exchange: false,
        });
        const data = (res && res.data) || {};
        const url =
          data.claim_url ||
          data.setup_url ||
          setupBtn.getAttribute("data-setup-url") ||
          "https://playit.gg/claim/";
        if (data.claim_code) {
          toast(
            flash,
            `Claim code ${data.claim_code} — open link, then click Finish claim`,
            true
          );
        } else {
          toast(flash, "playit ready — finish claim in the browser", true);
        }
        window.open(url, "_blank", "noopener");
        setTimeout(() => location.reload(), 900);
      } catch (e) {
        toast(flash, e.message || String(e), false);
      } finally {
        setupBtn.disabled = false;
      }
    });
  }

  const claimWaitBtn = document.getElementById("playitClaimWait");
  if (claimWaitBtn) {
    claimWaitBtn.addEventListener("click", async () => {
      claimWaitBtn.disabled = true;
      try {
        toast(flash, "Waiting for claim approval… keep the browser tab open", true);
        const code = claimWaitBtn.getAttribute("data-claim-code") || undefined;
        const res = await cmd("playit.claim.wait", {
          claim_code: code,
          timeout: 300,
        });
        const data = (res && res.data) || {};
        if (data.has_secret || (res && res.ok)) {
          toast(flash, "Claim complete — secret stored", true);
        } else {
          toast(flash, (data && data.error) || "Claim not finished yet — retry", false);
        }
        setTimeout(() => location.reload(), 900);
      } catch (e) {
        toast(flash, e.message || String(e), false);
      } finally {
        claimWaitBtn.disabled = false;
      }
    });
  }

  const resetBtn = document.getElementById("playitReset");
  if (resetBtn) {
    resetBtn.addEventListener("click", async () => {
      if (!confirm("Stop playit and clear the stored secret on this machine?")) return;
      resetBtn.disabled = true;
      try {
        await cmd("playit.reset", {});
        toast(flash, "playit reset — secret cleared", true);
        setTimeout(() => location.reload(), 700);
      } catch (e) {
        toast(flash, e.message || String(e), false);
      } finally {
        resetBtn.disabled = false;
      }
    });
  }

  const secretForm = document.getElementById("playitSecretForm");
  if (secretForm) {
    secretForm.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const fd = new FormData(secretForm);
      const secret = String(fd.get("secret") || "").trim();
      if (!secret) {
        toast(flash, "Paste a secret key first", false);
        return;
      }
      try {
        await cmd("playit.secret", { secret });
        secretForm.reset();
        toast(flash, "Secret saved on this machine", true);
        setTimeout(() => location.reload(), 700);
      } catch (e) {
        toast(flash, e.message || String(e), false);
      }
    });
  }

  const tunnelBtn = document.getElementById("playitTunnel");
  if (tunnelBtn) {
    tunnelBtn.addEventListener("click", async () => {
      tunnelBtn.disabled = true;
      try {
        const res = await cmd("playit.start", { ensure_tunnel: true });
        const data = (res && res.data) || {};
        if (data.public_endpoint) {
          toast(flash, `Tunnel ready: ${data.public_endpoint}`, true);
        } else {
          toast(flash, "Tunnel ensured — public address pending", true);
        }
        setTimeout(() => location.reload(), 900);
      } catch (e) {
        toast(flash, e.message || String(e), false);
      } finally {
        tunnelBtn.disabled = false;
      }
    });
  }

  const startBtn = document.getElementById("playitStart");
  if (startBtn) {
    startBtn.addEventListener("click", async () => {
      startBtn.disabled = true;
      try {
        await cmd("network.use", { provider: "playit" });
        const res = await cmd("playit.start", {});
        const data = (res && res.data) || {};
        const public =
          data.public_endpoint ||
          (data.tunnel && data.tunnel.public_endpoint);
        if (public) {
          toast(flash, `playit up — join ${public}`, true);
        } else if (data.tunnel_error) {
          toast(flash, data.tunnel_error, false);
        } else {
          toast(flash, "playit starting", true);
        }
        setTimeout(() => location.reload(), 1200);
      } catch (e) {
        toast(flash, e.message || String(e), false);
      } finally {
        startBtn.disabled = false;
      }
    });
  }

  const stopBtn = document.getElementById("playitStop");
  if (stopBtn) {
    stopBtn.addEventListener("click", async () => {
      stopBtn.disabled = true;
      try {
        await cmd("playit.stop", {});
        toast(flash, "playit stopped", true);
        setTimeout(() => location.reload(), 700);
      } catch (e) {
        toast(flash, e.message || String(e), false);
      } finally {
        stopBtn.disabled = false;
      }
    });
  }

  const directBtn = document.getElementById("networkDirect");
  if (directBtn) {
    directBtn.addEventListener("click", async () => {
      try {
        await cmd("network.use", { provider: "direct" });
        toast(flash, "Using direct / LAN", true);
        setTimeout(() => location.reload(), 600);
      } catch (e) {
        toast(flash, e.message || String(e), false);
      }
    });
  }
})();
