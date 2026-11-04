const feedUrl = new URL("./data.json", document.currentScript.src);
const homeContainer = document.querySelector("[data-news-home]");
const archiveContainer = document.querySelector("[data-news-archive]");
const searchForm = document.querySelector("[data-news-filters]");
const resultsSummary = document.querySelector("[data-news-results]");
let loadedArticles = [];

const validArticle = (article) => {
  if (
    !article
    || typeof article.id !== "string"
    || typeof article.headline !== "string"
    || typeof article.description !== "string"
    || typeof article.source !== "string"
    || typeof article.category !== "string"
    || typeof article.region !== "string"
    || typeof article.publishedAt !== "string"
    || typeof article.url !== "string"
  ) return false;

  try {
    const url = new URL(article.url);
    const date = new Date(article.publishedAt);
    return url.protocol === "https:"
      && [
        "bea.gov",
        "www.bea.gov",
        "apps.bea.gov",
        "www.ecb.europa.eu",
        "ec.europa.eu",
        "www.federalregister.gov",
      ].includes(url.hostname)
      && Number.isFinite(date.getTime())
      && ["Puerto Rico", "United States", "Global"].includes(article.category);
  } catch {
    return false;
  }
};

const formatDate = (article) => {
  const date = new Date(article.publishedAt);
  return new Intl.DateTimeFormat("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
};

const createCard = (article, showRegion = false) => {
  const card = document.createElement("article");
  card.className = "news-card";

  const metadata = document.createElement("p");
  metadata.className = "news-meta";

  const category = document.createElement("span");
  category.className = "news-category";
  category.textContent = showRegion ? (article.region || article.category) : article.category;

  const date = document.createElement("time");
  date.dateTime = article.publishedAt;
  date.textContent = formatDate(article);
  metadata.append(category, date);

  const headline = document.createElement("h3");
  const headlineLink = document.createElement("a");
  headlineLink.href = article.url;
  headlineLink.target = "_blank";
  headlineLink.rel = "noopener noreferrer";
  headlineLink.textContent = article.headline;
  headline.append(headlineLink);

  const source = document.createElement("p");
  source.className = "news-source";
  source.textContent = `Source: ${article.source}`;

  const description = document.createElement("p");
  description.className = "news-description";
  description.textContent = article.description;

  const readLink = document.createElement("a");
  readLink.className = "news-read-link";
  readLink.href = article.url;
  readLink.target = "_blank";
  readLink.rel = "noopener noreferrer";
  readLink.textContent = "Read original article";
  readLink.setAttribute("aria-label", `Read original article: ${article.headline}`);

  card.append(metadata, headline, source, description, readLink);
  return card;
};

const showEmpty = (container, message) => {
  const empty = document.createElement("p");
  empty.className = "news-empty";
  empty.textContent = message;
  container.replaceChildren(empty);
};

const renderHome = (articles) => {
  if (!homeContainer) return;
  if (articles.length === 0) {
    showEmpty(homeContainer, "No verified updates are available yet. Visit the archive for the latest feed status.");
  } else {
    homeContainer.replaceChildren(...articles.slice(0, 3).map((article) => createCard(article, true)));
  }
  homeContainer.setAttribute("aria-busy", "false");
};

const renderArchive = (articles) => {
  if (!archiveContainer) return;
  const search = searchForm.elements.q.value.trim().toLocaleLowerCase();
  const category = searchForm.elements.category.value;
  const matches = articles.filter((article) => {
    const searchable = [
      article.headline,
      article.description,
      article.source,
      article.category,
      article.publishedAt,
      formatDate(article),
    ].join(" ").toLocaleLowerCase();
    return (!search || searchable.includes(search))
      && (!category || article.category === category);
  });

  resultsSummary.textContent = `${matches.length} ${matches.length === 1 ? "article" : "articles"}`;
  if (matches.length === 0) {
    showEmpty(archiveContainer, articles.length === 0
      ? "No verified articles are available yet."
      : "No articles match those filters.");
  } else {
    archiveContainer.replaceChildren(...matches.map(createCard));
  }
  archiveContainer.setAttribute("aria-busy", "false");
};

const loadNews = async () => {
  try {
    const response = await fetch(feedUrl, { cache: "no-cache" });
    if (!response.ok) throw new Error(`News feed returned HTTP ${response.status}`);
    const feed = await response.json();
    if (!feed || !Array.isArray(feed.articles) || !feed.articles.every(validArticle)) {
      throw new Error("News feed has an invalid format");
    }

    const unique = new Map();
    for (const article of feed.articles) {
      if (!unique.has(article.url)) unique.set(article.url, article);
    }
    const allArticles = [...unique.values()].sort((a, b) => (
      Date.parse(b.publishedAt) - Date.parse(a.publishedAt)
    ));
    const featuredIds = Array.isArray(feed.featuredIds) ? feed.featuredIds : [];
    const byId = new Map(allArticles.map((article) => [article.id, article]));
    const featured = featuredIds.map((id) => byId.get(id)).filter(Boolean);
    const articles = featured.length ? featured : allArticles.slice(0, 3);
    loadedArticles = allArticles;
    renderHome(articles);
    renderArchive(allArticles);
  } catch (error) {
    console.error("Unable to load cached news feed:", error);
    if (homeContainer) {
      showEmpty(homeContainer, "News is temporarily unavailable. The rest of the website remains available.");
      homeContainer.setAttribute("aria-busy", "false");
    }
    if (archiveContainer) {
      showEmpty(archiveContainer, "The cached news archive is temporarily unavailable. Please try again later.");
      archiveContainer.setAttribute("aria-busy", "false");
    }
  }
};

if (searchForm) {
  searchForm.addEventListener("input", () => renderArchive(loadedArticles));
  searchForm.addEventListener("change", () => renderArchive(loadedArticles));
}

loadNews();
