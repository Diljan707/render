from flask import Flask, Response, redirect
import requests
import re
import threading
import time

app = Flask(__name__)

cached_m3u = '#EXTM3U\n'
cached_epg = '<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n</tv>'
is_updating = False

# ਚੈਨਲਾਂ ਦਾ ਡਾਟਾ ਸਟੋਰ ਕਰਨ ਲਈ ਡਿਕਸ਼ਨਰੀ
channel_streams_map = {}


# ==========================================
# COMMON NAME FILTER
# ==========================================

regional_langs = [
    'tamil',
    'telugu',
    'malayalam',
    'marathi',
    'bengali',
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
    return re.sub(r'\s+', ' ', name).strip()


def normalize_name(name):
    name = clean_and_filter_name(name)
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
        url = "https://raw.githubusercontent.com/Sflex0719/STBPLUS/refs/heads/main/Zio.m3u"
        r = requests.get(url, timeout=5)
        if r.status_code != 200:
            return streams

        raw_text = r.text.replace('\r\n', '\n')
        entries = raw_text.split('#EXTINF:')

        for entry in entries:
            if not entry.strip():
                continue
            lines = [l.strip() for l in entry.split('\n') if l.strip()]
            if not lines:
                continue

            header_line = lines[0]
            raw_name = header_line.split(",", 1)[1].strip() if "," in header_line else header_line.strip()
            key = normalize_name(raw_name)
            if not key:
                continue

            block_lines = [l for l in lines[1:] if not l.startswith("#EXTINF:")]
            if block_lines:
                streams[key] = "\n".join(block_lines)
    except Exception as e:
        print("Secondary error:", e)
    return streams


# ==========================================
# BACKGROUND UPDATE
# ==========================================

def update_m3u_background():
    global cached_m3u, cached_epg, is_updating, channel_streams_map

    if is_updating:
        return
    is_updating = True

    try:
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

        secondary_streams = get_secondary_streams()

        dishtv_lcn_map = {}
        try:
            url = "https://raw.githubusercontent.com/your-username/repo/main/dishtv_channels.json"
            r = requests.get(url, timeout=4)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, dict):
                    dishtv_lcn_map = {str(k).lower(): str(v) for k, v in data.items()}
        except Exception:
            pass

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

        url = "https://jjtvxweb.pages.dev/jstr4web.json"
        r = requests.get(url, timeout=6)
        channels = r.json()

        m3u = '#EXTM3U url-tvg="http://localhost:10000/epg.xml"\n'
        epg = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE tv SYSTEM "xmltv.dtd">\n<tv>\n'
        
        fallback_counter = 1
        new_streams_map = {}

        for ch in channels:
            raw_name = ch.get("name", "Unknown")
            ch_id = str(ch.get("id", ""))

            clean_name = clean_and_filter_name(raw_name)
            if not clean_name:
                continue

            match_name = normalize_name(raw_name)
            if not match_name:
                continue

            url = ch.get("url", "")
            logo = ch.get("logo", "")
            category = ch.get("category", "Unknown")

            if not url:
                continue

            group = f"JioTV+ ▶ | {category}"
            group_logo = "https://i.postimg.cc/52qG6sKt/STREAMXi.png"

            name_lower = raw_name.lower()
            ch_no = dishtv_lcn_map.get(name_lower) or dishtv_lcn_map.get(ch_id)
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

            # ਲਾਇਸੈਂਸ ਕੀਅ ਤੈਅ ਕਰੋ
            if has_clearkey:
                license_key = f"{key_id}:{key_val}"
            else:
                license_key = f"{base_proxy_url}{ch_id}/"

            # ਸੈਕੰਡਰੀ ਸਟ੍ਰੀਮ ਲੱਭੋ
            sec_block = secondary_streams.get(match_name)
            if not sec_block:
                for k, v in secondary_streams.items():
                    if match_name in k or k in match_name:
                        sec_block = v
                        break

            # ਇਸ ਚੈਨਲ ਦਾ ਡਾਟਾ ਮੈਪ ਵਿੱਚ ਸੇਵ ਕਰੋ (ਫੇਲਓਵਰ ਲਈ)
            new_streams_map[ch_id] = {
                "primary_url": final_url,
                "license_key": license_key,
                "secondary_block": sec_block
            }

            # M3U ਐਂਟਰੀ (ਹੁਣ ਲਿੰਕ ਦੀ ਜਗਾ ਸਾਡਾ ਪ੍ਰੌਕਸੀ ਰੂਟ ਜਾਵੇਗਾ)
            m3u += f'#EXTINF:-1 tvg-id="{ch_id}" ch-number="{ch_no}" group-title="{group}" group-logo="{group_logo}" tvg-logo="{logo}",{formatted_name}\n'
            m3u += '#KODIPROP:inputstream.adaptive.license_type=clearkey\n'
            m3u += f'#KODIPROP:inputstream.adaptive.license_key={license_key}\n'
            m3u += '#EXTVLCOPT:http-user-agent=plaYtv/7.1.5\n'
            
            if ch_token:
                m3u += f'#EXTHTTP:{{"cookie":"{ch_token}","Origin":"https://www.jiotv.com/","Referer":"https://www.jiotv.com/"}}\n'
            else:
                m3u += '#EXTHTTP:{"Origin":"https://www.jiotv.com/","Referer":"https://www.jiotv.com/"}\n'

            # ਪ੍ਰੌਕਸੀ ਪਲੇਅਰ ਲਿੰਕ
            m3u += f'http://localhost:10000/play/{ch_id}\n\n'

            # EPG ਐਂਟਰੀ
            epg += f'  <channel id="{ch_id}">\n'
            epg += f'    <display-name lang="en">{clean_name}</display-name>\n'
            if logo:
                epg += f'    <icon src="{logo}" />\n'
            epg += f'  </channel>\n'

        epg += '</tv>'

        cached_m3u = m3u
        cached_epg = epg
        channel_streams_map = new_streams_map
        print("Playlist and Smart Proxy map updated successfully.")

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
    return "JioTV Smart Proxy Failover Server is Running!"


@app.route('/playlist.m3u')
def generate_m3u():
    return Response(cached_m3u, mimetype='audio/x-mpegurl')


@app.route('/epg.xml')
def generate_epg():
    return Response(cached_epg, mimetype='application/xml')


# ==========================================
# SMART FAILOVER PROXY ROUTE
# ==========================================
@app.route('/play/<ch_id>')
def proxy_play(ch_id):
    ch_data = channel_streams_map.get(ch_id)
    if not ch_data:
        return "Channel not found", 404

    primary_url = ch_data["primary_url"]
    
    # ਪਹਿਲਾਂ ਪ੍ਰਾਇਮਰੀ URL ਚੈੱਕ ਕਰੋ ਕਿ ਇਹ ਕੰਮ ਕਰ ਰਿਹਾ ਹੈ ਜਾਂ ਨਹੀਂ
    try:
        resp = requests.head(primary_url, timeout=3)
        if resp.status_code < 400:
            return redirect(primary_url, code=302)
    except Exception:
        pass

    # ਜੇ ਪ੍ਰਾਇਮਰੀ ਫੇਲ੍ਹ ਹੋ ਜਾਵੇ, ਤਾਂ ਸੈਕੰਡਰੀ ਬਲਾਕ ਵਿੱਚੋਂ ਲਿੰਕ ਕੱਢ ਕੇ ਰੀਡਾਇਰੈਕਟ ਕਰੋ
    sec_block = ch_data["secondary_block"]
    if sec_block:
        for line in sec_block.split('\n'):
            if line.startswith("http"):
                return redirect(line.strip(), code=302)

    # ਜੇ ਕੁਝ ਨਾ ਮਿਲੇ ਤਾਂ ਪ੍ਰਾਇਮਰੀ ਹੀ ਭੇਜ ਦਿਓ
    return redirect(primary_url, code=302)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
