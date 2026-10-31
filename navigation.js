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

const filterButtons = [...document.querySelectorAll(".filter-button")];
const researchSearch = document.querySelector("#research-search");
const outlookCards = [...document.querySelectorAll(".outlook-card")];
const researchResults = document.querySelector("#research-results");
let activeSector = "all";

const filterPublications = () => {
  const query = researchSearch.value.trim().toLocaleLowerCase();
  let visibleCount = 0;

  for (const card of outlookCards) {
    const matchesSector = activeSector === "all" || card.dataset.sector === activeSector;
    const matchesSearch = !query || card.textContent.toLocaleLowerCase().includes(query);
    card.hidden = !matchesSector || !matchesSearch;
    if (!card.hidden) visibleCount += 1;
  }

  researchResults.textContent = visibleCount === 1
    ? "Showing 1 publication."
    : `Showing ${visibleCount} publications.`;
};

for (const button of filterButtons) {
  button.addEventListener("click", () => {
    activeSector = button.dataset.sector;
    for (const filterButton of filterButtons) {
      const isActive = filterButton === button;
      filterButton.classList.toggle("is-active", isActive);
      filterButton.setAttribute("aria-pressed", String(isActive));
    }
    filterPublications();
  });
}

researchSearch.addEventListener("input", filterPublications);

for (const openButton of document.querySelectorAll("[data-dialog-target]")) {
  const dialog = document.getElementById(openButton.dataset.dialogTarget);
  const closeButton = dialog.querySelector("[data-dialog-close]");

  openButton.addEventListener("click", () => dialog.showModal());
  closeButton.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
}
