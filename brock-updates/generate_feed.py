###########################################################################
# Example use 
# python generate_feed.py --max-events 5 --max-news 2 --output-path ./brock_updates.html
#
# Other flag defaults:
# --news-url https://brocku.ca/brock-news/tag/brightspace/feed/
# --events-url https://experiencebu.brocku.ca/events.rss
# --max-chars 260
# --event-offset 900
###########################################################################

import os
import re
import html
import sys
import argparse
import urllib.request
import feedparser
from datetime import datetime, timezone, timedelta
from dateutil import parser
try:
    # Native in Python 3.9+
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
    try:
        # Backport for Python 3.7 / 3.8 / 3.6
        from backports.zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    except ImportError:
        # Extreme fallback if compilation fails or package isn't recognized
        print("CRITICAL: backports.zoneinfo package missing. Please run: pip install backports.zoneinfo", file=sys.stderr)
        sys.exit(1)

def detect_local_timezone():
    """
    Attempts to discover the system's local timezone.
    Cascades through environment variables, common Linux configurations,
    and falls back to America/Toronto if undetermined.
    """
    # 1. Check common standard 'TZ' environment variable
    tz_env = os.environ.get('TZ')
    if tz_env:
        try:
            return ZoneInfo(tz_env)
        except ZoneInfoNotFoundError:
            pass
            
    # 2. Check Debian/Ubuntu system file
    if os.path.exists('/etc/timezone'):
        try:
            with open('/etc/timezone', 'r', encoding='utf-8') as f:
                tz_name = f.read().strip()
                if tz_name:
                    return ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, IOError):
            pass
            
    # 3. Check RedHat/CentOS symlink configuration
    if os.path.exists('/etc/localtime') and os.path.islink('/etc/localtime'):
        try:
            target = os.readlink('/etc/localtime')
            # Extracts zone name out of paths like /usr/share/zoneinfo/America/Toronto
            match = re.search(r'zoneinfo/(.+)$', target)
            if match:
                return ZoneInfo(match.group(1))
        except (ZoneInfoNotFoundError, OSError):
            pass

    # 4. Universal Fallback
    return ZoneInfo("America/Toronto")


# Initialize the dynamically detected timezone globally
LOCAL_TZ = detect_local_timezone()


# --- Helper Functions ---

def sanitize_text(text):
    """Unescapes potential double-encoded entities, then strictly escapes for HTML."""
    if not text:
        return ""
    raw_text = html.unescape(str(text))
    return html.escape(raw_text, quote=True)

def extract_first_paragraph_or_truncate(entry, max_chars):
    """
    Looks for structural HTML paragraphs in content fields to preserve a clean first sentence/block.
    Falls back gracefully to standard character truncation if no formatting is found.
    """
    content_block = ""
    if "content" in entry and entry.content:
        content_block = entry.content[0].value
    if not content_block:
        content_block = entry.get("summary", "")
        
    if not content_block:
        return ""

    # Strategy 1: Attempt to match the first HTML paragraph block
    p_match = re.search(r'<p\b[^>]*>(.*?)</p>', content_block, re.IGNORECASE | re.DOTALL)
    if p_match:
        p_content = p_match.group(1)
        clean_text = html.unescape(p_content)
        clean_text = re.sub(r'<.*?>', '', clean_text).strip()
        if clean_text:
            return html.escape(clean_text, quote=True)

    # Strategy 2: Fallback configuration for plain-text entries or flat structures
    text = html.unescape(content_block)
    text = re.sub(r'<.*?>', '', text).strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "..."
    return html.escape(text, quote=True)

def sanitize_url(url):
    """Ensures the URL is an HTTP/HTTPS link and escapes it for attribute use."""
    if not url:
        return "#"
    url = str(url).strip()
    if url.lower().startswith(('http://', 'https://')):
        return html.escape(url, quote=True)
    return "#"

def format_date(dt_obj, include_year=True):
    """Formats dates while robustly stripping leading zeros from days/hours."""
    day = dt_obj.strftime("%d").lstrip("0")
    if include_year:
        return dt_obj.strftime(f"%b {day}, %Y")
    return dt_obj.strftime(f"%b {day}")


# --- Feed Processors ---

def process_news(feed_url, max_items, max_chars):
    html_output = '<div class="rss-box-brocknews"><ul class="rss-items">\n'
    
    try:
        req = urllib.request.Request(feed_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            raw_xml = response.read().decode('utf-8')
    except Exception as e:
        print(f"Error fetching news: {e}", file=sys.stderr)
        return html_output + "<li>Error loading news.</li></ul></div>\n"

    # Convert non-standard item-level <image> elements into standard <media:thumbnail> elements.
    processed_xml = re.sub(
        r'<image\b[^>]*>([^<]+)</image>', 
        r'<media:thumbnail url="\1" />', 
        raw_xml, 
        flags=re.IGNORECASE
    )
    
    feed = feedparser.parse(processed_xml)
    count = 0
    
    for entry in feed.entries:
        if count >= max_items:
            break
            
        title = sanitize_text(entry.get("title", "Untitled"))
        link = sanitize_url(entry.get("link", "#"))
        
        pub_date_str = ""
        if "published_parsed" in entry and entry.published_parsed:
            dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            pub_date_str = format_date(dt.astimezone(LOCAL_TZ), include_year=True)
        
        summary_clean = extract_first_paragraph_or_truncate(entry, max_chars)
            
        # --- AGGRESSIVE IMAGE EXTRACTION ---
        image_url = ""
        
        # 1. Target normalized media_thumbnail parameter
        if "media_thumbnail" in entry:
            image_url = entry.media_thumbnail[0].get("url", "")
        
        # 2. Fallback to standard enclosures if present
        if not image_url and "enclosures" in entry:
            for enc in entry.enclosures:
                if "image" in enc.get("type", "") or enc.get("href", "").lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp','.svg')):
                    image_url = enc.href
                    break
            
        # 3. Fallback to standard media_content maps
        if not image_url and "media_content" in entry:
            for media in entry.media_content:
                if "image" in media.get("medium", "") or "image" in media.get("type", ""):
                    image_url = media.get("url", "")
                    break
                    
        # 4. Final safety scraper against direct inline body <img> parameters
        if not image_url:
            content_block = entry.content[0].value if "content" in entry else entry.get("summary", "")
            img_match = re.search(r'<img[^>]+src=["\'](.*?)["\']', content_block, re.IGNORECASE)
            if img_match:
                image_url = img_match.group(1)
        
        safe_img_url = sanitize_url(image_url)
        if safe_img_url != "#":
            img_div = f'<div class="rss-image" style="background-image: url(\'{safe_img_url}\');"></div>'
        else:
            img_div = '<div class="rss-image empty-image"></div>'
            
        img_link = f'<a href="{link}" target="_blank" rel="noopener" tabindex="-1" aria-hidden="true" class="image-link">{img_div}</a>'

        html_output += f'''
        <li class="rss-item">
            {img_link}
            <div class="rss-content">
                <a href="{link}" target="_blank" rel="noopener">{title}</a><br>
                <span class="rss-date">{pub_date_str}</span><br>
                {summary_clean}
            </div>
        </li>
        '''
        count += 1
        
    html_output += '</ul></div>\n'
    return html_output

def process_events(feed_url, max_items, offset_seconds):
    html_output = '<div class="rss-box-experiencebu"><ul class="rss-items">\n'
    
    try:
        req = urllib.request.Request(feed_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            raw_xml = response.read().decode('utf-8')
    except Exception as e:
        print(f"Error fetching events: {e}", file=sys.stderr)
        return html_output + "<li>Error loading events.</li></ul></div>\n"

    processed_xml = re.sub(
        r'<host\b[^>]*>(.*?)</host>', 
        r'<category domain="event_host">\1</category>', 
        raw_xml, 
        flags=re.IGNORECASE | re.DOTALL
    )
    
    feed = feedparser.parse(processed_xml)
    count = 0
    now_utc = datetime.now(timezone.utc)
    threshold_time = now_utc + timedelta(seconds=offset_seconds)

    for entry in feed.entries:
        if count >= max_items:
            break
            
        # --- STATUS FILTER ---
        status_str = entry.get("status", "").strip().lower()
        if status_str != "confirmed":
            continue

        start_str = entry.get("start", entry.get("startdate", ""))
        end_str = entry.get("end", entry.get("enddate", ""))
        
        if not start_str:
            continue
            
        try:
            start_dt = parser.parse(start_str)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
                
            if start_dt < threshold_time:
                continue
                
            start_local = start_dt.astimezone(LOCAL_TZ)
            date_display = format_date(start_local, include_year=False) + " " + start_local.strftime("%-I:%M %p")
            
            if end_str:
                end_dt = parser.parse(end_str)
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(timezone.utc)
                end_local = end_dt.astimezone(LOCAL_TZ)
                date_display += f" to {format_date(end_local, include_year=False)}"  + " " + end_local.strftime("%-I:%M %p")

        except Exception as e:
            print(f"Error parsing date for {entry.get('title')}: {e}", file=sys.stderr)
            date_display = sanitize_text(start_str)

        title = sanitize_text(entry.get("title", "Untitled Event"))
        link = sanitize_url(entry.get("link", "#"))
        
        # --- HOST HANDLING ---
        host_names = []
        for tag in entry.get("tags", []):
            if tag.get("scheme") == "event_host":
                host_names.append(sanitize_text(tag.get("term", "")))
                
        host_str = ", ".join(host_names)
        host_display = f' <div class="rss-item-auth">[{host_str}]</div>' if host_str else ''
        
        image_url = ""
        if "enclosures" in entry:
            for enc in entry.enclosures:
                if enc.get("href"):
                    image_url = enc.href
                    break
                    
        safe_img_url = sanitize_url(image_url)
        if safe_img_url != "#":
            img_div = f'<div class="rss-image" style="background-image: url(\'{safe_img_url}\');"></div>'
        else:
            img_div = '<div class="rss-image empty-image"></div>'
            
        img_link = f'<a href="{link}" target="_blank" rel="noopener" tabindex="-1" aria-hidden="true" class="image-link">{img_div}</a>'

        html_output += f'''
        <li class="rss-item">
            {img_link}
            <div class="rss-content">
                <div><a href="{link}" target="_blank" rel="noopener">{title}</a>{host_display}</div>
                <div class="rss-date">{date_display}</div>
            </div>
        </li>
        '''
        count += 1

    html_output += '</ul></div>\n'
    return html_output


# --- Orchestration Engine ---

def main():
    parser = argparse.ArgumentParser(
        description="Aggregates and transforms Brock RSS feeds into an accessible, static HTML file."
    )
    
    parser.add_argument('--news-url', type=str, default="https://brocku.ca/brock-news/tag/brightspace/feed/",
                        help="Target RSS feed endpoint for Brock News.")
    parser.add_argument('--events-url', type=str, default="https://experiencebu.brocku.ca/events.rss",
                        help="Target RSS feed endpoint for ExperienceBU events.")
    parser.add_argument('--output-path', type=str, default="./brock_updates.html",
                        help="Destination write path for the generated static HTML structure.")
    parser.add_argument('--event-offset', type=int, default=900,
                        help="Future timeline horizon cutoff limit in seconds (skips stale/in-progress events).")
    parser.add_argument('--max-news', type=int, default=2,
                        help="Maximum constraint capping calculated news articles.")
    parser.add_argument('--max-events', type=int, default=5,
                        help="Maximum constraint capping processed calendar events.")
    parser.add_argument('--max-chars', type=int, default=260,
                        help="Character bounding limit tracking descriptive string truncations.")
    
    args = parser.parse_args()

    # Process individual panels using CLI configs
    news_html = process_news(args.news_url, args.max_news, args.max_chars)
    events_html = process_events(args.events_url, args.max_events, args.event_offset)
    
    # Generate the dynamic generation timestamp string
    gen_time_str = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")

    # Template composition
    final_html = f'''<!DOCTYPE html>
<html xml:lang="en-CA" lang="en-CA">
<head>
    <meta created="{gen_time_str}">
    <meta charset="UTF-8">
    <title>Brock News &amp; Events</title>
     <style>
        /* Base styles */
        body {{ font-family: 'Lato', sans-serif; padding: 0 10px 0 10px; margin: 0; color: #202122; }}
        h3 {{ margin-bottom: 0.5em; font-size: 1rem; }}
        h3 a {{ text-decoration: none; color: #cc0000; }}
        ul {{ list-style: none; margin: 0; padding: 0; }}
        
        /* Layout for items */
        .rss-item {{ display: flex; align-items: flex-start; margin-bottom: 0.5em; padding-bottom: 0.5em; }}
        .rss-item:last-child {{ border-bottom: none; }}
        
        /* Image styling - matches Brightspace rounded cards */
        .image-link {{ flex-shrink: 0; margin-right: 15px; text-decoration: none; }}
        .rss-image {{ width: 90px; height: 60px; background-size: cover; background-position: center; border-radius: 6px; background-color: #f1f5fb; border: 1px solid #e3e9f1; transition: opacity 0.2s ease; }}
        .image-link:hover .rss-image {{ opacity: 0.85; }}
        
        /* Content styling */
        .rss-content {{ flex-grow: 1; font-size: 0.9rem; line-height: 1.3; border-bottom: 1px solid #e3e9f1; padding-bottom: 0.5em; }}
        .rss-item:last-child .rss-content {{ border-bottom: none; padding-bottom: 0; }}
        .rss-content a {{ font-weight: bold; text-decoration: none; color: #006fbf; }}
        .rss-content a:hover {{ text-decoration: underline; color: #004489; }}
        .rss-date {{ font-size: 0.8rem; color: #6e7477; display: inline-block; margin-top: 4px; margin-bottom: 4px; }}
        .rss-item-auth {{ font-size: 0.8rem; color: #202122; }}
        
        /* Fallback image */
        .empty-image {{ background-color: #CC0000; background-image: url('https://brightspace.brocku.ca/d2l/lp/navbars/6606/theme/viewimage/1179993/view'); background-size: cover; background-position: center; }}
 
        /* Floating / Sticky Footer Bar for "More Events" */
        .more-events-sticky {{position: fixed; bottom: 0;left: 0;right: 0;background: linear-gradient(to top, rgba(255,255,255,1) 75%, rgba(255,255,255,0) 100%);padding: 20px 10px 10px 10px; z-index: 1000;}}
    </style>
</head>
<body>
    <h3><a href="https://brocku.ca/brock-news/" target="_blank" rel="noopener">Brock University News</a></h3>
    {news_html}
    
    <h3><a href="https://experiencebu.brocku.ca/events" target="_blank" rel="noopener">Brock University Upcoming Events</a></h3>
    {events_html}
    <div class="more-events-sticky">
        <a style="color: #006fbf; text-decoration: none;" href="https://experiencebu.brocku.ca/events" target="_blank" rel="noopener"><strong>More Events &raquo;</strong></a>
    </div>
</body>
</html>
'''

    # Cache Optimization Guard: Verify file contents but strip out dynamic meta strings
    # so we don't trigger cache invalidation purely based on time string increments.
    if os.path.exists(args.output_path):
        try:
            with open(args.output_path, 'r', encoding='utf-8') as current_file:
                existing_html = current_file.read()
            
            # Use regex to strip out the dynamic generation meta tag from both strings
            clean_existing = re.sub(r'<meta created="[^"]*">', '', existing_html)
            clean_proposed = re.sub(r'<meta created="[^"]*">', '', final_html)
            
            if clean_existing == clean_proposed:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Content unchanged. Skipping file modification to keep upstream caches primed.")
                return
        except Exception as e:
            print(f"Warning: Cache check read mismatch error: {e}", file=sys.stderr)

    # Atomic write pattern executed only if actual RSS data has drifted
    temp_path = args.output_path + ".tmp"
    try:
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(final_html)
        os.replace(temp_path, args.output_path)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Content shifted! Static HTML written successfully.")
    except Exception as e:
        print(f"File writing failure encountered on path target destinations: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()