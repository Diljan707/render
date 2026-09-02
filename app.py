from flask import Flask, Response
import requests
import re
import threading
import time

app = Flask(__name__)

cached_m3u = '#EXTM3U\n'
is_updating = False

def update_m3u_background():
    global cached_m3u, is_updating
    if is_updating:
        return
    is_updating = True
    
    try:
        # 1. Star Sports dynamic cookies fetch karo
        COOKIE_STAR_SPORTS = "https://allinonereborn2.online/jtv-fetch/jstarcookie/cookie.json"
        star_tokens = {}
        try:
            res = requests.get(COOKIE_STAR_SPORTS, timeout=6)
            if res.status_code == 200:
                data = res.json()
                if data and "failed_results" in data:
                    for item in data["failed_results"]:
                        ch_id_str = str(item.get("channel_id"))
                        err_details = item.get("error_details", {})
                        final_url = err_details.get("final_url", "")
                        if "__hdnea__=" in final_url:
                            match = re.search(r'__hdnea__=([^&]+)', final_url)
                            if match:
                                star_tokens[ch_id_str] = f"__hdnea__={match.group(1)}"
        except Exception:
            pass

        # 2. Global fallback cookies fetch karo
        token_urls = [
            "https://allinonereborn2.online/jstrweb2/cookies.json",
            "https://allinonereborn2.online/jstrweb3/cookies.json",
            "https://allinonereborn2.online/jstrweb4/cookies.json"
        ]
        global_token = ""
        for url in token_urls:
            try:
                res = requests.get(url, timeout=3)
                if res.status_code == 200:
                    for item in res.json():
                        if isinstance(item, dict) and "cookie" in item:
                            global_token = item["cookie"]
                            break
                    if global_token:
                        break
            except Exception:
                continue

        # 3. Base Proxy URL
        base_proxy_url = "https://streamflexsmm.in/license/"
        try:
            target_m3u_url = "https://raw.githubusercontent.com/Sflex0719/STBPLUS/main/ZioMobile.m3u"
            res = requests.get(target_m3u_url, timeout=3)
            if res.status_code == 200:
                for line in res.text.splitlines():
                    if 'license_key=' in line:
                        l_key = line.split('license_key=')[1].strip()
                        if l_key and l_key != "null:null":
                            match = re.search(r'(https?://[^\s]+?/)(?:\d+/)?$', l_key)
                            if match:
                                base_proxy_url = match.group(1)
                            else:
                                base_proxy_url = re.sub(r'\d+/?$', '', l_key)
                            break
        except Exception:
            pass

        # 4. Channels JSON fetch te M3U generation with Filtering & Renaming
        channels_res = requests.get("https://jjtvxweb.pages.dev/jstr4web.json", timeout=6)
        channels = channels_res.json()
        
        m3u = '#EXTM3U\n'
        
        # 'punjabi' nu etho hata ditta hai, hun Punjabi channels delete nahi honge
        regional_langs = ['tamil', 'telugu', 'malayalam', 'marathi', 'bengali', 'kannada', 'gujarati', 'odia']
        
        for ch in channels:
            name = ch.get('name', 'Unknown')
            name_lower = name.lower()
            
            # Rule 1: Je channel name vich koi regional language hai (te Hindi nahi hai), taan skip/delete kar do
            skip = False
            for lang in regional_langs:
                if lang in name_lower:
                    skip = True
                    break
            if skip:
                continue
                
            # Rule 2: Je channel name de piche " Hindi" likheya hai, taan usnu hata ke clean kar do
            if " hindi" in name_lower:
                name = re.sub(r'\s+Hindi\b', '', name, flags=re.IGNORECASE)

            url = ch.get('url', '')
            logo = ch.get('logo', '')
            category = ch.get('category', 'Unknown')
            group = f"JioTV+ ▶ | {category}"
            group_logo = "https://i.postimg.cc/52qG6sKt/STREAMXi.png"
            ch_id = str(ch.get('id', ''))
            
            if not url:
                continue
                
            key_id = ch.get('keyId', '')
            key_val = ch.get('key', '')
            has_clearkey = key_id and key_val and key_id != "null" and key_val != "null"
            
            ch_token = star_tokens.get(ch_id) or global_token
            final_url = f"{url}?{ch_token}" if ch_token and '?' not in url else f"{url}&{ch_token}" if ch_token else url
            
            m3u += f'#EXTINF:-1 tvg-id="{ch_id}" group-title="{group}" group-logo="{group_logo}" tvg-logo="{logo}",{name}\n'
            
            if has_clearkey:
                license_key = f"{key_id}:{key_val}"
                m3u += f'#KODIPROP:inputstream.adaptive.license_type=clearkey\n'
                m3u += f'#KODIPROP:inputstream.adaptive.license_key={license_key}\n'
            else:
                custom_license_proxy = f"{base_proxy_url}{ch_id}/"
                m3u += f'#KODIPROP:inputstream.adaptive.license_type=clearkey\n'
                m3u += f'#KODIPROP:inputstream.adaptive.license_key={custom_license_proxy}\n'
                
            m3u += f'#EXTVLCOPT:http-user-agent=plaYtv/7.1.5\n'
            if ch_token:
                m3u += f'#EXTHTTP:{{"cookie":"{ch_token}","Origin":"https://www.jiotv.com/","Referer":"https://www.jiotv.com/"}}\n'
            else:
                m3u += f'#EXTHTTP:{{"Origin":"https://www.jiotv.com/","Referer":"https://www.jiotv.com/"}}\n'
                
            m3u += f'{final_url}\n\n'

        cached_m3u = m3u
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
    return "JioTV Zero-Latency M3U Server is Running!"

@app.route('/playlist.m3u')
def generate_m3u():
    return Response(cached_m3u, mimetype='audio/x-mpegurl')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
                            
