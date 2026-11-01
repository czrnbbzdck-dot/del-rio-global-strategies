const menuToggle = document.querySelector(".menu-toggle");
const primaryNavigation = document.querySelector("#primary-navigation");

const setMenuOpen = (isOpen, restoreFocus = false) => {
  menuToggle.setAttribute("aria-expanded", String(isOpen));
  primaryNavigation.classList.toggle("is-open", isOpen);
  if (restoreFocus) menuToggle.focus();
};

menuToggle.addEventListener("click", () => {
  setMenuOpen(menuToggle.getAttribute("aria-expanded") !== "true");
});

primaryNavigation.addEventListener("click", (event) => {
  if (event.target.closest("a")) setMenuOpen(false);
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && menuToggle.getAttribute("aria-expanded") === "true") {
    setMenuOpen(false, true);
  }
});

document.addEventListener("click", (event) => {
  if (!event.target.closest(".site-header") && menuToggle.getAttribute("aria-expanded") === "true") {
    setMenuOpen(false, primaryNavigation.contains(document.activeElement));
  }
});
