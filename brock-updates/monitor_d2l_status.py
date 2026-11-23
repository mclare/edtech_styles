#!/usr/bin/env python3
###########################################################################
# Example cron usage (every 5 minutes):
# */5 * * * * /usr/bin/python3 /path/to/monitor_d2l_status.py --output-dir /path/to/d2l_status_logs
###########################################################################

import os
import re
import sys
import json
import hashlib
import tempfile
import argparse
import urllib.request
from datetime import datetime

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
    try:
        from backports.zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    except ImportError:
        print("CRITICAL: backports.zoneinfo package missing. Please run: pip install backports.zoneinfo", file=sys.stderr)
        sys.exit(1)

DEFAULT_STATUS_URL = "https://d1cxwt39sm8ti5.cloudfront.net/prod/status/brightspace.brocku.ca.json"
HEALTHY_STATUS = "All Services Operational"
USER_AGENT = "Mozilla/5.0"
FETCH_TIMEOUT_SECONDS = 15


def detect_local_timezone():
    """Discovers the system's local timezone, falling back to America/Toronto."""
    tz_env = os.environ.get("TZ")
    if tz_env:
        try:
            return ZoneInfo(tz_env)
        except ZoneInfoNotFoundError:
            pass

    if os.path.exists("/etc/timezone"):
        try:
            with open("/etc/timezone", "r", encoding="utf-8") as f:
                tz_name = f.read().strip()
                if tz_name:
                    return ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, IOError):
            pass

    if os.path.exists("/etc/localtime") and os.path.islink("/etc/localtime"):
        try:
            target = os.readlink("/etc/localtime")
            match = re.search(r"zoneinfo/(.+)$", target)
            if match:
                return ZoneInfo(match.group(1))
        except (ZoneInfoNotFoundError, OSError):
            pass

    return ZoneInfo("America/Toronto")


LOCAL_TZ = detect_local_timezone()


def fetch_json(url, timeout=FETCH_TIMEOUT_SECONDS):
    """Fetches and parses a JSON object from an HTTP/HTTPS endpoint."""
    if not url or not str(url).strip().lower().startswith(("http://", "https://")):
        print(f"Invalid or unsupported URL scheme: {url}", file=sys.stderr)
        return None

    try:
        req = urllib.request.Request(str(url).strip(), headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw_bytes = response.read()
        parsed = json.loads(raw_bytes.decode("utf-8"))
        if not isinstance(parsed, dict):
            print("Unexpected JSON structure: expected top-level object.", file=sys.stderr)
            return None
        return parsed
    except Exception as e:
        print(f"Error fetching or parsing D2L status JSON: {e}", file=sys.stderr)
        return None


def compute_payload_hash(data):
    """Returns a deterministic SHA-256 hash of the JSON payload."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_last_state(state_path):
    """Loads the previously recorded status state, or returns None if unavailable."""
    if not os.path.exists(state_path):
        return None
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        return state if isinstance(state, dict) else None
    except Exception as e:
        print(f"Warning: Could not read state file {state_path}: {e}", file=sys.stderr)
        return None


def write_json_atomically(data, output_path):
    """Writes formatted JSON atomically with 0644 permissions."""
    output_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(output_dir, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_dir,
            prefix=".tmp_d2l_status_",
            suffix=".json",
            delete=False,
        ) as tmp_file:
            temp_path = tmp_file.name
            json.dump(data, tmp_file, indent=2, ensure_ascii=False)
            tmp_file.write("\n")
        os.chmod(temp_path, 0o644)
        os.replace(temp_path, output_path)
    except Exception as e:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        print(f"Error writing JSON to {output_path}: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Monitors D2L Brightspace status JSON and archives snapshots on state changes."
    )
    parser.add_argument(
        "--url",
        type=str,
        default=DEFAULT_STATUS_URL,
        help="Target D2L status JSON endpoint.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./d2l_status_logs",
        help="Directory where timestamped JSON snapshots will be saved.",
    )
    parser.add_argument(
        "--state-file",
        type=str,
        default=None,
        help="Path to the state tracking JSON file (defaults to <output-dir>/.last_state.json).",
    )
    args = parser.parse_args()

    data = fetch_json(args.url)
    if data is None:
        sys.exit(1)

    overall_status = str(data.get("status", "")).strip()
    is_healthy = overall_status == HEALTHY_STATUS
    current_hash = compute_payload_hash(data)

    state_path = args.state_file or os.path.join(args.output_dir, ".last_state.json")
    last_state = load_last_state(state_path)
    last_status = last_state.get("status") if last_state else None
    last_hash = last_state.get("payload_hash") if last_state else None

    was_unhealthy = last_status is not None and last_status != HEALTHY_STATUS
    now_local = datetime.now(LOCAL_TZ)
    timestamp_str = now_local.strftime("%Y-%m-%d_%H-%M-%S")
    log_time_str = now_local.strftime("%Y-%m-%d %H:%M:%S %Z")

    if not is_healthy:
        if current_hash != last_hash:
            filename = f"brightspace_status_{timestamp_str}.json"
            output_path = os.path.join(args.output_dir, filename)
            write_json_atomically(data, output_path)
            print(f"[{log_time_str}] Status is '{overall_status}'. Snapshot saved to {output_path}")
    elif was_unhealthy:
        filename = f"brightspace_status_{timestamp_str}_resolved.json"
        output_path = os.path.join(args.output_dir, filename)
        write_json_atomically(data, output_path)
        print(f"[{log_time_str}] Status recovered to '{overall_status}'. Resolution snapshot saved to {output_path}")

    if current_hash != last_hash or overall_status != last_status:
        write_json_atomically(
            {
                "status": overall_status,
                "payload_hash": current_hash,
                "updated_at": now_local.isoformat(),
            },
            state_path,
        )


if __name__ == "__main__":
    main()