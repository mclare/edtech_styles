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
# --service-alerts https://brightspace.brocku.ca/d2l/le/news/rss/249302/course?token=apqljg7nhrr09cs811&ou=249302
# --max-chars 260
# --event-offset 900
###########################################################################

import os
import re
import html
import sys
import tempfile
import argparse
import urllib.request
import feedparser
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
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
        print("CRITICAL: backports.zoneinfo package missing. Please run: pip install backports.zoneinfo", file=sys.stderr)
        sys.exit(1)

USER_AGENT = "Mozilla/5.0"
FETCH_TIMEOUT_SECONDS = 15


def detect_local_timezone():
    """
    Attempts to discover the system's local timezone.
    Cascades through environment variables, common Linux configurations,
    and falls back to America/Toronto if undetermined.
    """
    tz_env = os.environ.get('TZ')
    if tz_env:
        try:
            return ZoneInfo(tz_env)
        except ZoneInfoNotFoundError:
            pass

    if os.path.exists('/etc/timezone'):
        try:
            with open('/etc/timezone', 'r', encoding='utf-8') as f:
                tz_name = f.read().strip()
                if tz_name:
                    return ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, IOError):
            pass

    if os.path.exists('/etc/localtime') and os.path.islink('/etc/localtime'):
        try:
            target = os.readlink('/etc/localtime')
            match = re.search(r'zoneinfo/(.+)$', target)
            if match:
                return ZoneInfo(match.group(1))
        except (ZoneInfoNotFoundError, OSError):
            pass

    return ZoneInfo("America/Toronto")


LOCAL_TZ = detect_local_timezone()


# --- Helper Functions ---

def fetch_url(url, label, timeout=FETCH_TIMEOUT_SECONDS):
    """Fetches HTTP/HTTPS content with scheme validation and a socket timeout."""
    if not url or not str(url).strip().lower().startswith(('http://', 'https://')):
        print(f"Invalid or unsupported URL scheme for {label}: {url}", file=sys.stderr)
        return None

    try:
        req = urllib.request.Request(str(url).strip(), headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read()
    except Exception as e:
        print(f"Error fetching {label}: {e}", file=sys.stderr)
        return None


def parse_xml_bytes(raw_xml, label):
    """Parses XML bytes while blocking DOCTYPE/ENTITY declarations."""
    if not raw_xml:
        return None
    if re.search(rb'<!(?:DOCTYPE|ENTITY)\b', raw_xml, re.IGNORECASE):
        print(f"Error parsing {label}: disallowed DOCTYPE or ENTITY declaration", file=sys.stderr)
        return None
    try:
        return ET.fromstring(raw_xml)
    except ET.ParseError as e:
        print(f"Error parsing {label}: {e}", file=sys.stderr)
        return None


def sanitize_text(text):
    """Unescapes potential double-encoded entities, then strictly escapes for HTML."""
    if not text:
        return ""
    raw_text = html.unescape(str(text))
    return html.escape(raw_text, quote=True)


class _SafeDescriptionParser(HTMLParser):
    """Sanitizes HTML descriptions, preserving safe <a> links and block breaks within max_chars."""

    def __init__(self, max_chars=None):
        super().__init__(convert_charrefs=True)
        self.max_chars = max_chars
        self.char_count = 0
        self.truncated = False
        self.in_link = False
        self.skip_depth = 0
        self.tokens = []

    def handle_starttag(self, tag, attrs):
        if self.truncated:
            return
        tag = tag.lower()
        if tag in ("script", "style"):
            self.skip_depth += 1
            return
        if self.skip_depth > 0:
            return

        if tag == "br":
            self.tokens.append("\n")
        elif tag == "a" and not self.in_link:
            href = next((val for key, val in attrs if key.lower() == "href" and val), "")
            safe_href = sanitize_url(href)
            if safe_href != "#":
                self.tokens.append(f'<a href="{safe_href}" target="_blank" rel="noopener">')
                self.in_link = True

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("script", "style") and self.skip_depth > 0:
            self.skip_depth -= 1
            return
        if self.skip_depth > 0:
            return

        if tag == "a" and self.in_link:
            self.tokens.append("</a>")
            self.in_link = False
        elif tag in ("p", "div", "li") and not self.truncated:
            self.tokens.append("\n")

    def handle_data(self, data):
        if self.truncated or self.skip_depth > 0 or not data:
            return

        clean_data = re.sub(r'[\r\n]+', ' ', data)
        if not self.tokens or self.tokens[-1] == "\n":
            clean_data = clean_data.lstrip()
        if not clean_data:
            return

        if self.max_chars is not None:
            remaining = self.max_chars - self.char_count
            if len(clean_data) > remaining:
                snippet = clean_data[:remaining].rstrip() + "..."
                self.tokens.append(html.escape(snippet, quote=True))
                self.char_count = self.max_chars
                self.truncated = True
                if self.in_link:
                    self.tokens.append("</a>")
                    self.in_link = False
                return

        self.tokens.append(html.escape(clean_data, quote=True))
        self.char_count += len(clean_data)

    def get_html(self):
        if self.in_link:
            self.tokens.append("</a>")
            self.in_link = False

        lines = []
        for raw_line in "".join(self.tokens).split("\n"):
            line = raw_line.strip()
            visible_text = re.sub(r'<[^>]+>', '', line).strip()
            if visible_text:
                lines.append(line)
        return "<br>".join(lines)


def sanitize_rss_description(description, max_chars=None):
    """Converts an RSS description to safe HTML, preserving validated <a> links and block breaks."""
    if not description:
        return ""
    unescaped = html.unescape(str(description))
    desc_parser = _SafeDescriptionParser(max_chars=max_chars)
    desc_parser.feed(unescaped)
    desc_parser.close()
    return desc_parser.get_html()


def extract_first_paragraph_or_truncate(entry, max_chars):
    """
    Looks for structural HTML paragraphs in content fields to preserve a clean first block.
    Falls back to stripped plain text, enforcing max_chars in both cases.
    """
    content_block = ""
    if "content" in entry and entry.content:
        content_block = entry.content[0].value
    if not content_block:
        content_block = entry.get("summary", "")

    if not content_block:
        return ""

    p_match = re.search(r'<p\b[^>]*>(.*?)</p>', content_block, re.IGNORECASE | re.DOTALL)
    if p_match:
        clean_text = re.sub(r'<.*?>', '', html.unescape(p_match.group(1))).strip()
    else:
        clean_text = re.sub(r'<.*?>', '', html.unescape(content_block)).strip()

    if not clean_text:
        return ""

    if max_chars and len(clean_text) > max_chars:
        clean_text = clean_text[:max_chars] + "..."
    return html.escape(clean_text, quote=True)


def sanitize_url(url):
    """
    Ensures the URL uses HTTP/HTTPS, strips control characters, and neutralizes
    characters that could break out of HTML attributes or CSS url('...') contexts.
    """
    if not url:
        return "#"
    url = re.sub(r'[\x00-\x1f\x7f]', '', str(url)).strip()
    if not url.lower().startswith(('http://', 'https://')):
        return "#"

    css_safe = (
        url.replace('\\', '%5C')
           .replace("'", '%27')
           .replace('"', '%22')
           .replace('(', '%28')
           .replace(')', '%29')
    )
    return html.escape(css_safe, quote=True)


def format_date(dt_obj, include_year=True):
    """Formats dates while robustly stripping leading zeros from days."""
    day = dt_obj.strftime("%d").lstrip("0")
    if include_year:
        return dt_obj.strftime(f"%b {day}, %Y")
    return dt_obj.strftime(f"%b {day}")


def render_image_link(link, image_url):
    """Renders the thumbnail link block with fallback styling when no image is present."""
    safe_img_url = sanitize_url(image_url)
    if safe_img_url != "#":
        img_div = f'<div class="rss-image" style="background-image: url(\'{safe_img_url}\');"></div>'
    else:
        img_div = '<div class="rss-image empty-image"></div>'
    return f'<a href="{link}" target="_blank" rel="noopener" tabindex="-1" aria-hidden="true" class="image-link">{img_div}</a>'


def render_alert_banner(box_class, heading_url, heading_text, item_url, item_title, description, svg_markup):
    """Renders a top-level status/degradation banner matching the feed card layout."""
    description_markup = f"<br>{description}" if description else ""
    encoded_svg = quote(svg_markup, safe="")
    return f'''    <div class="{box_class}">
        <h3><a href="{heading_url}" target="_blank" rel="noopener">{heading_text}</a></h3>
        <div class="rss-item" style="border: none; padding-bottom: 0;">
            <a href="{item_url}" target="_blank" rel="noopener" tabindex="-1" aria-hidden="true" class="image-link"><div class="rss-image" style="background-image: url('data:image/svg+xml,{encoded_svg}'); background-size: contain; background-repeat: no-repeat; background-color: #fff;"></div></a>
            <div class="rss-content">
                <a href="{item_url}" target="_blank" rel="noopener">{item_title}</a>{description_markup}
            </div>
        </div>
    </div>\n'''

# --- Feed Processors --- SVG images for special alerts

SERVICE_ALERT_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="-5 -5 130 118">
<path d="M53.1 8.5C56.2 3.2 63.8 3.2 66.9 8.5L116.4 93.5C119.5 98.8 115.7 105.5 109.5 105.5H10.5C4.3 105.5 0.5 98.8 3.6 93.5L53.1 8.5Z" fill="none" stroke="#CC0000" stroke-width="8" stroke-linejoin="round"/>
<rect x="54" y="36" width="12" height="32" rx="6" fill="#202122"/>
<circle cx="60" cy="83" r="6.5" fill="#202122"/>
</svg>'''

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


def process_service_alerts(feed_url, max_chars):
    """Checks the service alerts RSS feed for active items and returns a warning banner for the first item."""
    raw_xml = fetch_url(feed_url, "service alerts")
    root = parse_xml_bytes(raw_xml, "service alerts")
    if root is None:
        return ""

    items = root.findall(".//item")
    if not items:
        return ""

    latest_item = items[0]
    link = sanitize_url(latest_item.findtext("link", ""))
    if link == "#":
        link = "https://brightspace.brocku.ca/"

    raw_title = latest_item.findtext("title", "").strip()
    title = sanitize_text(raw_title) if raw_title else "There is currently an issue disrupting services"
    description = sanitize_rss_description(latest_item.findtext("description", ""), max_chars)

    return render_alert_banner(
        box_class="rss-box-service-alerts",
        heading_url=link,
        heading_text="Service Degradation",
        item_url=link,
        item_title=title,
        description=description,
        svg_markup=SERVICE_ALERT_SVG,
    )


def process_microsoft_status(feed_url, max_chars):
    """Checks the Microsoft 365 status feed for ServiceDegradation and returns a warning banner if found."""
    raw_xml = fetch_url(feed_url, "Microsoft status")
    root = parse_xml_bytes(raw_xml, "Microsoft status")
    if root is None:
        return ""

    status_item = next(
        (item for item in root.findall(".//item") if item.findtext("status") == "ServiceDegradation"),
        None,
    )
    if status_item is None:
        return ""

    description = sanitize_rss_description(status_item.findtext("description", ""), max_chars)
    ms_url = "https://status.cloud.microsoft/"

    return render_alert_banner(
        box_class="rss-box-microsoft",
        heading_url=ms_url,
        heading_text="Microsoft 365 Service Degradation",
        item_url=ms_url,
        item_title="There is currently an issue disrupting services like Outlook and Teams.",
        description=description,
        svg_markup=MICROSOFT_STATUS_SVG,
    )


def extract_entry_image(entry):
    """Extracts the best available image URL from normalized media fields, enclosures, or inline HTML."""
    if entry.get("media_thumbnail"):
        url = entry.media_thumbnail[0].get("url", "")
        if url:
            return url

    for enc in entry.get("enclosures", []):
        href = enc.get("href", "")
        if "image" in enc.get("type", "") or href.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg')):
            if href:
                return href

    for media in entry.get("media_content", []):
        if "image" in media.get("medium", "") or "image" in media.get("type", ""):
            url = media.get("url", "")
            if url:
                return url

    content_block = entry.content[0].value if entry.get("content") else entry.get("summary", "")
    img_match = re.search(r'<img[^>]+src=["\'](.*?)["\']', content_block, re.IGNORECASE)
    return img_match.group(1) if img_match else ""


def process_standard_feed(feed_url, max_items, max_chars, box_class, label):
    """Processes standard RSS feeds (News, Sports) into an HTML list."""
    raw_bytes = fetch_url(feed_url, label)
    if raw_bytes is None:
        return None

    raw_xml = raw_bytes.decode('utf-8', errors='replace')
    # Normalize non-standard item-level <image> elements into <media:thumbnail>
    processed_xml = re.sub(
        r'<image\b[^>]*>([^<]+)</image>',
        r'<media:thumbnail url="\1" />',
        raw_xml,
        flags=re.IGNORECASE,
    )

    feed = feedparser.parse(processed_xml)
    html_output = f'<div class="{box_class}"><ul class="rss-items">\n'

    for entry in feed.entries[:max_items]:
        title = sanitize_text(entry.get("title", "Untitled"))
        link = sanitize_url(entry.get("link", "#"))

        pub_date_str = ""
        if entry.get("published_parsed"):
            dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            pub_date_str = format_date(dt.astimezone(LOCAL_TZ), include_year=True)

        summary_clean = extract_first_paragraph_or_truncate(entry, max_chars)
        img_link = render_image_link(link, extract_entry_image(entry))

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

    html_output += '</ul></div>\n'
    return html_output


def process_events(feed_url, max_items, offset_seconds):
    """Processes ExperienceBU upcoming confirmed events into an HTML list."""
    raw_bytes = fetch_url(feed_url, "events")
    if raw_bytes is None:
        return None

    raw_xml = raw_bytes.decode('utf-8', errors='replace')
    processed_xml = re.sub(
        r'<host\b[^>]*>(.*?)</host>',
        r'<category domain="event_host">\1</category>',
        raw_xml,
        flags=re.IGNORECASE | re.DOTALL,
    )

    feed = feedparser.parse(processed_xml)
    html_output = '<div class="rss-box-experiencebu"><ul class="rss-items">\n'
    count = 0
    threshold_time = datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)

    for entry in feed.entries:
        if count >= max_items:
            break

        if entry.get("status", "").strip().lower() != "confirmed":
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
            start_time_str = start_local.strftime("%I:%M %p").lstrip("0")
            date_display = f"{format_date(start_local, include_year=False)} {start_time_str}"

            if end_str:
                end_dt = parser.parse(end_str)
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                end_local = end_dt.astimezone(LOCAL_TZ)
                end_time_str = end_local.strftime("%I:%M %p").lstrip("0")
                date_display += f" to {format_date(end_local, include_year=False)} {end_time_str}"

        except Exception as e:
            print(f"Error parsing date for {entry.get('title')}: {e}", file=sys.stderr)
            date_display = sanitize_text(start_str)

        title = sanitize_text(entry.get("title", "Untitled Event"))
        link = sanitize_url(entry.get("link", "#"))

        host_names = [
            sanitize_text(tag.get("term", ""))
            for tag in entry.get("tags", [])
            if tag.get("scheme") == "event_host" and tag.get("term")
        ]
        host_display = f' <div class="rss-item-auth">[{", ".join(host_names)}]</div>' if host_names else ''

        image_url = next((enc.get("href", "") for enc in entry.get("enclosures", []) if enc.get("href")), "")
        img_link = render_image_link(link, image_url)

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
    arg_parser = argparse.ArgumentParser(
        description="Aggregates and transforms Brock RSS feeds into an accessible, static HTML file."
    )

    arg_parser.add_argument('--news-url', type=str, default="https://brocku.ca/brock-news/tag/brightspace/feed/",
                            help="Target RSS feed endpoint for Brock News.")
    arg_parser.add_argument('--sports-url', type=str, default="https://gobadgers.ca/rss?path=",
                            help="Target RSS feed endpoint for Brock Badgers sports news.")
    arg_parser.add_argument('--events-url', type=str, default="https://experiencebu.brocku.ca/events.rss",
                            help="Target RSS feed endpoint for ExperienceBU events.")
    arg_parser.add_argument('--microsoft-status', type=str, nargs='?',
                            const="https://status.cloud.microsoft/api/feed/mac", default=None,
                            help="Target RSS feed endpoint for Microsoft 365 status.")
    arg_parser.add_argument('--service-alerts', type=str, nargs='?',
                            const="https://brightspace.brocku.ca/d2l/le/news/rss/249302/course?token=apqljg7nhrr09cs811&ou=249302", default=None,
                            help="Target RSS feed endpoint for service degradation alerts.")
    arg_parser.add_argument('--output-path', type=str, default="./brock_updates.html",
                            help="Destination write path for the generated static HTML structure.")
    arg_parser.add_argument('--event-offset', type=int, default=900,
                            help="Future timeline horizon cutoff limit in seconds (skips stale/in-progress events).")
    arg_parser.add_argument('--max-news', type=int, default=2,
                            help="Maximum constraint capping calculated news articles.")
    arg_parser.add_argument('--max-sports', type=int, default=1,
                            help="Maximum number of Brock Badgers sports news items.")
    arg_parser.add_argument('--max-events', type=int, default=5,
                            help="Maximum constraint capping processed calendar events.")
    arg_parser.add_argument('--max-chars', type=int, default=260,
                            help="Character bounding limit tracking descriptive string truncations.")

    args = arg_parser.parse_args()

    # Process individual panels using CLI configs
    service_alerts_section = process_service_alerts(args.service_alerts, args.max_chars) if args.service_alerts else ""
    microsoft_section = process_microsoft_status(args.microsoft_status, args.max_chars) if args.microsoft_status else ""

    news_section = ""
    if args.max_news > 0:
        news_html = process_standard_feed(args.news_url, args.max_news, args.max_chars, "rss-box-brocknews", "news")
        if news_html is not None:
            news_section = f'''    <h3><a href="https://brocku.ca/brock-news/" target="_blank" rel="noopener">Brock University News</a></h3>
    {news_html}'''

    sports_section = ""
    if args.max_sports > 0:
        sports_html = process_standard_feed(args.sports_url, args.max_sports, args.max_chars, "rss-box-brocksports", "sports news")
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

    gen_time_str = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")

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
{service_alerts_section}
{microsoft_section}
{news_section}
{sports_section}
{events_section}
</body>
</html>
'''

    # Cache Optimization Guard: Strip dynamic meta timestamp before comparing
    if os.path.exists(args.output_path):
        try:
            with open(args.output_path, 'r', encoding='utf-8') as current_file:
                existing_html = current_file.read()

            clean_existing = re.sub(r'<meta created="[^"]*">', '', existing_html)
            clean_proposed = re.sub(r'<meta created="[^"]*">', '', final_html)

            if clean_existing == clean_proposed:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Content unchanged. Skipping file modification to keep upstream caches primed.")
                return
        except Exception as e:
            print(f"Warning: Cache check read mismatch error: {e}", file=sys.stderr)

    # Collision-safe atomic write pattern
    output_dir = os.path.dirname(os.path.abspath(args.output_path))
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=output_dir, prefix='.tmp_brock_', suffix='.html', delete=False) as tmp_file:
            temp_path = tmp_file.name
            tmp_file.write(final_html)
        os.chmod(temp_path, 0o644)
        os.replace(temp_path, args.output_path)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Content shifted! Static HTML written successfully.")
    except Exception as e:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        print(f"File writing failure encountered on path target destinations: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()