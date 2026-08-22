(function () {
  const box = document.getElementById("console");
  const input = document.getElementById("consoleInput");
  const send = document.getElementById("consoleSend");
  if (!box || !window.SERVER_ID) return;

  let afterSeq = 0;
  let usingWs = false;
  let pollTimer = null;
  const { api, toast } = window.CultPanel || window.CultAgent;

  function appendLines(lines) {
    for (const line of lines || []) {
      const text = typeof line === "string" ? line : (line.text || "");
      box.textContent += text.endsWith("\n") ? text : text + "\n";
      if (line && line.seq != null) afterSeq = Math.max(afterSeq, line.seq);
    }
    box.scrollTop = box.scrollHeight;
  }

  async function pollOnce() {
    try {
      const res = await api(`/v1/servers/${window.SERVER_ID}/console?after_seq=${afterSeq}&limit=300`);
      const data = res.data || res;
      appendLines(data.lines || []);
      if (data.next_seq != null) afterSeq = Math.max(afterSeq, data.next_seq);
    } catch (_) {}
  }

  function startPoll() {
    if (pollTimer) return;
    pollOnce();
    pollTimer = setInterval(pollOnce, 1500);
  }

  function stopPoll() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function connectWs() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${location.host}/ws/servers/${window.SERVER_ID}/console`;
    let ws;
    try {
      ws = new WebSocket(url);
    } catch (_) {
      startPoll();
      return;
    }

    ws.onopen = () => {
      usingWs = true;
      stopPoll();
    };
    ws.onmessage = (ev) => {
      let msg;
      try {
        msg = JSON.parse(ev.data);
      } catch (_) {
        return;
      }
      if (msg.type === "snapshot" || msg.type === "lines") {
        appendLines(msg.lines || []);
        if (msg.next_seq != null) afterSeq = Math.max(afterSeq, msg.next_seq);
      }
    };
    ws.onclose = () => {
      usingWs = false;
      startPoll();
    };
    ws.onerror = () => {
      try {
        ws.close();
      } catch (_) {}
    };

    window.__cultConsoleWs = ws;
  }

  async function sendLine() {
    const line = (input.value || "").trim();
    if (!line) return;
    const flash = document.getElementById("flash");
    const ws = window.__cultConsoleWs;
    if (usingWs && ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "command", command: line }));
      input.value = "";
      return;
    }
    try {
      await api(`/v1/servers/${window.SERVER_ID}/console`, {
        method: "POST",
        body: JSON.stringify({ command: line }),
      });
      input.value = "";
      await pollOnce();
    } catch (e) {
      toast(flash, e.message || String(e), false);
    }
  }

  if (send) send.addEventListener("click", sendLine);
  if (input) input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendLine();
  });

  connectWs();
})();
