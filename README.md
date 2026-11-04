# del-rio-global-strategies
Del Rio Global Strategies | Puerto Rico | Americas &amp; Caribbean

## Website

The public website is a static, accessible editorial site in `index.html`, styled by `styles.css`. Its research purchases, custom brief orders, payment processing, and publication downloads are handled by Payhip. The existing `CNAME` publishes the `delrioglobalstrategies.com` domain through the repository's existing hosting configuration; website updates do not require DNS or hosting changes.

For a local preview, serve the repository root with a static HTTP server. The world clocks use the visitor's browser to display local times in San Juan, New York, London, and Panama City.

## Latest News & Insights

The homepage and [`/news/`](news/) read the committed `news/data.json` snapshot and do not make visitor browsers contact third-party sources. The archive is separate from original DRGS research and includes source attribution, publication dates, and links to original articles. The interface displays only source headlines and short source-provided descriptions; it does not republish article bodies, photographs, or source logos.

The daily GitHub Actions workflow runs at `10:00` and `22:00 UTC` (`6:00 AM` and `6:00 PM` in Puerto Rico, UTC−4), including weekends and holidays, and can also be started manually. Sources are the BEA RSS feed (`https://apps.bea.gov/rss/rss.xml`), European Central Bank RSS (`https://www.ecb.europa.eu/rss/press.xml`), European Commission Presscorner RSS (`https://ec.europa.eu/commission/presscorner/api/rss`), and the Federal Register API. The BEA [reuse and linking policy](https://www.bea.gov/about/policies-and-information/linking) allows reuse of public-domain information with attribution; the ECB [copyright notice](https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html) permits accurate reuse with ECB citation; European Commission website content is licensed under [CC BY 4.0 unless otherwise indicated](https://commission.europa.eu/legal-notice_en); Federal Register records are official U.S. government material. Feed items and article URLs are restricted to the verified HTTPS source hosts. Federal Register publication dates are day-precision because its API does not provide publication times.

Homepage selection prioritizes timestamped news from the prior 12 hours, then other source records from the prior 24 hours. It tries to use three different regions (Puerto Rico, United States, Europe, or Global), deduplicates URLs, suppresses previously featured stories where alternatives exist, and preserves the previous selection when no eligible recent article is available. The archive retains prior records and the cards show actual source dates and attribution. BEA and Federal Register results mentioning Puerto Rico may fill the Puerto Rico region; no Puerto Rico government feed with verified reuse terms was found, so no PR-government source is scraped. The Federal Reserve and other inaccessible or unlicensed sources remain disabled.

The updater writes its start/completion timestamps and per-source results to `news/data.json` and the Actions log. A monitor workflow checks for a successful scheduled run three hours after each expected update; failures and overdue scheduled runs create/update a GitHub issue alert, and a later successful refresh closes the alert. GitHub Actions scheduled starts can still be delayed; the monitor allows a four-hour window, while the actual completion timestamp is available in the workflow run record and summary.
