from flask import Flask, Response
import requests
import re
import threading
import time

app = Flask(__name__)

cached_m3u = "#EXTM3U\n"
cached_epg = '<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n</tv>'

is_updating = False


# =========================================================
# CUSTOM DISHTV LCN LIST (Optional / Kept for reference)
# =========================================================

LCN_TEXT = """
100: Star Plus HD
101: Star Plus
102: Zee TV HD
103: Zee tv
104: SONY ENTERTAINMENT TELEVISION HD
105: SONY ENTERTAINMENT TELEVISION
106: SONY SAB HD
107: SONY SAB
108: &TV HD
109: Dangal TV
"""


# =========================================================
# NAME NORMALIZATION
# =========================================================

def normalize_name(name):
    name = str(name or "").lower().strip()

    # Hindi remove
    name = re.sub(r"\bhindi\b", "", name, flags=re.IGNORECASE)

    # Common separators normalize
    name = name.replace("_", " ")
    name = name.replace("-", " ")
    name = name.replace(".", " ")

    # Extra spaces
    name = re.sub(r"\s+", " ", name)

    return name.strip()


def normalize_lcn_name(name):
    name = str(name or "").lower().strip()

    name = re.sub(r"\bhindi\b", "", name)
    name = re.sub(r"\bhd\b", " hd ", name)

    name = name.replace("_", " ")
    name = name.replace("-", " ")
    name = name.replace(".", " ")

    name = re.sub(r"\s*&\s*", "&", name)
    name = re.sub(r"[^a-z0-9&]+", " ", name)
    name = re.sub(r"\s+", " ", name)

    return name.strip()


# =========================================================
# BUILD DISHTV LCN MAP
# =========================================================

dishtv_lcn_map = {}

for line in LCN_TEXT.splitlines():
    line = line.strip()
    if not line or line.startswith("#") or ":" not in line:
        continue

    lcn, name = line.split(":", 1)
    lcn = lcn.strip()
    name = name.strip()

    if not lcn or not name:
        continue

    key1 = normalize_name(name)
    key2 = normalize_lcn_name(name)

    if key1:
        dishtv_lcn_map[key1] = lcn
    if key2:
        dishtv_lcn_map[key2] = lcn


def find_lcn(channel_name):
    raw = str(channel_name or "").strip()
    if not raw:
        return None

    key = normalize_name(raw)
    if key in dishtv_lcn_map:
        return dishtv_lcn_map[key]

    key = normalize_lcn_name(raw)
    if key in dishtv_lcn_map:
        return dishtv_lcn_map[key]

    return None


# =========================================================
# REGIONAL FILTER
# =========================================================

regional_langs = [
    "tamil",
    "telugu",
    "malayalam",
    "marathi",
    "bengali",
    "kannada",
    "gujarati",
    "odia"
]


def clean_and_filter_name(raw_name):
    raw_name = str(raw_name or "").strip()
    if not raw_name:
        return None

    name_lower = raw_name.lower()

    # Regional channels remove
    for lang in regional_langs:
        if re.search(rf"\b{re.escape(lang)}\b", name_lower):
            return None

    # Hindi remove
    cleaned = re.sub(r"\s+\bHindi\b", "", raw_name, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)

    return cleaned.strip()


def get_extinf_name(line):
    if not line.startswith("#EXTINF:"):
        return ""
    match = re.search(r",(.+)$", line)
    if match:
        return match.group(1).strip()
    return ""


# =========================================================
# SECONDARY M3U PARSER (WITH SAME FILTERS)
# =========================================================

def load_secondary_streams():
    secondary_streams = {}
    sec_url = "https://raw.githubusercontent.com/Sflex0719/STBPLUS/refs/heads/main/Zio.m3u"

    try:
        print("Downloading secondary M3U...")
        sec_res = requests.get(sec_url, timeout=10)

        if sec_res.status_code != 200:
            print("Secondary HTTP error:", sec_res.status_code)
            return secondary_streams

        lines = sec_res.text.splitlines()
        current_name = ""
        current_extinf = ""
        current_extra_tags = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith("#EXTINF:"):
                current_extinf = line
                current_name = get_extinf_name(line)
                current_extra_tags = []
                continue

            if current_extinf and line.startswith("#") and not line.startswith("#EXTINF:"):
                if (
                    line.startswith("#EXTHTTP:")
                    or line.startswith("#EXTVLCOPT:")
                    or line.startswith("#KODIPROP:")
                    or line.startswith("#EXT-X-")
                ):
                    current_extra_tags.append(line)
                continue

            if current_extinf and current_name and line and not line.startswith("#"):
                # Apply same regional and clean filters to secondary streams
                cleaned_name = clean_and_filter_name(current_name)

                if cleaned_name:
                    key1 = normalize_name(cleaned_name)
                    key2 = normalize_lcn_name(cleaned_name)

                    stream_data = {
                        "url": line,
                        "tags": list(current_extra_tags)
                    }

                    if key1:
                        secondary_streams[key1] = stream_data
                    if key2:
                        secondary_streams[key2] = stream_data

                current_name = ""
                current_extinf = ""
                current_extra_tags = []

        print("Secondary channels loaded:", len(secondary_streams))

    except Exception as e:
        print(f"Secondary M3U error: {e}")

    return secondary_streams


def get_primary_url(ch):
    return str(
        ch.get("url")
        or ch.get("stream_url")
        or ch.get("link")
        or ""
    ).strip()


# =========================================================
# BACKGROUND UPDATE
# =========================================================

def update_m3u_background():
    global cached_m3u
    global cached_epg
    global is_updating

    if is_updating:
        return

    is_updating = True

    try:
        # 1. Star Sports Token
        COOKIE_STAR_SPORTS = "https://allinonereborn2.online/jtv-fetch/jstarcookie/cookie.json"
        star_tokens = {}

        try:
            res = requests.get(COOKIE_STAR_SPORTS, timeout=6)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, dict):
                    for item in data.get("failed_results", []):
                        if not isinstance(item, dict):
                            continue
                        ch_id_str = str(item.get("channel_id", ""))
                        err_details = item.get("error_details", {})
                        if not isinstance(err_details, dict):
                            continue
                        final_url = str(err_details.get("final_url", ""))
                        if "__hdnea__=" in final_url:
                            match = re.search(r"__hdnea__=([^&]+)", final_url)
                            if match:
                                star_tokens[ch_id_str] = "__hdnea__=" + match.group(1)
        except Exception as e:
            print(f"Star token error: {e}")

        # 2. Global Cookie
        token_urls = [
            "https://allinonereborn2.online/jstrweb2/cookies.json",
            "https://allinonereborn2.online/jstrweb3/cookies.json",
            "https://allinonereborn2.online/jstrweb4/cookies.json"
        ]
        global_token = ""

        for url in token_urls:
            try:
                res = requests.get(url, timeout=4)
                if res.status_code != 200:
                    continue
                data = res.json()
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("cookie"):
                            global_token = str(item["cookie"])
                            break
                if global_token:
                    break
            except Exception as e:
                print(f"Cookie error: {e}")
                continue

        # 3. Secondary M3U
        secondary_streams = load_secondary_streams()

        # 4. Channel JSON
        channel_url = "https://jjtvxweb.pages.dev/jstr4web.json"
        res = requests.get(channel_url, timeout=12)
        res.raise_for_status()
        channels = res.json()

        if not isinstance(channels, list):
            raise ValueError("Channel JSON list nahi hai")

        # 5. Build M3U
        m3u_lines = ["#EXTM3U"]
        epg_channels = []

        primary_count = 0
        secondary_count = 0

        for ch in channels:
            if not isinstance(ch, dict):
                continue

            raw_name = str(ch.get("name") or ch.get("channel_name") or "").strip()
            if not raw_name:
                continue

            ch_id = str(ch.get("id") or ch.get("channel_id") or "").strip()

            clean_name = clean_and_filter_name(raw_name)
            if not clean_name:
                continue

            primary_url = get_primary_url(ch)
            if not primary_url:
                continue

            # Display name without LCN numbers prefix
            display_name = clean_name

            # Check secondary match using clean name variations
            secondary_data = None
            secondary_key1 = normalize_name(clean_name)
            secondary_key2 = normalize_lcn_name(clean_name)

            if secondary_key1 in secondary_streams:
                secondary_data = secondary_streams[secondary_key1]
            elif secondary_key2 in secondary_streams:
                secondary_data = secondary_streams[secondary_key2]

            # Primary EXTINF
            extinf = (
                f'#EXTINF:-1 '
                f'tvg-id="{ch_id}" '
                f'tvg-name="{display_name}",'
                f'{display_name}'
            )
            m3u_lines.append(extinf)

            if global_token:
                m3u_lines.append(f"#EXTHTTP:{global_token}")

            if ch_id in star_tokens:
                m3u_lines.append(f"#EXTHTTP:{star_tokens[ch_id]}")

            m3u_lines.append(primary_url)
            primary_count += 1

            if secondary_data:
                secondary_url = str(secondary_data.get("url", "")).strip()
                if secondary_url and re.match(r"^(https?|rtmp|rtsp)://", secondary_url, flags=re.IGNORECASE):
                    secondary_count += 1
                    print(f"SECONDARY MATCH: {clean_name} -> {secondary_url[:80]}")

            if ch_id:
                safe_name = (
                    display_name
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                epg_channels.append(
                    f'  <channel id="{ch_id}">'
                    f'<display-name>{safe_name}</display-name>'
                    f'</channel>'
                )

        epg_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<tv>\n'
            + "\n".join(epg_channels)
            + "\n</tv>"
        )

        cached_m3u = "\n".join(m3u_lines) + "\n"
        cached_epg = epg_xml

        print("================================")
        print("Playlist updated (LCN numbers removed)")
        print(f"Primary channels: {primary_count}")
        print(f"Secondary matches: {secondary_count}")
        print("================================")

    except Exception as e:
        print(f"Background update error: {e}")
    finally:
        is_updating = False


def periodic_updater():
    while True:
        try:
            update_m3u_background()
        except Exception as e:
            print(f"Updater error: {e}")
        time.sleep(180)


@app.route("/")
def index():
    return "IPTV Server Running"


@app.route("/playlist.m3u")
def playlist():
    return Response(cached_m3u, mimetype="audio/x-mpegurl")


@app.route("/epg.xml")
def epg():
    return Response(cached_epg, mimetype="application/xml")


if __name__ == "__main__":
    threading.Thread(target=periodic_updater, daemon=True).start()
    app.run(host="0.0.0.0", port=10000)
