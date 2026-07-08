(function () {
  const root = document.documentElement;
  const storedTheme = window.localStorage.getItem("tracky-theme");
  const systemDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const initialTheme = storedTheme || (systemDark ? "dark" : "light");
  root.dataset.theme = initialTheme;

  document.addEventListener("click", function (event) {
    const confirmControl = event.target.closest("[data-confirm]");
    if (confirmControl && !window.confirm(confirmControl.dataset.confirm)) {
      event.preventDefault();
      return;
    }

    const button = event.target.closest("[data-theme-toggle]");
    if (button) {
      const nextTheme = root.dataset.theme === "dark" ? "light" : "dark";
      root.dataset.theme = nextTheme;
      window.localStorage.setItem("tracky-theme", nextTheme);
    }

    const correctionButton = event.target.closest("[data-check-correction-toggle]");
    if (correctionButton) {
      const correctionForm = document.querySelector("[data-check-correction]");
      if (correctionForm) {
        correctionForm.classList.add("visible");
        const input = correctionForm.querySelector("input[name='tmdb_url']");
        if (input) {
          input.focus();
        }
      }
    }
  });

  document.addEventListener("submit", function (event) {
    const scoreInput = document.querySelector("[data-check-score]");
    if (!scoreInput) {
      return;
    }
    const target = event.target.querySelector("[data-check-score-target]");
    if (target) {
      target.value = scoreInput.value;
    }
  });
})();
