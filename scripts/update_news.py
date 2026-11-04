#!/usr/bin/env python3
"""Refresh the static news archive from validated official feeds."""

from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "news" / "data.json"
USER_AGENT = "DelRioGlobalStrategies-NewsFeed/1.0 (+https://delrioglobalstrategies.com/)"
MAX_RESPONSE_BYTES = 2_000_000
TIMEOUT_SECONDS = 20
LOG = logging.getLogger("news-updater")

SOURCES = (
    {
        "id": "bea",
        "name": "U.S. Bureau of Economic Analysis",
        "url": "https://apps.bea.gov/rss/rss.xml",
        "article_hosts": {"bea.gov", "www.bea.gov", "apps.bea.gov"},
        "source_url": "https://www.bea.gov/",
        "region": "United States",
        "summary_from_article": False,
        "kind": "rss",
    },
    {
        "id": "ecb",
        "name": "European Central Bank",
        "url": "https://www.ecb.europa.eu/rss/press.xml",
        "article_hosts": {"www.ecb.europa.eu"},
        "source_url": "https://www.ecb.europa.eu/",
        "region": "Europe",
        "summary_from_article": True,
        "kind": "rss",
    },
    {
        "id": "european-commission",
        "name": "European Commission",
        "url": "https://ec.europa.eu/commission/presscorner/api/rss",
        "article_hosts": {"ec.europa.eu"},
        "source_url": "https://commission.europa.eu/",
        "region": "Europe",
        "summary_from_article": False,
        "kind": "rss",
        "required_description_pattern": r"European Commission Press release",
    },
    {
        "id": "federal-register",
        "name": "Federal Register",
        "url": "https://www.federalregister.gov/api/v1/documents.json",
        "article_hosts": {"www.federalregister.gov"},
        "source_url": "https://www.federalregister.gov/",
        "region": "United States",
        "summary_from_article": False,
        "kind": "federal-register",
    },
)

FRESHNESS_HOURS = 12
MAX_AGE_HOURS = 24
MAX_ARTICLE_FETCHES_PER_SOURCE = 20
VALID_REGIONS = {"Puerto Rico", "United States", "Europe", "Global"}

PUERTO_RICO_TERMS = re.compile(
    r"\bpuerto rico\b|\bpuerto rican\b|\bsan juan\b|\bboricua\b",
    re.IGNORECASE,
)
GLOBAL_TERMS = re.compile(
    r"\binternational\b|\bglobal\b|\bforeign\b|\bworld\b|\btrade\b|"
    r"\bmultinational\b|\bcaribbean\b|\blatin america\b|\beurope(?:an)?\b|"
    r"\bchina\b|\bjapan\b|\bindia\b|\bafrica\b|\bmiddle east\b",
    re.IGNORECASE,
)
RELEVANCE_TERMS = re.compile(
    r"\beconom(?:y|ic|ics)\b|\bbusiness\b|\binvest(?:ment|ing|or)?\b|"
    r"\bmarket(?:s)?\b|\btrade\b|\bfinancial\b|\bfinance\b|\bbank(?:ing)?\b|"
    r"\binflation\b|\bemployment\b|\bjobs?\b|\bgdp\b|\bgross domestic product\b|"
    r"\bbudget\b|\btax(?:es|ation)?\b|\bsmall business\b|\bloan(?:s)?\b|"
    r"\bcredit\b|\bcapital\b|\bindustry\b|\binfrastructure\b|\btourism\b|"
    r"\benergy\b|\bPuerto Rico\b|\bmonetary policy\b|\bwages?\b|\bgrowth\b|"
    r"\bprices?\b|\binterest rates?\b|\btourism\b|\bcompetitiveness\b",
    re.IGNORECASE,
)
FEDERAL_REGISTER_RELEVANCE_TERMS = re.compile(
    r"\beconom(?:y|ic|ics)\b|\bbusiness\b|\binvest(?:ment|ing|or)?\b|"
    r"\bfinancial\b|\bfinance\b|\bbank(?:ing)?\b|\binflation\b|\bemployment\b|"
    r"\bjobs?\b|\bgdp\b|\bgross domestic product\b|\bsmall business\b|"
    r"\bloan(?:s)?\b|\bcredit\b|\bcapital\b|\bindustry\b|\binfrastructure\b|"
    r"\btourism\b|\benergy\b|\bmonetary policy\b|\bwages?\b|\bgrowth\b|"
    r"\bprices?\b|\binterest rates?\b|\btrade\b|\bcommercial lending\b|"
    r"\bexports?\b|\bimports?\b|\btariffs?\b|\bcommodit(?:y|ies)\b",
    re.IGNORECASE,
)
FEDERAL_REGISTER_POLICY_TERMS = re.compile(
    r"\b(?:federal|state|territorial|local)\s+budget\b|"
    r"\bbudget\s+(?:deficit|proposal|plan|request|reconciliation)\b|"
    r"\b(?:income|corporate|sales|property|payroll)\s+tax(?:es)?\b|"
    r"\btax\s+(?:policy|credit|rate|bill|reform)\b",
    re.IGNORECASE,
)


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.skip_depth += 1
        elif tag in {"p", "br", "li"} and not self.skip_depth:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.skip_depth:
            self.skip_depth -= 1
        elif tag in {"p", "li"} and not self.skip_depth:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)


def clean_text(value: str, limit: int = 480) -> str:
    parser = TextExtractor()
    parser.feed(value)
    text = html.unescape(" ".join(parser.parts))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"
    return text


def safe_article_url(raw_url: str, allowed_hosts: set[str]) -> str:
    raw_url = raw_url.strip()
    if re.match(r"^(?:www\.)?bea\.gov/", raw_url, re.IGNORECASE):
        raw_url = f"https://{raw_url}"
    elif raw_url.startswith("//"):
        raw_url = f"https:{raw_url}"
    parsed = urllib.parse.urlsplit(raw_url.strip())
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.hostname.lower() not in allowed_hosts
        or not parsed.path
    ):
        raise ValueError(f"Article URL is not on the approved HTTPS host list: {raw_url}")
    return urllib.parse.urlunsplit(("https", parsed.netloc.lower(), parsed.path, parsed.query, ""))


def article_category(headline: str, description: str, source_region: str = "United States") -> str:
    text = f"{headline} {description}"
    if PUERTO_RICO_TERMS.search(text):
        return "Puerto Rico"
    if source_region == "Europe" or GLOBAL_TERMS.search(text):
        return "Global"
    return "United States"


def article_region(headline: str, description: str, source_region: str) -> str:
    text = f"{headline} {description}"
    if PUERTO_RICO_TERMS.search(text):
        return "Puerto Rico"
    if source_region == "Europe":
        return "Europe"
    if GLOBAL_TERMS.search(text):
        return "Global"
    return source_region


def is_relevant(headline: str, description: str) -> bool:
    return bool(RELEVANCE_TERMS.search(f"{headline} {description}"))


def is_federal_register_relevant(headline: str, description: str) -> bool:
    if FEDERAL_REGISTER_RELEVANCE_TERMS.search(headline) or FEDERAL_REGISTER_POLICY_TERMS.search(headline):
        return True
    description_terms = set(FEDERAL_REGISTER_RELEVANCE_TERMS.findall(description))
    return len(description_terms) >= 2


def make_article(
    *,
    source: dict[str, Any],
    headline: str,
    description: str,
    url: str,
    published: datetime,
    date_precision: str,
    region: str,
) -> dict[str, str] | None:
    clean_headline = clean_text(headline, 240)
    clean_description = clean_text(description)
    if (
        not clean_headline
        or not clean_description
        or clean_headline.casefold() == clean_description.casefold()
        or not is_relevant(clean_headline, clean_description)
    ):
        return None

    published_utc = published.astimezone(timezone.utc)
    url = url.strip()
    if re.match(r"^(?:www\.)?bea\.gov/", url, re.IGNORECASE):
        url = f"https://{url}"
    else:
        url = urllib.parse.urljoin(source["source_url"], url)
    article_url = safe_article_url(url, source["article_hosts"])
    identifier = hashlib.sha256(article_url.encode("utf-8")).hexdigest()
    return {
        "id": identifier,
        "headline": clean_headline,
        "description": clean_description,
        "source": source["name"],
        "sourceUrl": source["source_url"],
        "category": article_category(clean_headline, clean_description, source["region"]),
        "region": region,
        "publishedAt": published_utc.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "datePrecision": date_precision,
        "url": article_url,
    }


class ArticleParagraphParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[str] = []
        self.current: list[str] | None = None
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip_depth += 1
        elif tag == "p" and not self.skip_depth:
            self.current = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.skip_depth:
            self.skip_depth -= 1
        elif tag == "p" and self.current is not None:
            text = clean_text(" ".join(self.current), 480)
            if text:
                self.paragraphs.append(text)
            self.current = None

    def handle_data(self, data: str) -> None:
        if self.current is not None and not self.skip_depth:
            self.current.append(data)


def fetch_article_description(url: str, source: dict[str, Any]) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        final_url = urllib.parse.urlsplit(response.geturl())
        if final_url.scheme != "https" or final_url.hostname not in source["article_hosts"]:
            raise ValueError("Article redirected outside its verified HTTPS origin")
        if response.headers.get_content_type() != "text/html":
            raise ValueError("Article URL did not return HTML")
        payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError("Article response exceeded the size limit")

    parser = ArticleParagraphParser()
    parser.feed(payload.decode("utf-8", errors="replace"))
    relevant = [
        paragraph
        for paragraph in parser.paragraphs
        if len(paragraph) >= 55 and is_relevant("", paragraph)
    ]
    if relevant:
        return max(
            relevant,
            key=lambda paragraph: (
                len(RELEVANCE_TERMS.findall(paragraph)),
                min(len(paragraph), 480),
            ),
        )
    raise ValueError("No relevant source-provided article summary was available")


def parse_rss(xml_content: bytes, source: dict[str, Any], now: datetime) -> list[dict[str, str]]:
    root = ET.fromstring(xml_content)
    if root.tag.rsplit("}", 1)[-1].lower() not in {"rss", "feed"}:
        raise ValueError("Feed response was not RSS or Atom XML")

    articles: list[dict[str, str]] = []
    item_tag = "entry" if root.tag.rsplit("}", 1)[-1].lower() == "feed" else "item"
    article_fetches = 0
    for item in root.iter():
        if item.tag.rsplit("}", 1)[-1].lower() != item_tag:
            continue
        fields: dict[str, str] = {}
        for child in list(item):
            key = child.tag.rsplit("}", 1)[-1].lower()
            value = (child.text or "").strip()
            if key == "link" and not value:
                attributes = dict(child.attrib)
                value = attributes.get("href", "")
            fields[key] = value
        raw_date = fields.get("pubdate") or fields.get("published") or fields.get("updated")
        try:
            published = parsedate_to_datetime(raw_date)
        except (TypeError, ValueError, OverflowError) as error:
            LOG.warning("Skipping feed item with invalid publication date: %s", error)
            continue
        if published.tzinfo is None:
            LOG.warning("Skipping feed item with timezone-free publication date")
            continue
        if published > now + timedelta(minutes=5):
            LOG.warning("Skipping feed item with future publication date: %s", raw_date)
            continue
        if now - published > timedelta(hours=MAX_AGE_HOURS):
            continue

        link = fields.get("link")
        if not link:
            continue
        if re.match(r"^(?:www\.)?bea\.gov/", link, re.IGNORECASE):
            link = f"https://{link}"
        else:
            link = urllib.parse.urljoin(source["source_url"], link)
        description = fields.get("description") or fields.get("summary") or fields.get("content", "")
        required_pattern = source.get("required_description_pattern")
        if required_pattern and not re.search(required_pattern, description, re.IGNORECASE):
            continue
        try:
            article_url = safe_article_url(link, source["article_hosts"])
        except ValueError as error:
            LOG.warning("Skipping invalid feed item: %s", error)
            continue
        if not description and source["summary_from_article"]:
            if article_fetches >= MAX_ARTICLE_FETCHES_PER_SOURCE:
                continue
            article_fetches += 1
            try:
                description = fetch_article_description(article_url, source)
            except (OSError, urllib.error.URLError, ValueError) as error:
                LOG.warning("Skipping article without a verified summary: %s (%s)", article_url, error)
                continue

        region = article_region(fields.get("title", ""), description, source["region"])
        try:
            article = make_article(
                source=source,
                headline=fields.get("title", ""),
                description=description,
                url=article_url,
                published=published,
                date_precision="timestamp",
                region=region,
            )
        except ValueError as error:
            LOG.warning("Skipping invalid feed item: %s", error)
            continue
        if article:
            articles.append(article)
    return articles


def fetch_source(source: dict[str, Any], now: datetime) -> list[dict[str, str]]:
    if source["kind"] == "federal-register":
        return fetch_federal_register(source, now)
    request = urllib.request.Request(
        source["url"],
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        final_url = urllib.parse.urlsplit(response.geturl())
        if final_url.scheme != "https" or final_url.hostname != urllib.parse.urlsplit(source["url"]).hostname:
            raise ValueError("Feed redirected outside its verified HTTPS origin")
        content_type = response.headers.get_content_type()
        if content_type not in {"application/rss+xml", "application/atom+xml", "application/xml", "text/xml"}:
            raise ValueError(f"Unexpected feed content type: {content_type}")
        payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError("Feed response exceeded the size limit")
    return parse_rss(payload, source, now)


def fetch_federal_register(source: dict[str, Any], now: datetime) -> list[dict[str, str]]:
    today_pr = now.astimezone(ZoneInfo("America/Puerto_Rico")).date().isoformat()
    query = urllib.parse.urlencode(
        [
            ("per_page", "100"),
            ("order", "newest"),
            ("conditions[publication_date][gte]", today_pr),
            ("fields[]", "title"),
            ("fields[]", "abstract"),
            ("fields[]", "publication_date"),
            ("fields[]", "html_url"),
        ]
    )
    request = urllib.request.Request(
        f"{source['url']}?{query}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        final_url = urllib.parse.urlsplit(response.geturl())
        if final_url.scheme != "https" or final_url.hostname != "www.federalregister.gov":
            raise ValueError("Federal Register API redirected outside its verified HTTPS origin")
        if response.headers.get_content_type() != "application/json":
            raise ValueError("Federal Register API returned an unexpected content type")
        payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError("Federal Register API response exceeded the size limit")
    result = json.loads(payload)
    if not isinstance(result, dict) or not isinstance(result.get("results"), list):
        raise ValueError("Federal Register API response has an invalid format")

    articles = []
    for item in result["results"]:
        if not isinstance(item, dict):
            continue
        try:
            title = item.get("title") or ""
            abstract = item.get("abstract") or ""
            if not is_federal_register_relevant(title, abstract):
                continue
            publication_date = datetime.strptime(item["publication_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            article = make_article(
                source=source,
                headline=title,
                description=abstract,
                url=item.get("html_url") or "",
                published=publication_date,
                date_precision="day",
                region=article_region(title, abstract, source["region"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            LOG.warning("Skipping invalid Federal Register result: %s", error)
            continue
        if article:
            articles.append(article)
    return articles


def article_datetime(article: dict[str, Any]) -> datetime:
    published = datetime.fromisoformat(article["publishedAt"].replace("Z", "+00:00"))
    if published.tzinfo is None:
        raise ValueError("Archived article publication time has no timezone")
    return published.astimezone(timezone.utc)


def valid_archived_article(article: Any) -> bool:
    if not isinstance(article, dict):
        return False
    required_strings = (
        "id", "headline", "description", "source", "sourceUrl",
        "category", "publishedAt", "datePrecision", "url",
    )
    if any(not isinstance(article.get(key), str) or not article[key] for key in required_strings):
        return False
    if article["category"] not in {"Puerto Rico", "United States", "Global"}:
        return False
    if article["datePrecision"] not in {"timestamp", "day"}:
        return False
    if article.get("region", article["category"]) not in VALID_REGIONS:
        return False
    try:
        article_datetime(article)
        approved_hosts = {
            host
            for source in SOURCES
            for host in source["article_hosts"]
        }
        source_hosts = {urllib.parse.urlsplit(source["source_url"]).hostname for source in SOURCES}
        return (
            safe_article_url(article["url"], approved_hosts) == article["url"]
            and safe_article_url(article["sourceUrl"], source_hosts) == article["sourceUrl"]
        )
    except (ValueError, TypeError):
        return False


def load_archive(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"updatedAt": None, "articles": []}
    try:
        feed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read existing news archive at {path}: {error}") from error
    if (
        not isinstance(feed, dict)
        or not isinstance(feed.get("articles"), list)
        or not all(valid_archived_article(article) for article in feed["articles"])
    ):
        raise ValueError(f"Existing news archive has an invalid format: {path}")
    return feed


def merge_articles(existing: list[dict[str, Any]], incoming: list[dict[str, str]]) -> list[dict[str, Any]]:
    by_url: dict[str, dict[str, Any]] = {}
    for article in [*existing, *incoming]:
        if not valid_archived_article(article):
            raise ValueError("Refusing to store an article with invalid metadata")
        if article["source"] == "Federal Register" and not is_federal_register_relevant(
            article["headline"],
            article["description"],
        ):
            continue
        normalized = dict(article)
        normalized.setdefault(
            "region",
            "Puerto Rico" if normalized["category"] == "Puerto Rico" else (
                "Global" if normalized["category"] == "Global" else "United States"
            ),
        )
        normalized["category"] = article_category(
            article["headline"],
            article["description"],
            normalized["region"],
        )
        by_url[article["url"]] = normalized
    return sorted(
        by_url.values(),
        key=lambda article: (article_datetime(article), article["headline"].casefold()),
        reverse=True,
    )


def select_homepage_articles(
    articles: list[dict[str, Any]],
    previous_ids: list[str],
    now: datetime,
) -> list[str]:
    candidates = []
    for article in articles:
        age = now.astimezone(timezone.utc) - article_datetime(article)
        if article.get("datePrecision") == "day":
            publication_day = article["publishedAt"][:10]
            local_today = now.astimezone(ZoneInfo("America/Puerto_Rico")).date().isoformat()
            eligible = publication_day == local_today
        else:
            eligible = timedelta(0) <= age <= timedelta(hours=MAX_AGE_HOURS)
        if eligible:
            candidates.append(article)

    previous = set(previous_ids)
    candidates.sort(
        key=lambda article: (
            article.get("datePrecision") == "day"
            or article_datetime(article) < now.astimezone(timezone.utc) - timedelta(hours=FRESHNESS_HOURS),
            article["id"] in previous,
            -article_datetime(article).timestamp(),
        )
    )

    selected: list[dict[str, Any]] = []
    seen_regions: set[str] = set()
    seen_headlines: set[str] = set()
    seen_sources: set[str] = set()
    for article in candidates:
        region = article.get("region", article["category"])
        headline = re.sub(r"[^a-z0-9]+", " ", article["headline"].casefold()).strip()
        if region in seen_regions or headline in seen_headlines:
            continue
        selected.append(article)
        seen_regions.add(region)
        seen_headlines.add(headline)
        seen_sources.add(article["source"])
        if len(selected) == 3:
            return [article["id"] for article in selected]

    for article in candidates:
        headline = re.sub(r"[^a-z0-9]+", " ", article["headline"].casefold()).strip()
        if (
            article not in selected
            and headline not in seen_headlines
            and article["source"] not in seen_sources
        ):
            selected.append(article)
            seen_headlines.add(headline)
            seen_sources.add(article["source"])
        if len(selected) == 3:
            break
    for article in candidates:
        if article not in selected:
            selected.append(article)
        if len(selected) == 3:
            break
    return [article["id"] for article in selected]


def write_archive(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(prefix=".news-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temporary_file:
            json.dump(payload, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
        raise


def refresh_archive(
    path: Path = DATA_PATH,
    now: datetime | None = None,
    fetcher: Any = fetch_source,
) -> int:
    current_time = now or datetime.now(timezone.utc)
    archive = load_archive(path)
    previous_ids = archive.get("featuredIds", [])
    if not isinstance(previous_ids, list) or not all(isinstance(item, str) for item in previous_ids):
        previous_ids = []
    new_articles: list[dict[str, str]] = []
    successful_sources = 0
    failures: list[str] = []
    source_results: list[dict[str, Any]] = []

    for source in SOURCES:
        try:
            items = fetcher(source, current_time)
            if not isinstance(items, list) or not all(valid_archived_article(item) for item in items):
                raise ValueError("Source parser returned invalid article data")
            new_articles.extend(items)
            successful_sources += 1
            source_results.append({"source": source["id"], "status": "success", "items": len(items)})
            LOG.info("%s: %d eligible items", source["name"], len(items))
        except (OSError, urllib.error.URLError, ET.ParseError, ValueError) as error:
            failures.append(f"{source['name']}: {error}")
            source_results.append({"source": source["id"], "status": "failed", "error": str(error)})
            LOG.warning("%s: %s", source["name"], error)

    if successful_sources == 0:
        raise RuntimeError("News update failed; the last successful archive was left unchanged. " + "; ".join(failures))
    if failures:
        for failure in failures:
            print(f"::warning::{failure}", file=sys.stderr)

    merged = merge_articles(archive["articles"], new_articles)
    featured_ids = select_homepage_articles(merged, previous_ids, current_time)
    if not featured_ids:
        featured_ids = previous_ids or [article["id"] for article in merged[:3]]
        LOG.warning("No source articles were published within 24 hours; retaining the previous homepage selection.")

    completed_at = datetime.now(timezone.utc) if now is None else current_time
    completed_text = completed_at.isoformat(timespec="seconds").replace("+00:00", "Z")
    write_archive(path, {
        "updatedAt": completed_text,
        "featuredIds": featured_ids,
        "lastRun": {
            "startedAt": current_time.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "completedAt": completed_text,
            "successfulSources": successful_sources,
            "sourceResults": source_results,
            "freshArticles": len(new_articles),
        },
        "articles": merged,
    })
    LOG.info("Completed update at %s; saved %d articles (%d current feed items).", completed_text, len(merged), len(new_articles))
    return len(merged)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    started_at = datetime.now(timezone.utc)
    LOG.info("News update started at %s.", started_at.isoformat(timespec="seconds").replace("+00:00", "Z"))
    try:
        refresh_archive()
    except Exception:
        LOG.exception("News archive update failed")
        print("::error::News archive update failed; the prior successful archive was retained.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
