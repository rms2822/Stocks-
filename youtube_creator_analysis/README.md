# YouTube Creator Title Performance Analysis

Scrapes real, published-view data for 25 top English-language YouTube creators, keeps
only videos with 1,000,000+ views, and analyzes which title patterns line up with
stronger performance. Results are explorable in `dashboard.html`.

## Scope & exclusions

25 channels across tech, science, finance, vlogging, cooking, DIY, fitness, cars,
travel, and comedy/entertainment (see `channels.py`). Excluded per constraints:
non-English channels, music channels, predominantly-gaming channels, large media
companies (Netflix/BBC-style), and kids' content.

## Pipeline

1. `scrape.py` — pulls each channel's subscriber count and up to 350 recent uploads
   (title, view count, duration) directly from YouTube via `yt-dlp` (no API key
   required). Writes `data/raw_data.json`.
2. `build_dataset.py` — filters to videos with >=1,000,000 views, keeps the top 25
   per channel by view count, and writes the clean `data/dataset.json` used by the
   dashboard.
3. `analyze.py` — computes title-pattern statistics (word frequency, title-length
   buckets, feature lift for things like "has a number", "has exclamation mark",
   etc.) into `data/analysis.json`. The dashboard recomputes these live in-browser
   too, so every chart updates when you apply filters.
4. `inject_data.py` — embeds `data/dataset.json` and `data/analysis.json` into
   `dashboard_template.html` to produce the final self-contained `dashboard.html`
   (no server or build step needed to view it — open the file directly).

Re-run the whole pipeline with:

```bash
pip install yt-dlp
python3 scrape.py
python3 build_dataset.py
python3 analyze.py
python3 inject_data.py
```

## Dashboard

Open `dashboard.html` in a browser. It includes:

- Category / channel / title-keyword / min-views filters that scope every chart and table
- Average views by category
- Title-feature impact (numbers, $ amounts, questions, exclamation marks, superlatives, etc.) vs. baseline
- Title length (word count / character count) vs. average views
- Clickable word list of common title words with their average views
- Sortable channel comparison table
- Sortable, searchable video explorer table linking to the original YouTube videos

## Data notes

- 620 qualifying videos (1M+ views) across 25 channels, scraped directly from public
  YouTube channel pages — no Apify credentials were available in this environment, so
  `yt-dlp` was used to pull the same public metadata (title, view count, duration,
  subscriber count) that a YouTube-scraping Apify actor would return.
- View counts reflect the scrape date and will drift from live YouTube.
- Only a channel's ~350 most recent uploads are scanned, so an older viral outlier
  could be missed on very long-running channels.
