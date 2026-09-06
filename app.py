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

        # Regional filter function (Hindi names kept)
        regional_langs = ['tamil', 'telugu', 'malayalam', 'marathi', 'bengali', 'kannada', 'gujarati', 'odia']

        def clean_and_filter_name(raw_name):
            name_lower = raw_name.lower()
            for lang in regional_langs:
                if lang in name_lower:
                    return None  
            return raw_name.strip()

        # Advanced SD/HD Separation Key Generator
        def get_channel_key(name):
            name_lower = name.lower()
            clean = re.sub(r'[^a-z0-9\s]', '', name_lower)
            if 'hd' in clean.split() or 'fhd' in clean.split():
                base = re.sub(r'\b(hd|fhd|hevc)\b', '', clean).strip()
                return base + "_hd"
            else:
                base = re.sub(r'\b(sd)\b', '', clean).strip()
                return base + "_sd"

        # 3. Secondary Zio.m3u fetch karo te SD/HD ਅਨੁਸਾਰ ਸਟੋਰ ਕਰੋ
        secondary_channels = {}
        try:
            sec_url = "https://raw.githubusercontent.com/Sflex0719/STBPLUS/refs/heads/main/Zio.m3u"
            sec_res = requests.get(sec_url, timeout=5)
            if sec_res.status_code == 200:
                lines = sec_res.text.splitlines()
                current_extinf = ""
                current_props = []
                for line in lines:
                    line = line.strip()
                    if line.startswith("#EXTINF:"):
                        current_extinf = line
                        current_props = []
                    elif line.startswith("#KODIPROP:") or line.startswith("#EXTVLCOPT:") or line.startswith("#EXTHTTP:"):
                        current_props.append(line)
                    elif line and not line.startswith("#"):
                        if current_extinf:
                            if "," in current_extinf:
                                raw_sec_name = current_extinf.split(",")[-1].strip()
                                processed_name = clean_and_filter_name(raw_sec_name)
                                if processed_name:
                                    ckey = get_channel_key(processed_name)
                                    secondary_channels[ckey] = {
                                        "props": current_props,
                                        "url": line
                                    }
                            current_extinf = ""
                            current_props = []
        except Exception:
            pass

        # 4. DishTV LCN Source Fetch Karo
        dishtv_lcn_map = {}
        try:
            dishtv_url = "https://raw.githubusercontent.com/your-username/repo/main/dishtv_channels.json"
            d_res = requests.get(dishtv_url, timeout=4)
            if d_res.status_code == 200:
                d_data = d_res.json()
                if isinstance(d_data, dict):
                    dishtv_lcn_map = {str(k).lower(): str(v) for k, v in d_data.items()}
        except Exception:
            pass

        # 5. Base Proxy URL for Primary streams
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

        # 6. Channels JSON fetch te M3U generation
        channels_res = requests.get("https://jjtvxweb.pages.dev/jstr4web.json", timeout=6)
        channels = channels_res.json()
        
        m3u = '#EXTM3U\n'
        fallback_counter = 1
        
        for ch in channels:
            raw_name = ch.get('name', 'Unknown')
            ch_id = str(ch.get('id', ''))
            
            clean_name = clean_and_filter_name(raw_name)
            if not clean_name:
                continue
                
            url = ch.get('url', '')
            logo = ch.get('logo', '')
            category = ch.get('category', 'Unknown')
            group = f"JioTV+ ▶ | {category}"
            group_logo = "https://i.postimg.cc/52qG6sKt/STREAMXi.png"
            
            if not url:
                continue
                
            name_lower = raw_name.lower()
            ch_no = dishtv_lcn_map.get(name_lower) or dishtv_lcn_map.get(ch_id)
            if not ch_no:
                ch_no = str(fallback_counter)
                fallback_counter += 1
                
            ch_key = get_channel_key(clean_name)
            
            # --- Adding (480p) or (1080p) based on SD/HD ---
            if 'hd' in ch_key:
                formatted_name = f"{clean_name} (1080p)"
            else:
                formatted_name = f"{clean_name} (480p)"
                
            key_id = ch.get('keyId', '')
            key_val = ch.get('key', '')
            has_clearkey = key_id and key_val and key_id != "null" and key_val != "null"
            
            ch_token = star_tokens.get(ch_id) or global_token
            final_url = f"{url}?{ch_token}" if ch_token and '?' not in url else f"{url}&{ch_token}" if ch_token else url
            
            # --- Primary Stream Entry ---
            m3u += f'#EXTINF:-1 tvg-id="{ch_id}" ch-number="{ch_no}" group-title="{group}" group-logo="{group_logo}" tvg-logo="{logo}",{formatted_name}\n'
            
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
                
            m3u += f'{final_url}\n'

            # --- Secondary Backup Stream Entry ---
            sec_data = secondary_channels.get(ch_key)
            if sec_data:
                m3u += f'#EXTINF:-1 tvg-id="{ch_id}" ch-number="{ch_no}" group-title="{group}" group-logo="{group_logo}" tvg-logo="{logo}",{formatted_name}\n'
                
                for prop in sec_data["props"]:
                    m3u += f'{prop}\n'
                
                m3u += f'{sec_data["url"]}\n'

            m3u += '\n'

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
    return "JioTV M3U Server (480p & 1080p Tags Added) is Running!"

@app.route('/playlist.m3u')
def generate_m3u():
    return Response(cached_m3u, mimetype='audio/x-mpegurl')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
                                      
