const menuToggle = document.querySelector(".menu-toggle");
  const menuLinks = document.querySelector("#top-menu-links");

  const desktopMenu = window.matchMedia("(min-width: 1200px)");

  const closeMenu = (restoreFocus = false) => {
    menuToggle.setAttribute("aria-expanded", "false");
    menuToggle.setAttribute("aria-label", "Open navigation menu");
    menuLinks.hidden = !desktopMenu.matches;
    if (restoreFocus) menuToggle.focus();
  };

  menuToggle.addEventListener("click", () => {
    const isExpanded = menuToggle.getAttribute("aria-expanded") === "true";
    menuToggle.setAttribute("aria-expanded", String(!isExpanded));
    menuToggle.setAttribute("aria-label", isExpanded ? "Open navigation menu" : "Close navigation menu");
    menuLinks.hidden = isExpanded;
  });

  menuLinks.addEventListener("click", (event) => {
    if (event.target.closest("a")) closeMenu();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !desktopMenu.matches && menuToggle.getAttribute("aria-expanded") === "true") closeMenu(true);
  });

  const syncMenu = () => {
    const hadFocus = menuLinks.contains(document.activeElement);
    closeMenu(hadFocus && !desktopMenu.matches);
  };
  desktopMenu.addEventListener("change", syncMenu);
  syncMenu();
  document.addEventListener("click", (event) => {
    if (!desktopMenu.matches && !event.target.closest(".top-menu")) {
      closeMenu(menuLinks.contains(document.activeElement));
    }
  });

  const scopeScroll = document.querySelector(".scope-scroll");

  if (scopeScroll) {
    let dragStartX = 0;
    let dragStartScroll = 0;
    let isDragging = false;

    scopeScroll.addEventListener("pointerdown", (event) => {
      if (event.pointerType !== "mouse" || event.button !== 0 || scopeScroll.scrollWidth <= scopeScroll.clientWidth) return;
      isDragging = true;
      dragStartX = event.clientX;
      dragStartScroll = scopeScroll.scrollLeft;
      scopeScroll.classList.add("is-dragging");
      scopeScroll.setPointerCapture(event.pointerId);
    });

    scopeScroll.addEventListener("pointermove", (event) => {
      if (isDragging) {
        scopeScroll.scrollLeft = dragStartScroll - (event.clientX - dragStartX);
      }
    });

    const endScopeDrag = () => {
      isDragging = false;
      scopeScroll.classList.remove("is-dragging");
    };

    scopeScroll.addEventListener("pointerup", endScopeDrag);
    scopeScroll.addEventListener("pointercancel", endScopeDrag);
    scopeScroll.addEventListener("lostpointercapture", endScopeDrag);
  }
