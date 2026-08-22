(function () {
  const steps = document.getElementById("wizardSteps");
  const form = document.getElementById("createServerForm");
  if (!form || !steps) return;

  let step = 1;
  const max = 3;

  function show(n) {
    step = Math.max(1, Math.min(max, n));
    form.querySelectorAll("[data-pane]").forEach((pane) => {
      const id = Number(pane.getAttribute("data-pane"));
      const on = id === step;
      pane.hidden = !on;
      pane.classList.toggle("active", on);
    });
    steps.querySelectorAll("li").forEach((li) => {
      const id = Number(li.getAttribute("data-step"));
      li.classList.toggle("active", id === step);
      li.classList.toggle("done", id < step);
    });
  }

  form.querySelectorAll("[data-wizard-next]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (step === 1) {
        const name = form.querySelector('[name="name"]');
        if (!name || !String(name.value || "").trim()) {
          name && name.focus();
          return;
        }
      }
      show(step + 1);
    });
  });
  form.querySelectorAll("[data-wizard-back]").forEach((btn) => {
    btn.addEventListener("click", () => show(step - 1));
  });

  show(1);
})();
