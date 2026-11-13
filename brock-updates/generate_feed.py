###########################################################################
# Example use 
# python generate_feed.py --max-events 5 --max-news 2 --max-sports 1 --output-path ./brock_updates.html
#
# Other flag defaults:
# --news-url https://brocku.ca/brock-news/tag/brightspace/feed/
# --sports-url https://gobadgers.ca/rss?path=
#           https://gobadgers.ca/rss?path=general returns too few stories, so we use the more general feed... without general.    
# --events-url https://experiencebu.brocku.ca/events.rss
# --microsoft-status https://status.cloud.microsoft/api/feed/mac
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
import xml.etree.ElementTree as ET
from urllib.parse import quote
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

def sanitize_rss_description(description, max_chars=None):
    """Converts an RSS description to escaped text, respects length limits, and preserves block breaks."""
    if not description:
        return ""
    text = html.unescape(str(description))
    text = re.sub(r'<br\b[^>]*>|</(?:div|p|li)\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text).strip()
    
    # Truncate text prior to splitting to preserve accurate character count
    if max_chars and len(text) > max_chars:
        text = text[:max_chars] + "..."
        
    return "<br>".join(
        html.escape(line.strip(), quote=True)
        for line in text.splitlines()
        if line.strip()
    )

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

MICROSOFT_STATUS_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1406 301">
<path d="M583.336 240H553.951V124.453C553.951 114.99 554.532 103.411 555.695 89.7144H555.197C553.37 97.5171 551.752 103.12 550.341 106.523L497.05 240H476.63L423.214 107.52C421.72 103.618 420.143 97.6831 418.483 89.7144H417.985C418.649 96.853 418.981 108.516 418.981 124.702V240H391.588V61.4502H433.3L480.24 180.359C483.81 189.49 486.134 196.296 487.213 200.779H487.836C490.907 191.399 493.397 184.426 495.306 179.861L543.119 61.4502H583.336V240Z" fill="#77787B"/>
<path d="M631.988 85.73C627.256 85.73 623.189 84.1943 619.785 81.123C616.465 78.0518 614.805 74.1504 614.805 69.4189C614.805 64.6875 616.465 60.7446 619.785 57.5903C623.189 54.436 627.256 52.8589 631.988 52.8589C636.885 52.8589 641.035 54.436 644.439 57.5903C647.842 60.7446 649.544 64.6875 649.544 69.4189C649.544 73.9014 647.842 77.7612 644.439 80.9985C641.035 84.1528 636.885 85.73 631.988 85.73ZM646.306 240H617.42V112.5H646.306V240Z" fill="#77787B"/>
<path d="M765.165 234.148C754.955 240.042 742.877 242.988 728.932 242.988C710.006 242.988 694.732 237.095 683.111 225.308C671.49 213.438 665.68 198.081 665.68 179.238C665.68 158.237 671.905 141.387 684.356 128.687C696.891 115.903 713.617 109.512 734.535 109.512C746.156 109.512 756.407 111.545 765.289 115.613V142.507C756.407 135.867 746.944 132.546 736.9 132.546C724.698 132.546 714.696 136.697 706.893 144.998C699.09 153.215 695.189 164.006 695.189 177.371C695.189 190.569 698.841 200.986 706.146 208.623C713.534 216.26 723.412 220.078 735.78 220.078C746.156 220.078 755.951 216.384 765.165 208.997V234.148Z" fill="#77787B"/>
<path d="M865.332 140.017C861.845 137.278 856.823 135.908 850.266 135.908C841.716 135.908 834.577 139.768 828.85 147.488C823.122 155.208 820.258 165.708 820.258 178.989V240H791.372V112.5H820.258V138.772H820.756C823.579 129.807 827.895 122.834 833.706 117.854C839.599 112.791 846.157 110.259 853.378 110.259C858.608 110.259 862.592 111.047 865.332 112.625V140.017Z" fill="#77787B"/>
<path d="M931.487 242.988C911.814 242.988 896.084 237.053 884.297 225.183C872.593 213.23 866.741 197.417 866.741 177.744C866.741 156.328 872.842 139.602 885.044 127.566C897.33 115.53 913.848 109.512 934.6 109.512C954.522 109.512 970.044 115.364 981.167 127.068C992.291 138.772 997.852 155 997.852 175.752C997.852 196.089 991.834 212.4 979.798 224.685C967.845 236.887 951.741 242.988 931.487 242.988ZM932.857 132.546C921.568 132.546 912.645 136.489 906.087 144.375C899.529 152.261 896.25 163.135 896.25 176.997C896.25 190.361 899.571 200.903 906.211 208.623C912.852 216.26 921.734 220.078 932.857 220.078C944.229 220.078 952.945 216.301 959.004 208.748C965.147 201.194 968.218 190.444 968.218 176.499C968.218 162.471 965.147 151.638 959.004 144.001C952.945 136.365 944.229 132.546 932.857 132.546Z" fill="#77787B"/>
<path d="M1178.18 242.988C1158.51 242.988 1142.78 237.053 1130.99 225.183C1119.29 213.23 1113.44 197.417 1113.44 177.744C1113.44 156.328 1119.54 139.602 1131.74 127.566C1144.02 115.53 1160.54 109.512 1181.3 109.512C1201.22 109.512 1216.74 115.364 1227.86 127.068C1238.99 138.772 1244.55 155 1244.55 175.752C1244.55 196.089 1238.53 212.4 1226.49 224.685C1214.54 236.887 1198.44 242.988 1178.18 242.988ZM1179.55 132.546C1168.26 132.546 1159.34 136.489 1152.78 144.375C1146.22 152.261 1142.95 163.135 1142.95 176.997C1142.95 190.361 1146.27 200.903 1152.91 208.623C1159.55 216.26 1168.43 220.078 1179.55 220.078C1190.92 220.078 1199.64 216.301 1205.7 208.748C1211.84 201.194 1214.91 190.444 1214.91 176.499C1214.91 162.471 1211.84 151.638 1205.7 144.001C1199.64 136.365 1190.92 132.546 1179.55 132.546Z" fill="#77787B"/>
<path d="M1334.72 74.7729C1330.81 72.5317 1326.37 71.4111 1321.39 71.4111C1307.36 71.4111 1300.35 79.3384 1300.35 95.1929V112.5H1329.98V135.161H1300.47V240H1271.59V135.161H1249.8V112.5H1271.59V91.8311C1271.59 78.3838 1275.99 67.8003 1284.79 60.0806C1293.58 52.2778 1304.58 48.3765 1317.78 48.3765C1324.92 48.3765 1330.56 49.165 1334.72 50.7422V74.7729Z" fill="#77787B"/>
<path d="M1405.77 238.63C1400.12 241.453 1392.69 242.864 1383.48 242.864C1358.74 242.864 1346.37 230.994 1346.37 207.253V135.161H1325.08V112.5H1346.37V82.9907L1375.26 74.7729V112.5H1405.77V135.161H1375.26V198.911C1375.26 206.465 1376.63 211.86 1379.37 215.098C1382.11 218.335 1386.67 219.954 1393.07 219.954C1397.96 219.954 1402.2 218.542 1405.77 215.72V238.63Z" fill="#77787B"/>
<path d="M1008.86 236.016V209.246C1019.65 217.463 1031.57 221.572 1044.6 221.572C1062.03 221.572 1070.74 216.426 1070.74 206.133C1070.74 203.228 1070 200.779 1068.5 198.787C1067.01 196.711 1064.98 194.885 1062.4 193.308C1059.91 191.731 1056.92 190.32 1053.44 189.075C1050.03 187.83 1046.22 186.418 1041.98 184.841C1036.75 182.766 1032.02 180.566 1027.79 178.242C1023.64 175.918 1020.15 173.303 1017.33 170.398C1014.59 167.41 1012.51 164.048 1011.1 160.312C1009.69 156.577 1008.99 152.219 1008.99 147.239C1008.99 141.096 1010.44 135.701 1013.34 131.052C1016.25 126.321 1020.15 122.378 1025.05 119.224C1029.95 115.986 1035.51 113.579 1041.73 112.002C1047.96 110.342 1054.39 109.512 1061.03 109.512C1072.82 109.512 1083.36 111.296 1092.66 114.866V140.142C1083.69 133.999 1073.4 130.928 1061.78 130.928C1058.13 130.928 1054.81 131.301 1051.82 132.048C1048.91 132.795 1046.42 133.833 1044.35 135.161C1042.27 136.489 1040.65 138.108 1039.49 140.017C1038.33 141.843 1037.75 143.877 1037.75 146.118C1037.75 148.857 1038.33 151.182 1039.49 153.091C1040.65 155 1042.36 156.702 1044.6 158.196C1046.92 159.607 1049.66 160.935 1052.82 162.18C1056.05 163.342 1059.75 164.629 1063.9 166.04C1069.38 168.281 1074.27 170.564 1078.59 172.888C1082.99 175.212 1086.72 177.869 1089.8 180.857C1092.87 183.762 1095.23 187.166 1096.89 191.067C1098.55 194.885 1099.38 199.451 1099.38 204.763C1099.38 211.238 1097.89 216.882 1094.9 221.697C1091.91 226.511 1087.93 230.496 1082.95 233.65C1077.97 236.804 1072.2 239.128 1065.64 240.623C1059.17 242.2 1052.32 242.988 1045.1 242.988C1031.15 242.988 1019.07 240.664 1008.86 236.016Z" fill="#77787B"/>
<path d="M157.424 0.75293H299.833V143.162H157.424V0.75293Z" fill="#8DC63F"/>
<path d="M0 0.75293H142.409V143.162H0V0.75293Z" fill="#F26522"/>
<path d="M0 158.344H142.409V300.753H0V158.344Z" fill="#00AEEF"/>
<path d="M157.424 158.344H299.833V300.753H157.424V158.344Z" fill="#FFC20E"/>
</svg>'''

def process_microsoft_status(feed_url, max_chars):
    """Checks the Microsoft 365 status feed for ServiceDegradation and returns a warning banner if found."""
    if not feed_url:
        return ""

    try:
        req = urllib.request.Request(feed_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            raw_xml = response.read()
    except Exception as e:
        print(f"Error fetching Microsoft status: {e}", file=sys.stderr)
        return ""

    try:
        status_item = next(
            (
                item for item in ET.fromstring(raw_xml).findall(".//item")
                if item.findtext("status") == "ServiceDegradation"
            ),
            None,
        )
    except ET.ParseError as e:
        print(f"Error parsing Microsoft status: {e}", file=sys.stderr)
        return ""

    if status_item is not None:
        description = sanitize_rss_description(
            status_item.findtext("description", ""), max_chars
        )
        description_markup = f"<br>{description}" if description else ""
        image_url = quote(MICROSOFT_STATUS_SVG, safe="")
        return f'''    <div class="rss-box-microsoft">
        <h3><a href="https://status.cloud.microsoft/" target="_blank" rel="noopener">Microsoft 365 Service Degradation</a></h3>
        <div class="rss-item" style="border: none; padding-bottom: 0;">
            <a href="https://status.cloud.microsoft/" target="_blank" rel="noopener" tabindex="-1" aria-hidden="true" class="image-link"><div class="rss-image" style="background-image: url('data:image/svg+xml,{image_url}'); background-size: contain; background-repeat: no-repeat; background-color: #fff;"></div></a>
            <div class="rss-content">
                <a href="https://status.cloud.microsoft/" target="_blank" rel="noopener">There is currently an issue disrupting services like Outlook and Teams.</a>{description_markup}
            </div>
        </div>
    </div>\n'''

    return ""

def process_news(feed_url, max_items, max_chars):
    html_output = '<div class="rss-box-brocknews"><ul class="rss-items">\n'
    
    try:
        req = urllib.request.Request(feed_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            raw_xml = response.read().decode('utf-8')
    except Exception as e:
        print(f"Error fetching news: {e}", file=sys.stderr)
        return None

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

def process_sports(feed_url, max_items, max_chars):
    html_output = '<div class="rss-box-brocksports"><ul class="rss-items">\n'

    try:
        req = urllib.request.Request(feed_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            raw_xml = response.read().decode('utf-8')
    except Exception as e:
        print(f"Error fetching sports news: {e}", file=sys.stderr)
        return None

    feed = feedparser.parse(raw_xml)

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

        image_url = ""
        if entry.get("media_thumbnail"):
            image_url = entry.media_thumbnail[0].get("url", "")

        if not image_url:
            for enclosure in entry.get("enclosures", []):
                if "image" in enclosure.get("type", ""):
                    image_url = enclosure.get("href", "")
                    break

        if not image_url:
            content_block = entry.get("summary", "")
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
        return None

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
    parser.add_argument('--sports-url', type=str, default="https://gobadgers.ca/rss?path=",
                        help="Target RSS feed endpoint for Brock Badgers sports news.")
    parser.add_argument('--events-url', type=str, default="https://experiencebu.brocku.ca/events.rss",
                        help="Target RSS feed endpoint for ExperienceBU events.")
    parser.add_argument('--microsoft-status', type=str, default="https://status.cloud.microsoft/api/feed/mac",
                        help="Target RSS feed endpoint for Microsoft 365 status.")
    parser.add_argument('--output-path', type=str, default="./brock_updates.html",
                        help="Destination write path for the generated static HTML structure.")
    parser.add_argument('--event-offset', type=int, default=900,
                        help="Future timeline horizon cutoff limit in seconds (skips stale/in-progress events).")
    parser.add_argument('--max-news', type=int, default=2,
                        help="Maximum constraint capping calculated news articles.")
    parser.add_argument('--max-sports', type=int, default=1,
                        help="Maximum number of Brock Badgers sports news items.")
    parser.add_argument('--max-events', type=int, default=5,
                        help="Maximum constraint capping processed calendar events.")
    parser.add_argument('--max-chars', type=int, default=260,
                        help="Character bounding limit tracking descriptive string truncations.")
    
    args = parser.parse_args()

    # Process individual panels using CLI configs
    microsoft_section = process_microsoft_status(args.microsoft_status, args.max_chars) if args.microsoft_status else ""

    news_section = ""
    if args.max_news > 0:
        news_html = process_news(args.news_url, args.max_news, args.max_chars)
        if news_html is not None:
            news_section = f'''    <h3><a href="https://brocku.ca/brock-news/" target="_blank" rel="noopener">Brock University News</a></h3>
    {news_html}'''

    sports_section = ""
    if args.max_sports > 0:
        sports_html = process_sports(args.sports_url, args.max_sports, args.max_chars)
        if sports_html is not None:
            sports_section = f'''    <h3><a href="https://gobadgers.ca/" target="_blank" rel="noopener">Brock Badgers Sports News</a></h3>
    {sports_html}'''

    events_section = ""
    if args.max_events > 0:
        events_html = process_events(args.events_url, args.max_events, args.event_offset)
        if events_html is not None:
            events_section = f'''    <h3><a href="https://experiencebu.brocku.ca/events" target="_blank" rel="noopener">Brock University Upcoming Events</a></h3>
    {events_html}
    <div class="more-events-sticky">
        <a style="color: #006fbf; text-decoration: none;" href="https://experiencebu.brocku.ca/events" target="_blank" rel="noopener"><strong>More Events &raquo;</strong></a>
    </div>'''
    
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
{microsoft_section}
{news_section}
{sports_section}
{events_section}
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