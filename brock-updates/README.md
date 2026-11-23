# Brock University News, Sports & Events Feed Generator

Python replacement for the deprecated dynamic PHP `feed2js` script. This script runs on a scheduled task (cron), aggregates RSS updates from Service Alerts, Microsoft 365 Status, Brock News, Brock Badgers Athletics, and ExperienceBU, sanitizes the payloads, and generates a completely static, accessible HTML widget ready for embedding in Brightspace. Parameters are configured when the script is run server-side, *not* passed through GET requests.

Conventional RSS feed parsers don't quite work out of the box because Anthology/Blackboard Engage events don't include standard author fields in the RSS feed, requiring custom XML preprocessing to extract one or more `<host>` tags. The script also filters out cancelled events and applies date-offset logic so students see upcoming events rather than events already in progress. Additionally, it conditionally renders high-priority outage banners at the top of the widget whenever active service alerts or Microsoft 365 service degradations are detected.

## Feeds Used

1. **EdTech Service Alerts (Brightspace Announcements):** `https://brightspace.brocku.ca/d2l/le/news/rss/249302/course?token=<TOKEN>&ou=249302` *(optional via `--service-alerts`)*
2. **Microsoft 365 Service Status:** `https://status.cloud.microsoft/api/feed/mac` *(optional via `--microsoft-status`)*
3. **Brock News (Brightspace tag):** `https://brocku.ca/brock-news/tag/brightspace/feed/`
4. **Brock Badgers Athletics:** `https://gobadgers.ca/rss?path=`
5. **ExperienceBU Events:** `https://experiencebu.brocku.ca/events.rss`

## Key Features

- **Service Degradation & Status Banners:**
  - **EdTech Service Alerts (`--service-alerts`):** Checks a Brightspace course announcements RSS feed and, if any active announcements exist, renders a **Service Degradation** alert banner at the very top of the widget using the first item in the feed.
  - **Microsoft 365 Status (`--microsoft-status`):** Monitors the Microsoft 365 status RSS feed for `<status>ServiceDegradation</status>` entries and displays a **Microsoft 365 Service Degradation** alert banner above the standard news and event feeds when an active incident is reported.
- **Performance & Cache Optimization:**
  - **Browser Side:** Replaces runtime browser JavaScript execution and cross-site server calls with a single static HTML payload.
  - **Server Side:** Uses an atomic write pattern and strips dynamic generation timestamps when comparing outputs so unchanged feeds do not invalidate upstream caches.
- **Visual Enhancements:** Extracts image links dynamically from normalized `<media:thumbnail>` metadata, `<enclosure>` tags, and inline WordPress HTML content blocks, utilizing a fallback profile pattern when no image exists and inline SVGs for status alerts.
- **Host Tracking:** Handles multi-host configurations by preprocessing the XML stream to capture non-standard repeated `<host>` elements.
- **Security & Data Isolation:** Implements strict input unescaping/re-escaping, URL scheme validation (`http://`/`https://`), CSS `url(...)` character neutralization, and XML entity guards to mitigate Cross-Site Scripting (XSS) and injection risks before rendering HTML.
- **Accessibility (a11y):** Formats links and components into semantic layouts. Decorative/redundant thumbnail links are hidden from keyboard tabs and assistive technologies (`tabindex="-1"`, `aria-hidden="true"`).

## Prerequisites

The script requires **Python 3.9+** due to its native use of the `zoneinfo` module for timezone handling (with fallback support for `backports.zoneinfo` on older Python 3 releases).

Install dependencies via pip:
```bash
pip install -r requirements.txt
```
## Usage
```bash
python generate_feed.py \
  --service-alerts "https://brightspace.brocku.ca/d2l/le/news/rss/249302/course?token=](https://brightspace.brocku.ca/d2l/le/news/rss/249302/course?token=<TOKEN>&ou=249302" \
  --microsoft-status \
  --max-events 5 \
  --max-news 2 \
  --max-sports 1 \
  --output-path ./brock_updates.html
  ```