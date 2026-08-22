(function () {
  const root = document.getElementById("filesRoot");
  if (!root || !window.SERVER_ID) return;
  const { api, toast } = window.CultPanel || window.CultAgent;
  const flash = document.getElementById("flash");
  let current = ".";

  async function load(path) {
    current = path || ".";
    document.getElementById("filesPath").textContent = current;
    try {
      const res = await api(`/v1/servers/${window.SERVER_ID}/files?path=${encodeURIComponent(current)}`);
      const items = res.items || [];
      root.innerHTML = "";
      if (current !== "." && current !== "") {
        const up = document.createElement("div");
        up.className = "file-row";
        const parent = current.split("/").slice(0, -1).join("/") || ".";
        up.innerHTML = `<a href="#" data-path="${parent}">../</a><span class="muted">dir</span>`;
        root.appendChild(up);
      }
      if (!items.length) {
        root.innerHTML += `<div class="empty">Empty directory</div>`;
      }
      for (const item of items) {
        const row = document.createElement("div");
        row.className = "file-row";
        if (item.is_dir) {
          row.innerHTML = `<a href="#" data-path="${item.path}">${item.name}/</a><span class="muted">dir</span>`;
        } else {
          row.innerHTML = `<a href="#" data-file="${item.path}">${item.name}</a><span class="muted">${item.size ?? ""}</span>`;
        }
        root.appendChild(row);
      }
      root.querySelectorAll("[data-path]").forEach((a) => {
        a.addEventListener("click", (e) => {
          e.preventDefault();
          load(a.getAttribute("data-path"));
        });
      });
      root.querySelectorAll("[data-file]").forEach((a) => {
        a.addEventListener("click", async (e) => {
          e.preventDefault();
          const p = a.getAttribute("data-file");
          try {
            const res = await api(`/v1/servers/${window.SERVER_ID}/files/content?path=${encodeURIComponent(p)}`);
            document.getElementById("fileEditorPath").value = p;
            document.getElementById("fileEditor").value = res.content || "";
            document.getElementById("fileEditorCard").hidden = false;
          } catch (err) {
            toast(flash, err.message || String(err), false);
          }
        });
      });
    } catch (e) {
      toast(flash, e.message || String(e), false);
    }
  }

  const saveBtn = document.getElementById("fileSave");
  if (saveBtn) {
    saveBtn.addEventListener("click", async () => {
      const path = document.getElementById("fileEditorPath").value;
      const content = document.getElementById("fileEditor").value;
      try {
        await api(`/v1/servers/${window.SERVER_ID}/files/content`, {
          method: "PUT",
          body: JSON.stringify({ path, content }),
        });
        toast(flash, "Saved " + path, true);
      } catch (e) {
        toast(flash, e.message || String(e), false);
      }
    });
  }

  load(".");
})();
