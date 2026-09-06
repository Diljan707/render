from flask import Flask, Response
import requests
import re
import threading
import time

app = Flask(__name__)

cached_m3u = '#EXTM3U\n'
cached_epg = '<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n</tv>'
is_updating = False


# ==========================================
# NAME CLEANING & FILTERS
# ==========================================

regional_langs = [
    'tamil',
    'telugu',
    'malayalam',
    'marathi',
    'bangla',
    'kannada',
    'gujarati',
    'odia'
]


def clean_and_filter_name(name, category=""):
    if not name:
        return None

    name = name.strip()
    low = name.lower()

    # ਸਿਰਫ਼ Kids ਕੈਟੇਗਰੀ ਵਿੱਚ ਹੀ ਭਾਸ਼ਾਵਾਂ ਵਾਲੇ ਚੈਨਲ ਫਿਲਟਰ ਹੋਣਗੇ
    if category and "kids" in category.lower():
        if any(re.search(rf'\b{re.escape(x)}\b', low) for x in regional_langs):
            return None

    # ਨਾਮ ਵਿੱਚੋਂ 'Hindi' ਹਟਾਉਣਾ
    name = re.sub(r'\s+Hindi\b', '', name, flags=re.IGNORECASE)

    # ਨਾਮ ਵਿੱਚੋਂ 'SD' ਹਟਾਉਣਾ (ਕੇਸ-ਇਨਸੈਂਟਿਵ, ਜਿਵੇਂ sd, SD, Sd)
    name = re.sub(r'\bSD\b', '', name, flags=re.IGNORECASE)

    return re.sub(r'\s+', ' ', name).strip()


def normalize_name(name):
    if not name:
        return None
    name = name.lower()
    name = re.sub(r'[^a-z0-9]+', '', name)
    return name.strip()


# ==========================================
# SECONDARY Zio.m3u STREAM EXTRACTOR
# ==========================================

def get_secondary_streams():
    streams = {}
    try:
        url = (
            "https://raw.githubusercontent.com/"
            "Sflex0719/STBPLUS/refs/heads/main/Zio.m3u"
        )
        r = requests.get(url, timeout=5)
        if r.status_code != 200:
            return streams

        lines = r.text.splitlines()
        raw_name = ""

        for line in lines:
            line = line.strip()
            if line.startswith("#EXTINF:"):
                if "," in line:
                    raw_name = line.split(",", 1)[1].strip()
                else:
                    raw_name = ""
            elif line and not line.startswith("#"):
                if raw_name:
                    key = normalize_name(raw_name)
                    if key:
                        streams[key] = line
                    raw_name = ""
    except Exception as e:
        print("Secondary error:", e)

    return streams


# ==========================================
# DISHTV LCN FETCHER FROM GITHUB
# ==========================================

def get_dishtv_lcn_map():
    lcn_map = {}
    try:
        url = "https://raw.githubusercontent.com/Diljan707/Automated-/main/dishtv_lcn_list.txt"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            for line in r.text.splitlines():
                line = line.strip()
                if not line or "|" not in line:
                    continue
                # ਮੰਨ ਲਓ ਫ਼ਾਈਲ ਵਿੱਚ ਫਾਰਮੈਟ "Channel Name | LCN" ਜਾਂ "LCN | Channel Name" ਹੈ
                parts = line.split("|")
                if len(parts) >= 2:
                    # ਜੇ ਪਹਿਲਾ ਹિસ્ਸਾ ਨਾਮ ਹੈ ਅਤੇ ਦੂਜਾ ਨੰਬਰ ਹੈ
                    name_part = parts[0].strip()
                    lcn_part = parts[1].strip()
                    
                    if lcn_part.isdigit():
                        lcn_map[normalize_name(name_part)] = lcn_part
                    elif name_part.isdigit():
                        lcn_map[normalize_name(parts[1].strip())] = name_part
        print(f"Loaded {len(lcn_map)} LCN mappings from GitHub.")
    except Exception as e:
        print("DishTV LCN fetch error:", e)
    return lcn_map


# ==========================================
# BACKGROUND UPDATE
# ==========================================

def update_m3u_background():
    global cached_m3u, cached_epg, is_updating

    if is_updating:
        return

    is_updating = True

    try:
        # 1. Star Sports tokens
        star_tokens = {}
        try:
            url = "https://allinonereborn2.online/jtv-fetch/jstarcookie/cookie.json"
            r = requests.get(url, timeout=6)
            if r.status_code == 200:
                data = r.json()
                for item in data.get("failed_results", []):
                    ch_id = str(item.get("channel_id", ""))
                    final_url = item.get("error_details", {}).get("final_url", "")
                    m = re.search(r'__hdnea__=([^&]+)', final_url)
                    if m:
                        star_tokens[ch_id] = f"__hdnea__={m.group(1)}"
        except Exception:
            pass

        # 2. Global token
        global_token = ""
        token_urls = [
            "https://allinonereborn2.online/jstrweb2/cookies.json",
            "https://allinonereborn2.online/jstrweb3/cookies.json",
            "https://allinonereborn2.online/jstrweb4/cookies.json"
        ]
        for url in token_urls:
            try:
                r = requests.get(url, timeout=3)
                if r.status_code == 200:
                    for item in r.json():
                        if isinstance(item, dict) and item.get("cookie"):
                            global_token = item["cookie"]
                            break
                    if global_token:
                        break
            except Exception:
                continue

        # 3. Secondary Streams Map
        secondary_streams = get_secondary_streams()

        # 4. DishTV LCN Map
        dishtv_lcn_map = get_dishtv_lcn_map()

        # 5. Base Proxy URL
        base_proxy_url = "https://streamflexsmm.in/license/"
        try:
            url = "https://raw.githubusercontent.com/Sflex0719/STBPLUS/main/ZioMobile.m3u"
            r = requests.get(url, timeout=3)
            if r.status_code == 200:
                for line in r.text.splitlines():
                    if "license_key=" not in line:
                        continue
                    key = line.split("license_key=", 1)[1].strip()
                    if not key or key == "null:null":
                        continue
                    m = re.search(r'(https?://[^\s]+?/)(?:\d+/)?$', key)
                    if m:
                        base_proxy_url = m.group(1)
                    else:
                        base_proxy_url = re.sub(r'\d+/?$', '', key)
                    break
        except Exception:
            pass

        # 6. Primary Channels
        url = "https://jjtvxweb.pages.dev/jstr4web.json"
        r = requests.get(url, timeout=6)
        channels = r.json()

        m3u = '#EXTM3U url-tvg="http://localhost:10000/epg.xml"\n'
        epg = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE tv SYSTEM "xmltv.dtd">\n<tv>\n'
        
        fallback_counter = 1

        for ch in channels:
            raw_name = ch.get("name", "Unknown")
            ch_id = str(ch.get("id", ""))
            category = ch.get("category", "Unknown")

            clean_name = clean_and_filter_name(raw_name, category)
            if not clean_name:
                continue

            match_name = normalize_name(raw_name)
            if not match_name:
                continue

            url = ch.get("url", "")
            logo = ch.get("logo", "")

            if not url:
                continue

            group = f"JioTV+ ▶ | {category}"
            group_logo = "https://i.postimg.cc/52qG6sKt/STREAMXi.png"

            # DishTV LCN ਮੈਚ ਕਰਨਾ
            ch_no = dishtv_lcn_map.get(match_name)
            if not ch_no:
                # ਜੇ ਸਿੱਧਾ ਮੈਚ ਨਾ ਹੋਵੇ ਤਾਂ ਪਾਰਸ਼ਲ ਮੈਚ ਦੇਖੋ
                for k, v in dishtv_lcn_map.items():
                    if match_name in k or k in match_name:
                        ch_no = v
                        break
            
            if not ch_no:
                ch_no = str(fallback_counter)
                fallback_counter += 1

            formatted_name = f"{ch_no} - {clean_name}"

            key_id = ch.get("keyId", "")
            key_val = ch.get("key", "")
            has_clearkey = key_id and key_val and key_id != "null" and key_val != "null"

            ch_token = star_tokens.get(ch_id) or global_token
            if ch_token:
                separator = "&" if "?" in url else "?"
                final_url = f"{url}{separator}{ch_token}"
            else:
                final_url = url

            # M3U Entry
            m3u += f'#EXTINF:-1 tvg-id="{ch_id}" ch-number="{ch_no}" group-title="{group}" group-logo="{group_logo}" tvg-logo="{logo}",{formatted_name}\n'

            # DRM / License Key
            if has_clearkey:
                m3u += '#KODIPROP:inputstream.adaptive.license_type=clearkey\n'
                m3u += f'#KODIPROP:inputstream.adaptive.license_key={key_id}:{key_val}\n'
            else:
                proxy = f"{base_proxy_url}{ch_id}/"
                m3u += '#KODIPROP:inputstream.adaptive.license_type=clearkey\n'
                m3u += f'#KODIPROP:inputstream.adaptive.license_key={proxy}\n'

            # User Agent & Headers
            m3u += '#EXTVLCOPT:http-user-agent=plaYtv/7.1.5\n'
            if ch_token:
                m3u += f'#EXTHTTP:{{"cookie":"{ch_token}","Origin":"https://www.jiotv.com/","Referer":"https://www.jiotv.com/"}}\n'
            else:
                m3u += '#EXTHTTP:{"Origin":"https://www.jiotv.com/","Referer":"https://www.jiotv.com/"}\n'

            # --- PRIMARY STREAM LINK ---
            m3u += f'{final_url}\n'

            # --- SECONDARY / BACKUP STREAM LINK ---
            sec_stream_url = secondary_streams.get(match_name)
            if not sec_stream_url:
                for k, v in secondary_streams.items():
                    if match_name in k or k in match_name:
                        sec_stream_url = v
                        break

            if sec_stream_url:
                m3u += f'{sec_stream_url}\n'

            m3u += '\n'

            # EPG Entry
            epg += f'  <channel id="{ch_id}">\n'
            epg += f'    <display-name lang="en">{clean_name}</display-name>\n'
            if logo:
                epg += f'    <icon src="{logo}" />\n'
            epg += f'  </channel>\n'

        epg += '</tv>'

        cached_m3u = m3u
        cached_epg = epg
        print("Playlist updated successfully with DishTV LCN and filters.")

    except Exception as e:
        print(f"Background update error: {e}")
    finally:
        is_updating = False


def periodic_updater():
    while True:
        update_m3u_background()
        time.sleep(180)


update_m3u_background()
threading.Thread(target=periodic_updater, daemon=True).start()


@app.route('/')
def home():
    return "JioTV M3U Server with DishTV LCN is Running!"


@app.route('/playlist.m3u')
def generate_m3u():
    return Response(cached_m3u, mimetype='audio/x-mpegurl')


@app.route('/epg.xml')
def generate_epg():
    return Response(cached_epg, mimetype='application/xml')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
    
