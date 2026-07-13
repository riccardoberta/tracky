(function () {
  const root = document.documentElement;
  const storedTheme = window.localStorage.getItem("tracky-theme");
  const systemDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const initialTheme = storedTheme || (systemDark ? "dark" : "light");
  root.dataset.theme = initialTheme;
  const mobileMenuQuery = window.matchMedia ? window.matchMedia("(max-width: 980px)") : null;

  function setMenuOpen(sidebar, isOpen) {
    const toggle = sidebar.querySelector("[data-menu-toggle]");
    sidebar.classList.toggle("is-open", isOpen);
    if (toggle) {
      toggle.setAttribute("aria-expanded", String(isOpen));
      toggle.setAttribute("aria-label", isOpen ? "Close menu" : "Open menu");
    }
  }

  function closeMobileMenu() {
    const sidebar = document.querySelector("[data-mobile-menu].is-open");
    if (sidebar) {
      setMenuOpen(sidebar, false);
    }
  }

  document.addEventListener("click", function (event) {
    const confirmControl = event.target.closest("[data-confirm]");
    if (confirmControl && !window.confirm(confirmControl.dataset.confirm)) {
      event.preventDefault();
      return;
    }

    const menuToggle = event.target.closest("[data-menu-toggle]");
    if (menuToggle) {
      const sidebar = menuToggle.closest("[data-mobile-menu]");
      if (sidebar) {
        setMenuOpen(sidebar, !sidebar.classList.contains("is-open"));
      }
      return;
    }

    const button = event.target.closest("[data-theme-toggle]");
    if (button) {
      const nextTheme = root.dataset.theme === "dark" ? "light" : "dark";
      root.dataset.theme = nextTheme;
      window.localStorage.setItem("tracky-theme", nextTheme);
      return;
    }

    if (event.target.closest("[data-mobile-menu] .nav a")) {
      closeMobileMenu();
      return;
    }

    const openMenu = document.querySelector("[data-mobile-menu].is-open");
    if (openMenu && !event.target.closest("[data-mobile-menu]")) {
      closeMobileMenu();
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeMobileMenu();
    }
  });

  if (mobileMenuQuery) {
    mobileMenuQuery.addEventListener("change", function (event) {
      if (!event.matches) {
        closeMobileMenu();
      }
    });
  }
})();
