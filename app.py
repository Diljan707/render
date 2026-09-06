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
# COMMON NAME FILTER & CLEANING
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


def clean_and_filter_name(name):
    if not name:
        return None

    name = name.strip()
    low = name.lower()

    if any(re.search(rf'\b{re.escape(x)}\b', low) for x in regional_langs):
        return None

    name = re.sub(r'\s+Hindi\b', '', name, flags=re.IGNORECASE)
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
            print("Failed to fetch Zio.m3u, status:", r.status_code)
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
                    clean_raw = clean_and_filter_name(raw_name)
                    if clean_raw:
                        streams[normalize_name(clean_raw)] = line
                        streams[clean_raw.lower()] = line
                    raw_name = ""
        
        print(f"Successfully loaded {len(streams)} secondary streams from Zio.m3u")
    except Exception as e:
        print("Secondary error:", e)

    return streams


# ==========================================
# DISHTV LCN FETCHER FROM GITHUB (ULTRA-FLEXIBLE)
# ==========================================

def get_dishtv_lcn_map():
    lcn_map = {}
    try:
        url = "https://raw.githubusercontent.com/Diljan707/Automated-/main/dishtv_lcn_list.txt"
        r = requests.get(url, timeout=5)
        print(f"DishTV LCN fetch status: {r.status_code}")
        if r.status_code == 200:
            lines = r.text.splitlines()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                parts = re.split(r'\||,|\t', line)
                if len(parts) >= 2:
                    p1 = parts[0].strip()
                    p2 = parts[1].strip()
                    
                    if p2.isdigit():
                        ch_name = p1
                        lcn_num = p2
                    elif p1.isdigit():
                        ch_name = p2
                        lcn_num = p1
                    else:
                        continue
                    
                    # ਸਾਰੇ ਵੇਰੀਐਂਟ ਸੇਵ ਕਰੋ ताकि ਮੈਚਿੰਗ ਵਿੱਚ ਕੋਈ ਕਮੀ ਨਾ ਰਹੇ
                    clean_ch = clean_and_filter_name(ch_name)
                    if clean_ch:
                        lcn_map[normalize_name(clean_ch)] = lcn_num
                        lcn_map[clean_ch.lower()] = lcn_num
                    lcn_map[normalize_name(ch_name)] = lcn_num
                    lcn_map[ch_name.lower()] = lcn_num
                    
            print(f"Successfully loaded {len(lcn_map)} LCN mappings from GitHub.")
    except Exception as e:
        print("DishTV Lcn fetch error:", e)
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

        # 4. DishTV LCN Map from GitHub
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
        merged_count = 0
        matched_lcn_count = 0

        for ch in channels:
            raw_name = ch.get("name", "Unknown")
            ch_id = str(ch.get("id", ""))

            clean_name = clean_and_filter_name(raw_name)
            if not clean_name:
                continue

            match_name = normalize_name(raw_name)
            clean_match = normalize_name(clean_name)
            lower_name = clean_name.lower()
            raw_lower = raw_name.lower()
            
            if not match_name:
                continue

            primary_url = ch.get("url", "")
            logo = ch.get("logo", "")
            category = ch.get("category", "Unknown")

            if not primary_url:
                continue

            group = f"JioTV+ ▶ | {category}"
            group_logo = "https://i.postimg.cc/52qG6sKt/STREAMXi.png"

            # --- DISHTV LCN MATCHING (POWERFUL CHECK) ---
            ch_no = (
                dishtv_lcn_map.get(clean_match) or 
                dishtv_lcn_map.get(match_name) or 
                dishtv_lcn_map.get(lower_name) or 
                dishtv_lcn_map.get(raw_lower)
            )
            
            if not ch_no:
                for k, v in dishtv_lcn_map.items():
                    if k in clean_match or clean_match in k or k in match_name or match_name in k or k in lower_name or lower_name in k:
                        ch_no = v
                        break
            
            if ch_no:
                matched_lcn_count += 1
            else:
                ch_no = str(fallback_counter)
                fallback_counter += 1

            formatted_name = f"{ch_no} - {clean_name}"

            # --- MERGE SECONDARY STREAM AS PRIMARY ---
            sec_stream_url = (
                secondary_streams.get(clean_match) or 
                secondary_streams.get(match_name) or 
                secondary_streams.get(lower_name) or 
                secondary_streams.get(raw_lower)
            )
            
            if not sec_stream_url:
                for k, v in secondary_streams.items():
                    if k in clean_match or clean_match in k or k in match_name or match_name in k or k in lower_name or lower_name in k:
                        sec_stream_url = v
                        break

            if sec_stream_url:
                target_url = sec_stream_url
                merged_count += 1
            else:
                target_url = primary_url

            key_id = ch.get("keyId", "")
            key_val = ch.get("key", "")
            has_clearkey = key_id and key_val and key_id != "null" and key_val != "null"

            ch_token = star_tokens.get(ch_id) or global_token
            if ch_token:
                separator = "&" if "?" in target_url else "?"
                final_url = f"{target_url}{separator}{ch_token}"
            else:
                final_url = target_url

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

            # --- FINAL MERGED STREAM LINK ---
            m3u += f'{final_url}\n\n'

            # EPG Entry
            epg += f'  <channel id="{ch_id}">\n'
            epg += f'    <display-name lang="en">{clean_name}</display-name>\n'
            if logo:
                epg += f'    <icon src="{logo}" />\n'
            epg += f'  </channel>\n'

        epg += '</tv>'

        cached_m3u = m3u
        cached_epg = epg
        print(f"Update finished! LCN Matched from GitHub: {matched_lcn_count}, Secondary Merged: {merged_count}")

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
    return "JioTV M3U Server with Fixed LCN is Running!"


@app.route('/playlist.m3u')
def generate_m3u():
    return Response(cached_m3u, mimetype='audio/x-mpegurl')


@app.route('/epg.xml')
def generate_epg():
    return Response(cached_epg, mimetype='application/xml')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
