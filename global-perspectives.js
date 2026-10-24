const perspectivesSection = document.querySelector("#global-perspectives");
const perspectivesList = document.querySelector("#perspectives-items");

const formatPublicationDate = (date) => new Intl.DateTimeFormat("en-US", {
  month: "long",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
}).format(new Date(`${date}T00:00:00Z`));

const isPerspective = (item) => {
  if (
    !item
    || typeof item.institution !== "string"
    || typeof item.headline !== "string"
    || typeof item.description !== "string"
    || typeof item.date !== "string"
    || !/^\d{4}-\d{2}-\d{2}$/.test(item.date)
    || typeof item.url !== "string"
  ) {
    return false;
  }

  const articleUrl = new URL(item.url);
  const publicationDate = new Date(`${item.date}T00:00:00Z`);
  return articleUrl.protocol === "https:"
    && Number.isFinite(publicationDate.getTime())
    && publicationDate.toISOString().startsWith(item.date);
};

const createPerspectiveItem = (item) => {
  const listItem = document.createElement("li");
  listItem.className = "perspective-item";

  const article = document.createElement("article");
  const metadata = document.createElement("div");
  metadata.className = "perspective-meta";

  const institution = document.createElement("span");
  institution.textContent = item.institution;

  const date = document.createElement("time");
  date.dateTime = item.date;
  date.textContent = formatPublicationDate(item.date);

  const headline = document.createElement("h3");
  headline.textContent = item.headline;

  const description = document.createElement("p");
  description.textContent = item.description;

  const link = document.createElement("a");
  link.className = "perspective-link";
  link.href = item.url;
  link.textContent = "Read original";
  link.setAttribute("aria-label", `Read original article: ${item.headline}`);

  metadata.append(institution, date);
  article.append(metadata, headline, description, link);
  listItem.append(article);
  return listItem;
};

const loadPerspectives = async () => {
  try {
    const response = await fetch("./global-perspectives.json");
    if (!response.ok) return;

    const items = await response.json();
    if (
      !Array.isArray(items)
      || items.length === 0
      || items.length > 6
      || !items.every(isPerspective)
    ) {
      return;
    }

    perspectivesList.append(...items.map(createPerspectiveItem));
    perspectivesSection.hidden = false;
  } catch {
    perspectivesSection.hidden = true;
  }
};

loadPerspectives();
