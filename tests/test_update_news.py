import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.update_news import (
    SOURCES,
    is_federal_register_relevant,
    merge_articles,
    parse_rss,
    refresh_archive,
    select_homepage_articles,
)


class UpdateNewsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc)
        self.source = SOURCES[0]

    def test_rss_parser_keeps_verified_relevant_metadata(self):
        payload = b"""<?xml version="1.0"?>
        <rss version="2.0"><channel><item>
          <title>U.S. GDP estimate shows economic growth</title>
          <link>https://www.bea.gov/news/2026/example</link>
          <pubDate>Wed, 04 Nov 2026 08:30:00 GMT</pubDate>
          <description><![CDATA[<p>Real gross domestic product increased, according to BEA.</p>]]></description>
        </item><item>
          <title>Financial outlook</title><link>https://example.com/story</link>
          <pubDate>Wed, 04 Nov 2026 08:30:00 GMT</pubDate>
          <description>Banking and financial market release.</description>
        </item></channel></rss>"""

        articles = parse_rss(payload, self.source, self.now)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["category"], "United States")
        self.assertEqual(articles[0]["publishedAt"], "2026-11-04T08:30:00Z")
        self.assertEqual(articles[0]["description"], "Real gross domestic product increased, according to BEA.")

    def test_merge_deduplicates_by_article_url_and_sorts_by_date(self):
        article = parse_rss(b"""<rss><channel><item>
          <title>GDP and economic growth</title>
          <link>https://www.bea.gov/news/2026/example</link>
          <pubDate>Wed, 04 Nov 2026 08:30:00 GMT</pubDate>
          <description>GDP increased in the quarter, according to BEA.</description>
        </item></channel></rss>""", self.source, self.now)[0]

        merged = merge_articles([article], [article])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["url"], article["url"])

    def test_parser_normalizes_bare_official_hosts_and_keeps_us_category(self):
        payload = b"""<rss><channel><item>
          <title>GDP quarterly update</title>
          <link>www.bea.gov/news/2026/gdp-update</link>
          <pubDate>Wed, 04 Nov 2026 08:30:00 GMT</pubDate>
          <description>U.S. gross domestic product grew; exports also rose.</description>
        </item></channel></rss>"""

        articles = parse_rss(payload, self.source, self.now)

        self.assertEqual(articles[0]["url"], "https://www.bea.gov/news/2026/gdp-update")
        self.assertEqual(articles[0]["category"], "United States")

    def test_european_commission_feed_adds_cited_european_articles(self):
        source = next(source for source in SOURCES if source["id"] == "european-commission")
        payload = b"""<rss><channel><item>
          <title>Commission expands European investment programme</title>
          <link>https://ec.europa.eu/commission/presscorner/detail/en/ip_26_1234</link>
          <pubDate>Wed, 04 Nov 2026 09:00:00 GMT</pubDate>
          <description>European Commission Press release The programme supports economic investment and growth.</description>
        </item></channel></rss>"""

        articles = parse_rss(payload, source, self.now)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["source"], "European Commission")
        self.assertEqual(articles[0]["region"], "Europe")
        self.assertEqual(articles[0]["category"], "Global")

    def test_federal_register_relevance_ignores_incidental_omb_mentions(self):
        self.assertFalse(is_federal_register_relevant(
            "Submission for OMB Review; Comment Request",
            "Submitted to the Office of Management and Budget for paperwork review.",
        ))
        self.assertFalse(is_federal_register_relevant(
            "Submission for Office of Management and Budget Review; Voluntary Acknowledgment of Paternity",
            "Child Support Enforcement requested an extension for a paternity data collection.",
        ))
        self.assertFalse(is_federal_register_relevant(
            "Privacy Act of 1974; Systems of Records",
            "FERC will rescind its Temporary Work-at-Home Program system of records notice.",
        ))
        self.assertTrue(is_federal_register_relevant(
            "Member Business Loans; Commercial Lending",
            "Amends regulations governing credit union business loans and commercial lending.",
        ))

    def test_failed_all_sources_preserves_last_successful_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            existing = {"updatedAt": "2026-11-03T10:00:00Z", "articles": []}
            original = json.dumps(existing).encode()
            path.write_bytes(original)

            def unavailable(_source, _now):
                raise OSError("source unavailable")

            with self.assertRaises(RuntimeError):
                refresh_archive(path=path, now=self.now, fetcher=unavailable)

            self.assertEqual(path.read_bytes(), original)

    def test_successful_empty_poll_keeps_previous_articles(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            article = parse_rss(b"""<rss><channel><item>
              <title>GDP and economic growth</title>
              <link>https://www.bea.gov/news/2026/example</link>
              <pubDate>Wed, 04 Nov 2026 08:30:00 GMT</pubDate>
              <description>GDP increased in the quarter, according to BEA.</description>
            </item></channel></rss>""", self.source, self.now)[0]
            path.write_text(json.dumps({"updatedAt": None, "articles": [article]}), encoding="utf-8")

            refresh_archive(path=path, now=self.now, fetcher=lambda _source, _now: [])

            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["articles"], [article])

    def test_featured_selection_prioritizes_12_hours_and_diversifies_regions(self):
        articles = [
            self._article("pr-new", "Puerto Rico", self.now - timedelta(minutes=20)),
            self._article("us-new", "United States", self.now - timedelta(hours=2)),
            self._article("eu-new", "Europe", self.now - timedelta(hours=8)),
            self._article("global-older", "Global", self.now - timedelta(hours=13)),
            self._article("us-older", "United States", self.now - timedelta(hours=18)),
        ]

        selected = select_homepage_articles(articles, [], self.now)
        selected_articles = [article for article in articles if article["id"] in selected]

        self.assertEqual(len(selected), 3)
        self.assertEqual({article["region"] for article in selected_articles}, {"Puerto Rico", "United States", "Europe"})
        self.assertNotIn("global-older", selected)

    def test_twice_daily_refresh_keeps_distinct_recent_regional_cards(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            for hour, suffix in ((10, "morning"), (22, "evening")):
                run_time = self.now.replace(hour=hour)
                articles = [
                    self._article(f"pr-{suffix}", "Puerto Rico", run_time - timedelta(minutes=15)),
                    self._article(f"us-{suffix}", "United States", run_time - timedelta(hours=2)),
                    self._article(f"eu-{suffix}", "Europe", run_time - timedelta(hours=7)),
                ]

                def fetcher(source, _now):
                    return articles if source["id"] == "bea" else []

                refresh_archive(path=path, now=run_time, fetcher=fetcher)
                feed = json.loads(path.read_text(encoding="utf-8"))
                by_id = {article["id"]: article for article in feed["articles"]}
                featured = [by_id[article_id] for article_id in feed["featuredIds"]]

                self.assertEqual(len(featured), 3)
                self.assertEqual(
                    {article["region"] for article in featured},
                    {"Puerto Rico", "United States", "Europe"},
                )
                self.assertEqual(feed["lastRun"]["startedAt"], run_time.isoformat().replace("+00:00", "Z"))

    def test_featured_fallback_uses_new_sources_before_repeating_one_source(self):
        articles = [
            self._article("eu-ecb", "Europe", self.now - timedelta(hours=1)),
            self._article("us-fr", "United States", self.now - timedelta(hours=2)),
            self._article("eu-commission", "Europe", self.now - timedelta(hours=3)),
        ]
        articles[0]["source"] = "European Central Bank"
        articles[1]["source"] = "Federal Register"
        articles[2]["source"] = "European Commission"

        selected = select_homepage_articles(articles, [], self.now)

        self.assertEqual(len(selected), 3)
        self.assertEqual(
            {article["source"] for article in articles if article["id"] in selected},
            {"European Central Bank", "Federal Register", "European Commission"},
        )

    def _article(self, article_id, region, published):
        category = "Puerto Rico" if region == "Puerto Rico" else (
            "United States" if region == "United States" else "Global"
        )
        return {
            "id": article_id,
            "headline": f"{region} economic update",
            "description": f"Verified economic investment news for {region}.",
            "source": "U.S. Bureau of Economic Analysis",
            "sourceUrl": "https://www.bea.gov/",
            "category": category,
            "region": region,
            "publishedAt": published.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "datePrecision": "timestamp",
            "url": f"https://www.bea.gov/news/2026/{article_id}",
        }


if __name__ == "__main__":
    unittest.main()
