# Brock University News & Events Feed Generator

Python replacement for the deprecated dynamic PHP `feed2js` script. This script runs on a scheduled task (cron), aggregates RSS updates from both Brock News and ExperienceBU, sanitizes the payloads, and generates a completely static, accessible HTML widget ready for embedding in Brightspace. Parameters are configured when script is run server-side, *not* parameters passed through GET requests.

Conventional RSS feeds parsers don't quite work because Anthology/Blackboard Engage events don't have authors in the RSS feed, so we have to parse the RSS tags to get the information in one or many `<host>` tags. We also omit cancelled events, and a little bit of date logic to make is so that students saw upcoming events only, not events they are currently missing!

The two feeds it makes use of are
1. A custom RSS feed from the Brock News https://brocku.ca/brock-news/tag/brightspace/feed/
2. And one from ExperienceBU https://experiencebu.brocku.ca/events.rss

## Key Features

- **Performance & Efficiency:** 
    - **Browser Side:** Replaces runtime browser JavaScript execution and cross-site server calls with a single static HTML payload.
    - **Server Side:** Replaces PHP script and heavily cached server-side processing with a single static HTML payload that is regularly updated.
- **Visual Enhancements:** Extracts image links dynamically from both standard `<enclosure>` metadata and hidden WordPress inline HTML content blocks, utilizing a fallback profile pattern if no image exists.
- **Host Tracking:** Handles multi-host configurations by preprocessing the XML stream to catch non-standard repeated `<host>` elements.
- **Security & Data Isolation:** Implements rigid input unescaping and re-escaping to mitigate Cross-Site Scripting (XSS) risks natively before rendering text elements.
- **Accessibility (a11y):** Formats links and components into semantic layouts. Secondary elements (like clickable thumbnails) are explicitly hidden from keyboard tabs and assistive technologies (`tabindex="-1"`, `aria-hidden="true"`) to prevent redundancy.

## Prerequisites

The script requires **Python 3.9+** due to its native use of the `zoneinfo` module for precise time tracking. 

Install dependencies via pip:
```bash
pip install -r requirements.txt
